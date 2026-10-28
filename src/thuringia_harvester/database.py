"""One transaction per batch, field-aware reconciliation and PostgreSQL upsert."""

from datetime import UTC, datetime

from geoalchemy2.shape import from_shape, to_shape
from sqlalchemy import Engine, case, create_engine, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from .config import Settings
from .models import Observation, SignalIngest
from .transform import Corridor, StateBoundary, deduplicate, normalize

TABLE = SignalIngest.__table__
CONTENT_COLUMNS = [
    c.name
    for c in TABLE.columns
    if c.name
    not in {
        "id",
        "source_system",
        "source_key",
        "first_seen_at",
        "last_seen_at",
        "content_updated_at",
    }
]


def make_engine(url: str | URL) -> Engine:
    return create_engine(url, connect_args={"connect_timeout": 5}, pool_pre_ping=True)


def ensure_test_database(target: URL) -> None:
    """Create only a dedicated test database; never drop or reset an existing one."""
    if not target.database or not target.database.endswith(("_test", "_fixture")):
        raise ValueError("A dedicated _test or _fixture database is required")
    admin = make_engine(target.set(database="postgres"))
    try:
        with admin.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            )
            if not exists:
                quoted = conn.dialect.identifier_preparer.quote_identifier(
                    target.database
                )
                try:
                    conn.exec_driver_sql(f"CREATE DATABASE {quoted}")
                except DBAPIError as exc:
                    # Another application instance may have created it concurrently.
                    if getattr(exc.orig, "sqlstate", None) != "42P04":
                        raise
    finally:
        admin.dispose()


def prepare_database(settings: Settings) -> Engine:
    """Select, verify, and initialize the fixture destination before returning it."""
    target = settings.selected_database_url()
    if settings.fixture_mode:
        ensure_test_database(target)
    engine = make_engine(target)
    try:
        with engine.connect() as conn:
            if conn.scalar(text("SELECT current_database()")) != target.database:
                raise ValueError(
                    "Connected database does not match the selected database"
                )
        if settings.fixture_mode:
            initialize(engine)
    except Exception:
        engine.dispose()
        raise
    return engine


