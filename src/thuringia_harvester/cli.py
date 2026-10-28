"""Fixture ingestion and an unverified live acquisition interface."""

import argparse
import json
import logging
from collections import Counter
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import requests
from pydantic import ValidationError
from shapely.geometry import mapping
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings
from .fetcher import FetchError, HttpFetcher, fetch_pages, read_fixture
from .parser import ParsedPage, ParseError, parse_page
from .transform import deduplicate, load_corridor, load_state_boundary, normalize

LOGGER = logging.getLogger(__name__)


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "geom_type"):
        return {"srid": 25832, **mapping(value)}
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, default=json_default, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def summarize(records: list[dict]) -> dict:
    statuses = Counter(
        "excluded" if record["exclusion_reasons"] else record["screening_status"]
        for record in records
    )
    return {
        "accepted": statuses["accepted"],
        "needs_review": statuses["needs_review"],
        "excluded": statuses["excluded"],
        "no_geometry": sum(record["geom"] is None for record in records),
        "classified_records": len(records),
        "domain": {
            name: dict(sorted(Counter(row[name] for row in records).items()))
            for name in ("approval_status", "industrial_status")
        },
        "spatial": dict(
            sorted(Counter(row["corridor_status"] for row in records).items())
        ),
        "state": dict(sorted(Counter(row["state_status"] for row in records).items())),
        "quality_flags": dict(
            sorted(
                Counter(
                    flag for record in records for flag in record["quality_flags"]
                ).items()
            )
        ),
        "excluded_records": [
            {"source_key": record["source_key"], "reasons": record["exclusion_reasons"]}
            for record in records
            if record["exclusion_reasons"]
        ],
    }


def acquire_pages(args: argparse.Namespace, settings: Settings) -> list[ParsedPage]:
    if settings.fixture_mode:
        paths = args.fixture if args.fixture else settings.fixture_files()
        if not paths:
            raise ValueError("Configure FIXTURE_PATHS or provide --fixture")
        return [
            parse_page(read_fixture(path), settings.fixture_base_url) for path in paths
        ]
    if args.fixture:
        LOGGER.warning("Live mode ignores --fixture paths and uses SOURCE_URL")
    LOGGER.warning("Live HTML format is unverified; fixture selectors are unchanged")
    with requests.Session() as session:
        fetcher = HttpFetcher(
            settings.request_timeout, settings.request_retries, session
        )
        pages = list(
            fetch_pages(settings.source_url, fetcher.fetch, settings.max_pages)
        )
    for page in pages:
        page.observations = [
            replace(observation, source_system="thueringen_planning", synthetic=False)
            for observation in page.observations
        ]
    return pages