def initialize(engine: Engine) -> None:
    """Explicit setup only; normal ingestion never creates schema or extensions."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS iris_staging"))
        SignalIngest.metadata.create_all(conn)


def content_changed(old: dict, new: dict) -> bool:
    for name in CONTENT_COLUMNS:
        previous, current = old[name], new[name]
        if name == "geom":
            previous = to_shape(previous).wkb if previous is not None else None
            current = current.wkb if current is not None else None
        if previous != current:
            return True
    return False


def persist_batch(
    engine: Engine,
    observations: list[Observation],
    corridor: Corridor | None,
    scan_time: datetime,
    boundary: StateBoundary | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Serialize prototype writers so effective-value merging cannot lose updates.

    The advisory lock is shared by all app batches, including first inserts. Database
    uniqueness remains authoritative. External writers must respect the same lock.
    """
    if scan_time.tzinfo is None or scan_time.utcoffset() is None:
        raise ValueError("scan_time must be timezone aware")
    scan_time = scan_time.astimezone(UTC)
    unique, _ = deduplicate(observations)
    counts = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "source_updated": 0,
        "reference_updated": 0,
    }
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(176910575, 10)"))
        systems = {o.source_system for o in unique}
        existing = (
            {
                (row["source_system"], row["source_key"]): dict(row)
                for row in conn.execute(
                    select(TABLE).where(TABLE.c.source_system.in_(systems))
                ).mappings()
            }
            if systems
            else {}
        )
        effective: dict[tuple[str, str], Observation] = {}
        unconfirmed_keys: set[tuple[str, str]] = set()
        # Reconciliation is intentionally limited to trustworthy exact canonical URLs.
        for observation in unique:
            key = (observation.source_system, observation.source_key)
            url = observation.values.get("source_url")
            flags = list(observation.flags)
            incoming_id = observation.values.get("source_id")
            if key not in existing and incoming_id:
                id_matches = [
                    k
                    for k, row in existing.items()
                    if k[0] == observation.source_system
                    and row["source_id"]
                    and row["source_id"].strip() == incoming_id.strip()
                ]
                if len(id_matches) == 1:
                    key = id_matches[0]
                elif len(id_matches) > 1:
                    flags.append("ambiguous_identity")
            candidates = {
                candidate_key
                for candidate_key, row in existing.items()
                if candidate_key[0] == observation.source_system
                and url
                and row["source_url"] == url
            } | {
                candidate_key
                for candidate_key, candidate in effective.items()
                if candidate_key[0] == observation.source_system
                and url
                and candidate.values.get("source_url") == url
            }
            if key not in existing and key not in effective and candidates:
                candidate_key = next(iter(candidates))
                prior_id = (
                    effective[candidate_key].values.get("source_id")
                    if candidate_key in effective
                    else existing[candidate_key]["source_id"]
                )
                incoming_id = observation.values.get("source_id")
                if len(candidates) == 1 and (
                    not prior_id
                    or not incoming_id
                    or prior_id.strip() == incoming_id.strip()
                ):
                    key = candidate_key
                elif not incoming_id or any(
                    k[1].startswith("url:") for k in candidates
                ):
                    flags.append("ambiguous_identity")
            shared_url_identity = (
                not incoming_id
                and key[1].startswith("url:")
                and len(candidates) > 1
                and (key in existing or key in effective)
            )
            if shared_url_identity:
                flags.append("ambiguous_identity")
            old = existing.get(key)
            if key in effective:
                previous = effective[key]
                values = dict(previous.values)
                flags.extend(previous.flags)
            elif old:
                raw = old["raw_record"]
                if not isinstance(raw, dict) or not raw:
                    raise ValueError("Existing row lacks source field-presence data")
                if isinstance(raw.get("values"), dict):
                    raise ValueError(
                        "Legacy raw_record: run sql/migrate_raw_record.sql"
                    )
                values = dict(raw)
                flags.extend(old["ingest_metadata"].get("observation_flags", []))
            else:
                values = {}
            # An older replay must not resurrect a withdrawn or corrected record.
            if shared_url_identity:
                # A shared URL is not proof that this particular record was seen.
                # Keep known source fields and mark the existing candidate for review.
                if old and key not in effective:
                    unconfirmed_keys.add(key)
            elif old is None or scan_time >= old["last_seen_at"]:
                unconfirmed_keys.discard(key)
                supplied = dict(observation.values)
                # Identity is not a clearable content field; a blank ID is not a
                # withdrawal of the source identity previously reconciled by URL.
                if not supplied.get("source_id"):
                    supplied.pop("source_id", None)
                values.update(supplied)
            effective[key] = Observation(
                values,
                sorted(set(flags)),
                observation.source_system,
                observation.synthetic,
            )
        records = []
        payload = []
        for key, observation in effective.items():
            old = existing.get(key)
            if old and scan_time < old["last_seen_at"]:
                row = {name: old[name] for name in TABLE.columns.keys() if name != "id"}
                row["geom"] = to_shape(old["geom"]) if old["geom"] is not None else None
                row["exclusion_reasons"] = [
                    flag.removeprefix("excluded_")
                    for flag in old["quality_flags"]
                    if flag.startswith("excluded_")
                ]
            else:
                row = normalize(observation, corridor, scan_time.date(), boundary)
                row["source_key"] = key[1]  # Keep a reconciled URL-fallback key stable.
            records.append(row)
            if row["exclusion_reasons"] and old is None:
                continue
            if old is None:
                counts["inserted"] += 1
            elif content_changed(old, row):
                counts["updated"] += 1
                if old["raw_record"] != row["raw_record"]:
                    counts["source_updated"] += 1
                old_meta, new_meta = old["ingest_metadata"], row["ingest_metadata"]
                if any(
                    old_meta.get(name) != new_meta.get(name)
                    for name in ("a4_reference", "state_reference")
                ):
                    counts["reference_updated"] += 1
            else:
                counts["unchanged"] += 1
            values = {name: row[name] for name in CONTENT_COLUMNS}
            point = values["geom"]
            values["geom"] = (
                from_shape(point, srid=25832) if point is not None else None
            )
            values.update(
                source_system=key[0],
                source_key=key[1],
                first_seen_at=old["first_seen_at"] if old else scan_time,
                last_seen_at=old["last_seen_at"]
                if key in unconfirmed_keys
                else scan_time,
                content_updated_at=scan_time,
            )
            payload.append(values)
        if payload:
            statement = insert(TABLE).values(payload)
            excluded = statement.excluded
            changed = or_(
                *(
                    TABLE.c[name].is_distinct_from(excluded[name])
                    for name in CONTENT_COLUMNS
                )
            )
            statement = statement.on_conflict_do_update(
                index_elements=["source_system", "source_key"],
                set_={
                    **{name: excluded[name] for name in CONTENT_COLUMNS},
                    "last_seen_at": func.greatest(
                        TABLE.c.last_seen_at, excluded.last_seen_at
                    ),
                    "content_updated_at": case(
                        (
                            changed,
                            func.greatest(
                                TABLE.c.content_updated_at, excluded.content_updated_at
                            ),
                        ),
                        else_=TABLE.c.content_updated_at,
                    ),
                },
            )
            conn.execute(statement)
    # No success counters escape a transaction that failed to commit.
    return records, counts