def run(args: argparse.Namespace, settings: Settings) -> dict:
    if not args.dry_run:
        # Validate isolation before acquisition or database setup.
        settings.selected_database_url()
    scan_time = (
        datetime.fromisoformat(args.scan_time) if args.scan_time else datetime.now(UTC)
    )
    if scan_time.tzinfo is None or scan_time.utcoffset() is None:
        raise ValueError("scan-time must contain a timezone")
    scan_time = scan_time.astimezone(UTC)
    reference = settings.reference_path()
    if args.a4_geojson:
        reference = args.a4_geojson
    if args.parser_only:
        corridor = None
    elif not reference.exists() and args.allow_missing_a4:
        LOGGER.warning(
            "A4 reference missing: all corridor classifications remain unknown"
        )
        corridor = None
    else:
        corridor = load_corridor(reference, settings.a4_buffer_meters)
    boundary = (
        None
        if args.parser_only
        else load_state_boundary(args.state_geojson or settings.boundary_path())
    )
    pages = acquire_pages(args, settings)
    observations = [observation for page in pages for observation in page.observations]
    unique, duplicates = deduplicate(observations)
    db_counts = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "source_updated": 0,
        "reference_updated": 0,
    }
    if args.dry_run:
        records = [
            normalize(observation, corridor, scan_time.date(), boundary)
            for observation in unique
        ]
    else:
        from .database import persist_batch, prepare_database

        engine = prepare_database(settings)
        try:
            records, db_counts = persist_batch(
                engine, unique, corridor, scan_time, boundary
            )
        finally:
            engine.dispose()
    quality = {
        "success": True,
        "synthetic": settings.fixture_mode,
        "source_mode": "fixture" if settings.fixture_mode else "live",
        "mode": "dry_run" if args.dry_run else "database",
        "scan_time": scan_time,
        "fetched_cards": sum(page.fetched_cards for page in pages),
        "parsed_observations": len(observations),
        "unique_keys": len(unique),
        "duplicates": duplicates,
        "quarantined": sum(len(page.errors) for page in pages),
        "quarantine_details": [error for page in pages for error in page.errors],
        "parse_failures": 0,
        "network_failures": 0,
        "database_failures": 0,
        "database": db_counts,
        "a4_reference": corridor.provenance if corridor else None,
        "state_reference": boundary.provenance if boundary else None,
        "warnings": (
            ["synthetic_planning_notices"]
            if settings.fixture_mode
            else ["unverified_live_parser"]
        )
        + (
            ["fixture_arguments_ignored"]
            if args.fixture and not settings.fixture_mode
            else []
        )
        + (["a4_reference_unavailable"] if corridor is None else [])
        + (["state_reference_unavailable"] if boundary is None else [])
        + (["parser_only"] if args.parser_only else []),
        **summarize(records),
    }
    result = {
        "synthetic": settings.fixture_mode,
        "geometry_crs": "EPSG:25832",
        "quality_report": quality,
        "records": [record for record in records if not record["exclusion_reasons"]],
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        action="append",
        help="Override FIXTURE_PATHS in fixture mode; ignored in live mode",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Select live mode (FIXTURE_MODE=false); parser remains unverified",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--a4-geojson", type=Path)
    parser.add_argument("--state-geojson", type=Path)
    parser.add_argument("--allow-missing-a4", action="store_true")
    parser.add_argument(
        "--parser-only",
        action="store_true",
        help="Skip corridor measurement explicitly; no records can be accepted",
    )
    parser.add_argument("--scan-time", help="Aware ISO timestamp; default: current UTC")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quality-report", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = None
    try:
        settings = Settings()
        if args.live:
            settings = settings.model_copy(update={"fixture_mode": False})
        result = run(args, settings)
    except (OSError, ValueError, ValidationError, SQLAlchemyError, FetchError) as exc:
        # SQLAlchemy/driver errors can contain credentials or raw payloads.
        if isinstance(exc, SQLAlchemyError):
            message = (
                "Database setup/ingestion failed; no batch committed. "
                "Check connection, CREATEDB and PostGIS permissions."
            )
            failure = "database_failures"
        elif isinstance(exc, ParseError):
            message = str(exc)
            failure = "parse_failures"
        elif isinstance(exc, FetchError):
            message = str(exc)
            failure = "network_failures"
        else:
            message = (
                str(exc) if not isinstance(exc, ValidationError) else "Invalid settings"
            )
            failure = "configuration_or_input_failures"
        LOGGER.error("%s", message)
        if args.quality_report:
            write_json(
                args.quality_report,
                {
                    "success": False,
                    "synthetic": settings.fixture_mode if settings else None,
                    "source_mode": ("fixture" if settings.fixture_mode else "live")
                    if settings
                    else None,
                    "parse_failures": 0,
                    "network_failures": 0,
                    "database_failures": 0,
                    failure: 1,
                    "database": {
                        "inserted": 0,
                        "updated": 0,
                        "unchanged": 0,
                        "source_updated": 0,
                        "reference_updated": 0,
                    },
                    "error": message,
                },
            )
        return 1
    try:
        if args.quality_report:
            write_json(args.quality_report, result["quality_report"])
        if args.output:
            write_json(args.output, result)
    except OSError:
        LOGGER.error(
            "Ingestion completed but output writing failed. Database outcomes: %s",
            result["quality_report"]["database"],
        )
        return 1
    print(json.dumps(result, default=json_default, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
