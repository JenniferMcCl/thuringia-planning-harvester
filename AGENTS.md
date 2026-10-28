# AGENTS.md — IRIS-SIG-10: Thuringia Planning Harvester

These instructions are for Codex and other coding agents operating in this repository. They are **project requirements and implementation guidance**, not a claim that the fictional HTML fixtures represent the real Thuringia website.

## 1. Mission, deadline and definition of done

Build a **small, maintainable Python prototype** for the job-application engineering assignment **IRIS-SIG-10 — Thuringia Citizen Portal Planning Harvester**.

- **Objective (verbatim from brief):** "Filter industrial site approvals along the A4 corridor in Thuringia."
- **Assigned source:** `https://thueringen.de/bauleitplanung`.
- **Assigned integration pattern:** `B (HTML)` — treat this as HTML acquisition/parsing; `B` is an IRIS label, **not a publicly specified protocol**.
- **Assigned database target:** `iris_staging.signal_ingest` on **PostgreSQL 16 / PostGIS 3.4**.
- **Assigned geometry:** `POINT` in **EPSG:25832**, when the source provides sufficiently precise, trustworthy location information.
- **Constraints:** Candidate reported the assigned website inaccessible on **2026-10-27**. Source structure/selectors, actual records and publication dates cannot be verified against it. Candidate has approximately **9 focused implementation hours** over 2026-10-27/28; the application deadline was stated as **2026-10-28 at 18:00 Europe/Berlin**.
- **Success:** A runnable offline demonstration from synthetic HTML; reproducible PostgreSQL/PostGIS insertion; robust tests, especially two identical runs without duplicated rows; documentation and meaningful error/quality reporting. Prefer a small, credible deliverable over breadth.

### Highest priorities (in order)
1. End-to-end offline fixture-based pipeline; traceable records; clear inclusion/exclusion logic.
2. Real local PostgreSQL/PostGIS integration and **database-enforced idempotency**.
3. Automated tests: parsing, filtering, dates, locations, duplicate/re-run, error cases.
4. Clear README, initialization/validation SQL, synthetic sample output, quality report and limitations.
5. Optional source alternatives / future live adapter, only if genuinely verified and time remains.

Do **not** build a dashboard, REST API, AI/LLM system, Docker stack, generic ETL framework or crawler fleet. Do not spend project time recreating the full IRIS sample repository.

## 2. Requirements from the one-page assignment

Source of truth: `IRIS-SIG-10_thuringia_citizen_portal_planning_harvester.pdf` supplied by the candidate (do not silently change its meaning). The PDF may not be committed to the repo; the assignment requirements are restated below so Codex can work without it.

- Identify a lawful public source and confirm its format, or explicitly record why verification was impossible.
- Extract **source identifiers, titles, publication dates, source URLs and geographic context** when actually available.
- Normalize to `iris_staging.signal_ingest`; support **repeatable and idempotent operations**.
- Resolve defensible EPSG:25832 points; preserve uncertainty and **never silently accept invalid coordinates**.
- Address pagination/incremental retrieval *where applicable* and handle network failures, duplicates, malformed data and empty responses.
- Deliver Python code, dependency/setup instructions, no secrets, README with mapping assumptions and limitations, representative fixture/mock tests including duplicate re-runs, sample synthetic or public-source output, validation SQL, concise quality/error report.
- Respect lawful, authorized access. **Do not bypass access restrictions, CAPTCHAs, login requirements or rate limits.** The assignment expressly permits a tested fixture-based implementation and justified alternative if a URL is obsolete/inaccessible.
- **Verify source access and publication dates rather than assuming them.** Synthetic fixture dates are labeled test values, not verified public publication dates.

## 3. Source status and critical domain ambiguities

**Known:** Applicant could not access `https://thueringen.de/bauleitplanung`; automated access was also not successful in review. This does **not** prove permanent removal or reveal the portal's live DOM. Record the access date, attempted URL, observed error (only if actually observed in our environment), and fallback strategy in the README. Do not manufacture a response status or verified CSS selector.

Potential *research leads*, **not verified drop-in substitutes**:
- Official municipal public planning announcements, e.g. `https://www.am-ettersberg.de/verwaltung/bekanntmachungen-bauleitplanungen/`.
- Thüringen Viewer planning resources, e.g. `https://thueringenviewer.thueringen.de/thviewer/planung.html`.

These are context only. Their content/data model may differ; they are not proof of a single statewide HTML feed or of specific permit approvals. Any future live integration must document its specific URL, rights, format and selector observations before implementation.

### Distinguish land-use planning from industrial site approval
- **Bauleitplanung / Bebauungsplan** announcements, draft public consultations, resolutions, adopted plans and individual industrial/building permits are *not interchangeable*.
- Separate `industrial_relevance` from `approval_status`/`signal_type` where possible.
- Do not label `Entwurf`, `öffentliche Auslegung`, `Beteiligung` or pending applications as *approved*.
- `Satzungsbeschluss`, `Inkrafttreten` or plan approval might mean **approved planning**, not a permit to build a specific industrial site. Preserve the original procedural stage and record an explicit assumption or `review` classification if needed.
- A mere keyword (`Industrie`, `Gewerbe`) is not enough to establish a confirmed industrial approval. Use transparent rules and test them; **avoid invented legal certainty**.

### Geographic reference datasets: complete A4 and Thüringen boundary

**Two independent real-world OSM/Overpass GeoJSON inputs are required for confirmed spatial screening:**

- `data/reference/a4_thueringen.geojson`: A4 motorway `LineString`/`MultiLineString` features, including the stretch through **Hessen near Wommen/Herleshausen**. Used for distance only; do **not** clip the motorway to Thüringen before calculating distances.
- `data/reference/thueringen_boundary.geojson`: the **complete Thüringen administrative area**, represented as a valid `Polygon`/`MultiPolygon`. Used to determine whether the project location is within the state. It is *not* a motorway feature and must not be approximated with a bounding box or invented polygon.

These files were added to the applicant's project during development; always **inspect the actual current files**, rather than assuming they are present, complete, valid or already committed. They are publicly sourced reference geometry, **not** real planning announcements. Never generate fake reference files as replacements or claim unverified OSM coverage.

**Why the initial A4 extract failed:** the original Overpass query selected A4 ways only inside the Thüringen administrative area. The motorway briefly traverses Hessen, so the query omitted the Hessian stretch (earlier observed longitude interval about **10.097534–10.1917413**, approximately **6.6 km**). The A4 GeoJSON was replaced with a wider extract. Confirm the gap is actually resolved in the local file; avoid claiming success merely because the filename is unchanged. OSM represents two carriageways and separate way segments, so check actual road coverage instead of demanding one topologically connected `LineString`.

**Reproducible Overpass extraction (examples, NOT proof of the exact downloaded queries):**

```overpass
[out:json][timeout:180];
area["name"="Thüringen"]["boundary"="administrative"]["admin_level"="4"]->.thueringen;
(
  way["highway"="motorway"]["ref"~"^A ?4$"](area.thueringen);
  way["highway"="motorway"]["ref"~"^A ?4$"](50.85,9.95,51.15,10.40);
);
out geom;
```

```overpass
[out:json][timeout:180];
relation["boundary"="administrative"]["admin_level"="4"]["name"="Thüringen"];
out geom;
```

Export each via `https://overpass-turbo.eu/` -> Export -> Data -> GeoJSON, and inspect the result. Overpass may export a boundary as **lines/relations instead of a Polygon/MultiPolygon**; if so, the output is **not usable as the study-area polygon** until a correctly assembled, validated polygon is obtained. Never interpret arbitrary boundary lines as a fillable state polygon.

**Provenance and rights:** maintain `data/reference/README.md` with the actual download/extraction date, source service, exact query *actually used*, feature counts, geometry types, CRS, coverage checks and any known limitations for **both files**. Attribute **© OpenStreetMap contributors (ODbL)** with `https://www.openstreetmap.org/copyright`. Don't invent timestamps, metadata or verification results. These GIS datasets have licensing considerations distinct from the Python code. Do not rely on Google Maps geometry.

**Validation and processing:**

1. Read both local GeoJSON files using **GeoPandas** (`geopandas.read_file`) where appropriate, and use **Shapely** and **pyproj** for validation/spatial operations. GeoPandas is explicitly allowed and preferred for loading/reprojection; do not maintain a second redundant custom reader. Use a single, clear implementation and cache/reference geometries once per run, not once per row.
2. Verify GeoJSON structure, nonempty usable geometries, finite coordinates, plausible geographic extents, supported CRS and absence of unhandled corrupt/tainted geometry. Require A4 line geometry with appropriate `highway=motorway`, `ref=A4` tags when present; require a complete, valid Thüringen `Polygon`/`MultiPolygon` for the boundary. Resolve any multiple polygon features intentionally rather than blindly joining unrelated areas. Validate the former gap region and other significant gaps (allow multiple carriageways).
3. Transform both reference layers to **EPSG:25832** before comparing with site points. Validate incoming site coordinate CRS and values; reproject verified EPSG:4326 coordinates with the proper axis order. No distances in angular degrees.
4. Set `inside_state = thuringia_polygon_25832.covers(site_point_25832)` (boundary included); set `distance_to_a4_m = site_point_25832.distance(a4_lines_25832)` and `corridor_status='inside'` when `distance_to_a4_m <= A4_BUFFER_METERS`, otherwise `outside`. Default `A4_BUFFER_METERS=10000` (10 km **on either side**), explicitly a project assumption rather than an IRIS requirement.
5. **Accepted geographic status requires both:** `state_status='inside'` and `corridor_status='inside'`. The effective geographic study area is `Thüringen polygon ∩ buffer(A4 lines, threshold)`. The motorway may lie in Hessen; an industrial project there does **not** qualify as in Thüringen.
6. Missing/invalid/ambiguous project coordinates result in `geom=NULL`, `distance_to_a4_m=NULL`, `state_status='unknown'`, `corridor_status='unknown'` and meaningful quality flags. Municipality-only evidence does not justify an invented site centroid or a verified in-state point. Points within/on the polygon are `inside`, verified outside points are `outside`; handle uncertain boundary precision conservatively.
7. If **either** reference file is absent, invalid or cannot be validated, fail any mode requiring confirmed spatial filtering with a clear reason. Parser-only / explicit no-spatial dry-run modes can proceed but must not mark a record `accepted`. Never silently fall back to synthetic A4 lines or state polygons for real classifications.
8. Keep synthetic line/polygon shapes **in tests only** to verify exact distance, inclusion and boundary behavior. Use separate smoke/integration tests against the actual local OSM files; don't present synthetic HTML project coordinates as independently verified real locations.
9. When either reference GeoJSON changes, recompute geographic outcomes for affected persisted rows **explicitly**; do not update `last_seen_at` for records not re-observed from the source. A changed spatial classification is a derived-content update, not necessarily a change in the source announcement. Document reference provenance/version (or its absence) so no stored distance is misrepresented as current.

## 4. Architecture: deliberately simpler than IRIS sample

Implement a small single-purpose application with the following **agreed project layout** (create files incrementally; no empty placeholder modules if unnecessary):

```text
thuringia-planning-harvester/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock                     # commit if generated
├── .env.example                # safe keys only; never secrets
├── .gitignore
├── src/
│   └── thuringia_harvester/
│       ├── __init__.py
│       ├── cli.py               # offline/live command, summary, orchestration
│       ├── config.py            # typed settings, default assumptions
│       ├── fetcher.py           # HTTP/pagination, fixture input adapter
│       ├── parser.py            # HTML -> source records, URL resolution
│       ├── transform.py         # validation, domain/stage/2-stage spatial filters, CRS
│       ├── models.py            # typed record(s), SQLAlchemy staging table model
│       └── database.py          # engine/session + idempotent persistence
├── data/
│   └── reference/
│       ├── a4_thueringen.geojson       # actual OSM motorway line export
│       ├── thueringen_boundary.geojson # actual OSM state polygon
│       └── README.md                  # provenance for both and ODbL notice
├── tests/
│   ├── fixtures/
│   │   ├── planning_basic.html
│   │   └── planning_edge_cases.html
│   ├── test_parser.py
│   ├── test_transform.py
│   ├── test_corridor.py          # A4 distance + state polygon tests; OSM smoke tests
│   └── test_database.py
├── sql/
│   ├── init.sql                # idempotent schema/table/index/bootstrap SQL
│   └── validation.sql          # count, duplicates, CRS, nulls, quality checks
└── examples/
    ├── sample_output.json      # clearly labeled SYNTHETIC
    └── quality_report.json     # example deterministic counts
```

**Processing boundary:** `fetcher -> parser -> transform/classify -> database`; `cli` coordinates. Fixture and live acquisition are separate input adapters but must share parsing, screening, and persistence behavior. No module should open sockets or connect to a database **at import time**. Parsing/filtering/geometry logic must be testable without any database.

**Database separation:** `models.py` declares the staging row and its constraints; `database.py` handles SQLAlchemy engine, transactions and inserts; neither parses HTML. Keep **one explicit transaction boundary per batch**; do not let generic CRUD helpers commit unpredictably. `config.py` owns external URLs, CRS, `A4_GEOJSON_PATH`, `STATE_GEOJSON_PATH`, distance threshold, timeouts, DB URL and run mode. Keep network requests behind an injectable interface so tests can mock them.

## 5. IRIS sample repository: take useful conventions, not its complexity

Reference: `https://github.com/amaurisantosjr/iris-sample` (a **different** NRW data center BI application). It has `app/scrapers`, `app/parsers`, `app/transformers`, `app/loaders`, `app/database/models`, `app/database/repositories`, `app/runners`, SQLAlchemy and Alembic; a separate Streamlit UI; root `pyproject.toml`; PostgreSQL in Docker Compose.

**Recognizable practices to respect:** `snake_case` modules/methods, `PascalCase` class names, 4-space indentation, useful docstrings, type hints, separated ingestion phases, SQLAlchemy declarative models, config from environment, source IDs and database uniqueness, descriptive logs.

**Improvements to apply:** Consistent PEP 8 + Ruff formatting, lean type-annotated functions, standard `logging` instead of mixed `print`/logging internally, explicit exception handling, consistent dependency management, one transaction owner, fewer redundant layers, no hard-coded credentials or paths. Keep comments useful and brief rather than copying the sample's excessive separators and one-expression-per-line style.

**Differences not to overlook:** Example uses `iris_core` and PostGIS geometries often in EPSG:4326, Docker Compose PostgreSQL 17/PostGIS 3.5, and an unrelated dashboard. **Your target is `iris_staging.signal_ingest`, PostgreSQL 16/PostGIS 3.4, point SRID 25832.** Do not fork the example just to duplicate its layout. It has no explicit license; do not copy large sections of code verbatim.

## 6. Python tools / libraries (minimal)

Use modern Python 3.12+ on the applicant's **Apple Silicon M2 Mac**, with **PyCharm, uv and native Postgres.app**; **no Docker and no CPU emulation**.

Core dependencies in root `pyproject.toml`:
- `requests` — HTTP acquisition, explicit timeout and bounded retries.
- `beautifulsoup4` — tolerant HTML parsing (`html.parser` standard library backend is sufficient).
- `sqlalchemy>=2,<3` — database model/queries and PostgreSQL upserts.
- `geoalchemy2` — PostGIS geometry model.
- `psycopg[binary]` — PostgreSQL driver.
- `pyproj` — WGS84/EPSG:4326 to EPSG:25832 (`always_xy=True`).
- `shapely` — point/line/polygon geometry and geographic screening.
- `geopandas` — read, validate and reproject the two real reference GeoJSON layers; use its GeoDataFrame/GeoSeries operations where useful.
- `python-dotenv` **or** `pydantic-settings` for local `.env` configuration; choose one, avoid overlap.
- `pydantic` **optional** for structured validation; standard `dataclasses` are also fine. Do not include a dependency unless code uses it.

Development: `pytest` (including integration tests), `ruff`, managed with `uv`; `pytest-mock` optional. **GeoPandas is intentionally permitted/used in the current implementation.** Do not add unrelated UI/AI/browser automation dependencies, nor duplicate GeoPandas capabilities unnecessarily. Install only packages actually used; `pandas` may be present as a GeoPandas dependency, not as a requirement for unrelated analytics.

`pyproject.toml` should declare runnable scripts where convenient, pytest and Ruff configuration, and the `src` package layout. Keep `.env.example` and `.gitignore` correct. No secrets in repository, logs, fixtures or sample outputs.

## 7. Staging table, missing values, identity, and scan semantics

The brief names the target `iris_staging.signal_ingest`, **but gives no actual DDL or IRIS-specific column contract**. Implement the following reasonable prototype mapping. Explain the assumption in the README and keep a single table plus a machine-readable quality report. `quality_flags` and `raw_record` should be JSONB, not separate join tables.

### Proposed `iris_staging.signal_ingest` columns

| Column | PostgreSQL type | Null? | Meaning / invariant |
|---|---|---|---|
| `id` | `BIGINT GENERATED ... AS IDENTITY PRIMARY KEY` | No | Internal, never used as the source identity |
| `source_system` | `TEXT` | No | Stable namespace, e.g. `thueringen_planning` |
| `source_id` | `TEXT` | Yes | Actual ID supplied by source, unmodified where practicable |
| `source_key` | `TEXT` | No | Canonical persistent key, see rules below |
| `source_url` | `TEXT` | Yes | Absolute item URL (not mere listing page) |
| `title` | `TEXT` | Yes | Announced title; missing is a quality flag, not an invented placeholder |
| `description` | `TEXT` | Yes | Original text/summary if available |
| `publication_date` | `DATE` | Yes | Actual source publication date; never substitute scan date |
| `publication_date_raw` | `TEXT` | Yes | Unparsed original date if missing/invalid/uncertain |
| `municipality` | `TEXT` | Yes | As reported, not inferred from point without explicit evidence |
| `location_text` | `TEXT` | Yes | Original location wording |
| `procedure_status` | `TEXT` | Yes | Original status in German |
| `approval_status` | `TEXT` | No | `approved`, `not_approved`, `unknown` (define handling of planning-only acts) |
| `industrial_status` | `TEXT` | No | `industrial`, `non_industrial`, `unknown` |
| `signal_type` | `TEXT` | Yes | Stable normalized signal category if legally/supportably identifiable |
| `geom` | `geometry(Point,25832)` | Yes | Verified sufficiently precise project point |
| `distance_to_a4_m` | `DOUBLE PRECISION` | Yes | Computed from **real A4** in projected metres, never negative |
| `corridor_status` | `TEXT` | No | `inside`, `outside`, `unknown`, based on A4 proximity |
| `state_status` | `TEXT` | No | `inside`, `outside`, `unknown`, based on Thüringen boundary |
| `screening_status` | `TEXT` | No | Only `accepted` or `needs_review`; `excluded` is **not a stored table status** |
| `quality_flags` | `JSONB` | No | Stable JSON array of warning strings, default `[]` |
| `raw_record` | `JSONB` | Yes | Extracted source fields as supplied, not pipeline-derived fixture metadata |
| `ingest_metadata` | `JSONB` | No | Processing metadata: observation flags and A4/state reference provenance; default `{}` |
| `first_seen_at` | `TIMESTAMPTZ` | No | UTC time record was first successfully ingested, immutable |
| `last_seen_at` | `TIMESTAMPTZ` | No | UTC time this identifiable record was most recently **successfully observed** |
| `content_updated_at` | `TIMESTAMPTZ` | No | UTC time normalized persisted content last materially changed |

Avoid extra tables and columns unless necessary for correctness. Add **`UNIQUE (source_system, source_key)`**, useful checks on enumerations and a GiST index on `geom` if appropriate. Only classify confirmed industrial approvals **spatially verified inside Thüringen and within the measured real-A4 buffer** as `accepted`; ambiguities belong in `needs_review`. Clearly irrelevant, known not approved, verified outside-state or demonstrably out-of-corridor records are **excluded from this target table** and counted with reasons in the run quality report. There is no `screening_status='excluded'` in the table. Don't erase previously stored historical rows simply because they weren't seen in the latest scan.

### Missing and invalid values: deliberate triage

1. **Accepted:** confirmed industrial approval AND reliably located within/on the Thüringen administrative boundary AND inside the configured real A4 corridor; stable source identity. Store with `screening_status='accepted'`.
2. **Needs review:** plausibly relevant record with a stable identity but uncertain approval type/status, location, date, **state membership** or corridor membership. Store with `screening_status='needs_review'`; add explicit `quality_flags`. Missing publication date/title is generally **not** enough to discard a traceable relevant record.
3. **Excluded:** conclusively non-industrial, draft/rejected rather than approved, reliably **outside Thüringen**, or reliably outside the A4 corridor. Do **not** store excluded rows in `signal_ingest` at all; include stable identity and reason in the run quality report. Handle any previously stored row that becomes conclusively ineligible using the explicit transition policy below.
4. **Unidentifiable/malformed:** neither reliable source ID nor canonical **item** URL => cannot compute stable key; do not insert. Count as quarantined/rejected in the quality report, with field-level reasons.

Never use `0`, `''`, `1970-01-01`, `today`, or `Point(0,0)` as missing placeholders. SQL `NULL` means unknown, not zero. Date parse failure => `publication_date=NULL` and preserve raw date text/flag. Unknown location => `geom=NULL`, distance `NULL`, **state `unknown` and corridor `unknown`**. Validate latitude/longitude numeric finite values, bounds, CRS and regional plausibility; don't silently swap axes or invent geocoded coordinates. Convert verified EPSG:4326 to EPSG:25832 with `always_xy=True`; accept verified projected EPSG:25832 after validation.

### Stable identity: exact `source_system` + `source_key` rules

- Use `source_system='thueringen_planning'` consistently for **real-source** ingestion. For **synthetic fixture mode**, use a *different but stable* namespace such as `thueringen_planning_fixture` (and/or an isolated local test database); this prevents synthetic rows from being mistaken for public-source data. The `(source_system, source_key)` pair MUST remain unchanged across all rescans **within a mode**. Fixture records are distinguished by their source namespace and/or isolated test database. **Do not add `synthetic` to `raw_record`**, which must contain only extracted source data. Clearly label synthetic data in README, quality reports and sample output (a top-level `synthetic: true` in exported sample JSON is fine). Never conflate unrelated sources or records with identical titles.
- `raw_record` is the direct parsed source-field mapping; absent keys remain absent
  and explicitly empty fields are stored as null. Keep `observation_flags`,
  `a4_reference` and `state_reference` in `ingest_metadata`, never in `raw_record`.
  This single additional JSONB column is justified by source-only storage while
  retaining duplicate history and reference versions. The storage migration
  `sql/migrate_raw_record.sql` must preserve identities and all timestamps.
- Determine `source_key` **before writing**:
  - If a genuine source ID exists: `source_key = 'id:' + normalized_source_id` (strip surrounding whitespace and normalize only documented insignificant differences; preserve significant punctuation/case). Save original in nullable `source_id`.
  - Otherwise, if a stable, canonical absolute **individual record** URL exists: `source_key = 'url:' + canonical_url`. Keep scheme/host normalization and fragment removal minimal; retain ID-bearing query parameters. Remove trackers only where proven safe; do **not** use the collection/list page URL for all records.
  - Otherwise: `source_key` cannot be determined => quarantine with error; never hash only title/date as a supposed stable ID.
- **Database uniqueness is the authority**: `UNIQUE (source_system, source_key)`; no accidental UNIQUE on `title` or nullable `source_id` alone. Never merge synthetic and real-source namespaces. Identical titles with different source IDs must remain separate records.
- Stable source IDs **survive source URL/title changes**. A URL-fallback row that gains a source ID on a later scan needs deliberate reconciliation: match a unique trustworthy prior canonical item URL, **keep the existing `source_key`** or perform an explicitly tested atomic key migration; update `source_id` instead of creating a second row. If matching is ambiguous, flag for review rather than merging. Do not silently change identity conventions between runs.
- Deduplicate input **before one PostgreSQL upsert statement** on the unique pair. Repeated exact records collapse to one; conflicting duplicates follow a clearly documented deterministic precedence (for these fixtures, last occurrence of source observation wins for **explicit values**, while earlier nonmissing values may fill later omissions). Record `duplicate_in_batch` and any conflicts.
- An existing URL-fallback key is not sufficient evidence to attribute an ID-less
  observation when multiple identities now share that URL. Preserve known source
  fields, flag the existing URL candidate `ambiguous_identity`/`needs_review`,
  and do not refresh its `last_seen_at` without an identifiable observation.

### Exact scan/update/upsert behavior (required)

The application must handle *first appearance*, *identical rescan*, *changed record*, *partial rescan*, *explicitly changed/withdrawn record* and *not observed* distinctly:

1. Establish `scan_time` once per successful scan/batch, as an **aware UTC timestamp**; use that exact timestamp for all rows actually observed in that scan. Ensure clock/source time is not confused with `publication_date`.
2. **First insert**: save normalized fields, `first_seen_at=scan_time`, `last_seen_at=scan_time`, `content_updated_at=scan_time`.
3. **Identical rescan**: find existing row by `(source_system, source_key)`; **no second row**; retain `id`, `first_seen_at`, and `content_updated_at`; set `last_seen_at` to the more recent `scan_time` even if content is identical. An `ON CONFLICT DO NOTHING` is **not sufficient**, because it fails to refresh `last_seen_at`.
4. **Changed valid data**: upsert corrected source fields, recompute dependent classification, `geom`, **state membership**, distance and flags from the **effective normalized values**; preserve `first_seen_at`; set `last_seen_at=scan_time` and `content_updated_at=scan_time` if persisted meaningful content changed. E.g. a corrected `publication_date` or approved→revoked status updates the same row, not a duplicate.
5. **Field omitted on a partial/incomplete scrape**: do not overwrite a previously valid value with `NULL` merely because the field was absent. Distinguish **not supplied** from **explicitly changed or invalid**; this requires field-presence tracking in parser/transform, not indiscriminate `COALESCE` on every column. For unchanged/missing optional values, retain previous content and refresh `last_seen_at`.
6. **Explicit correction, withdrawal, invalid location or altered status**: do not freeze incorrect old values with blanket `COALESCE`. Allow intentional clear/replace, recompute `approval_status`, `industrial_status`, `geom`, `distance_to_a4_m`, `state_status`, `corridor_status`, `screening_status` and quality flags from the effective record. If a previously `accepted` row becomes **uncertain**, change it to `needs_review` in place. If positive new evidence conclusively establishes exclusion (e.g. rejected/not-industrial/outside Thüringen/outside the A4 corridor), **remove that identity from `signal_ingest` in the same controlled transaction and record the exclusion in the quality report**; do not retain a row with `screening_status='excluded'`. Do not delete merely because an observation failed, a field was omitted, or the record was absent from one scan. Clearly document that this prototype's staging table holds current accepted/reviewable candidates, **not a permanent historical audit ledger**; historical exclusion details are limited to generated quality reports.

7. **Not seen in an otherwise successful scan**: keep previous row and `last_seen_at` unchanged. Do not delete or mark withdrawn just because the page is empty, source access failed or pagination was incomplete. An HTTP failure/parse failure does not count as a successful observation.
8. **Chronology**: do not move `last_seen_at` backwards if a replay has an older timestamp. Use `GREATEST(existing.last_seen_at, scan_time)` for replays. `content_updated_at` must represent actual updates and should not regress for replays; tests can inject explicit scan times to avoid flaky clocks.
9. **Database transaction**: process validated batch in one `with engine.begin() as conn:` (or equivalent SQLAlchemy session transaction). Do not commit in individual repository methods. Roll back on DB errors, report counts honestly; record-level parser errors need not abort all safe records.

**Reference-data updates are not source rescans:** if the A4 or Thüringen boundary changes, recompute derived geometry/status for persisted rows where feasible. If derived values change, update `content_updated_at` (without fabricating a new source observation); do **not** update `last_seen_at` unless the source record was actually observed again. Conclusively excluded rows follow the removal/report policy above. The pipeline should not silently leave old distances after reference replacement.

**Recommended implementation:** use SQLAlchemy 2.x PostgreSQL dialect `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update(index_elements=["source_system", "source_key"], set_=...)`. Ensure conflict updates **always refresh `last_seen_at` for actual observed records**, while meaningful-field comparisons determine whether `content_updated_at` changes. A `WHERE data_differ` clause on the entire upsert would incorrectly prevent `last_seen_at` refreshing on identical rescans. Implement these semantics in readable Python + explicit SQLAlchemy statements rather than a generalized ORM framework; use `IS DISTINCT FROM` or carefully scoped equality comparisons for NULL-aware change detection. Do not use a material-change checksum based on scan timestamps, order-unstable JSON, or missing-field placeholders.

**Minimal SQL pattern illustrating the timestamp invariant for eligible, stored rows (not the full column/geometry update or exclusion-removal path):**

```sql
INSERT INTO iris_staging.signal_ingest
    (source_system, source_key, source_id, title,
     first_seen_at, last_seen_at, content_updated_at,
     approval_status, industrial_status, state_status, corridor_status,
     screening_status, quality_flags)
VALUES
    (:source_system, :source_key, :source_id, :title,
     :scan_time, :scan_time, :scan_time,
     :approval_status, :industrial_status, :state_status, :corridor_status,
     :screening_status, '[]'::jsonb)
ON CONFLICT (source_system, source_key)
DO UPDATE SET
    last_seen_at = GREATEST(
        iris_staging.signal_ingest.last_seen_at, EXCLUDED.last_seen_at
    ),
    source_id = COALESCE(EXCLUDED.source_id, iris_staging.signal_ingest.source_id),
    title = COALESCE(EXCLUDED.title, iris_staging.signal_ingest.title),
    content_updated_at = CASE
        WHEN (EXCLUDED.source_id IS NOT NULL AND
              iris_staging.signal_ingest.source_id IS DISTINCT FROM EXCLUDED.source_id)
          OR (EXCLUDED.title IS NOT NULL AND
              iris_staging.signal_ingest.title IS DISTINCT FROM EXCLUDED.title)
        THEN GREATEST(
            iris_staging.signal_ingest.content_updated_at,
            EXCLUDED.last_seen_at
        )
        ELSE iris_staging.signal_ingest.content_updated_at
    END;
```

**NOTE:** The SQL block is **illustrative only** and omits other field updates, field-presence/explicit-clear decisions, **state-boundary screening**, exclusion/deletion handling, spatial validation and schema defaults. Implement the full policy above, not merely this shortened SQL. Ensure `source_key` cannot be null and the table is uniquely constrained.

### Report and validate actual results

- Distinguish **fetched cards**, **parsed observations**, **deduplicated unique keys**, **new inserts**, **meaningful updates**, **unchanged re-observations** (refreshed `last_seen_at` only), **needs_review**, **excluded**, **quarantined**, **no_geometry**, **network/parse failures**. Define each counter clearly to avoid double-counting.
- `sql/validation.sql` must show `COUNT(*)`, the uniqueness query on `(source_system,source_key)`, status distribution (**no stored `excluded` rows**), null dates/geometries, invalid SRIDs (`ST_SRID(geom)!=25832`), invalid geometries where present, accepted rows with unknown/outside **state or corridor**, and timestamps (`first_seen_at <= last_seen_at`, `content_updated_at <= last_seen_at` under normal chronological scans).
- Demonstrate with controlled scans: 1st scan inserts; identical 2nd scan keeps row count fixed but advances `last_seen_at` and preserves `content_updated_at`; corrected 3rd scan updates the existing row and advances both; an incomplete scan doesn't erase known values; a missing-from-scan row remains with unchanged `last_seen_at`; two separate IDs with same title remain separate; a changed **state/corridor** result updates classification; a conclusively disqualified existing row is removed from staging and its exclusion reported.

## 8. HTML fixtures: two deliberately distinct test datasets

The two HTML files in `tests/fixtures/` are **fully synthetic**. They are *not* screenshots, saved pages or scraped HTML from the assigned website. Their invented source IDs, titles, dates, locations and URLs are **test inputs only**. URLs use the reserved `.invalid` domain so they cannot be confused with real records.

1. `planning_basic.html` — compact, easy-to-inspect **base cases**: confirmed industrial approval, relevant business/industrial project, draft industrial plan (not approval), approved residential plan (not industrial), no precise location (geometry NULL / corridor unknown), duplicate source ID within a page, a geographically distant industrial project. Also includes a `rel="next"` link to a mocked second page.
2. `planning_edge_cases.html` — large **diverse/robustness suite**: German/ISO/missing/impossible dates; escaped German characters; status ambiguity (`Satzungsbeschluss`, publication of a draft, rejection); industrial vs retail/residential; duplicate/revised source IDs; same title with different IDs; missing identifiers; relative/empty URLs; missing, out-of-range and swapped coordinates; already projected EPSG:25832 values; municipality-only locations; alternate HTML card markup; unexpected nesting; noisy elements; metadata in different formats.

Fixtures may include `data-test-expected-*` attributes **solely for assertions**. Production logic **MUST NOT** inspect these expectation hints. Fixtures simulate a possible DOM, not the site's actual selectors; keep selectors configurable and isolate them in `parser.py`. Do not claim a live parser has been verified.

For pagination, mock `https://example.invalid/thueringen/bauleitplanung?page=1` with `planning_basic.html`, and `...?page=2` with `planning_edge_cases.html`. Test retries/network errors through mocked `requests` responses — never call `.invalid` hosts for real.

For spatial unit tests, inject a clearly synthetic EPSG:25832 **line and polygon** to assert exact point-to-road distances and state containment independently. For actual reference smoke tests and demos, load **both** `data/reference/a4_thueringen.geojson` and `data/reference/thueringen_boundary.geojson`, validate and reproject them. Never substitute synthetic line/polygon as real references. Record both OSM datasets' provenance and licensing separately.

## 9. Test plan and evidence

Minimum `pytest` checks:

1. Parse expected base records, text, IDs, dates, canonical individual URLs and German characters.
2. Differentiate confirmed industrial approval from drafts/consultation, residential and ambiguous approval statuses; preserve legally distinct stages.
3. Parse German and ISO dates; flag missing/invalid dates; never substitute crawl time as publication date.
4. Transform EPSG:4326 -> EPSG:25832 and validate numeric, finite, plausible coordinates. Reject unclear source CRS; preserve NULL geometry and uncertainty.
5. **Synthetic spatial unit tests:** inject EPSG:25832 known simple A4 `LineString` and Thüringen `Polygon`, assert exact metres and state inclusion. Test: inside state + within corridor; outside state + near A4 (Hessen case); inside state + far from A4; on administrative boundary; exactly 10 km from A4; missing/invalid location. No degree-based distance calculations.
6. **Actual OSM GeoJSON smoke tests:** load **both** reference files when present; verify A4 line coverage (including the corrected Herleshausen interval), valid complete state polygon, CRS and projection, correct spatial status for verified reference positions. A missing file causes a **skipped** smoke test, never a falsely passing one; any ingestion mode requiring verified classification must fail clearly if either reference is unusable.
7. **Stable identity:** source ID primary, canonical URL fallback, missing both rejects, same title with different IDs preserved, source URL changed but ID unchanged stable, new source ID added to a unique URL-fallback row reconciled without duplicate where safely possible, ambiguous URL matches reviewed.
8. **Batch duplicates:** multiple same-key entries deduplicated before upsert (last explicit observation wins, without erasing nonmissing values due to omission). Repeat upsert cannot create a second row.
9. **Time-controlled actual database runs:** first run inserts; identical second run row count stays fixed, `last_seen_at` advances and `first_seen_at`/`content_updated_at` don't; changed third run advances `content_updated_at`; partial omission preserves known values; revised state/approval/coordinates invalidate stale `accepted`; conclusively excluded existing identities are removed and counted in the report; not reobserved leaves `last_seen_at` intact. Test timestamps in UTC, and reference-only recalculation that does **not** refresh `last_seen_at`.
10. Mock pagination, no results, timeouts, HTTP 429/5xx and malformed records; bounded retries, no access bypass; no false `last_seen_at` refresh after failed fetch.
11. Verify schema/unique `(source_system,source_key)`, `state_status`, `screening_status` allowed values **only `accepted`/`needs_review`**, PostGIS SRID=25832, SQL upsert, exclusion/removal and transaction rollback against actual local PostgreSQL 16/PostGIS 3.4 if configured. Otherwise integration tests must show **skipped**, not pretend to pass.
12. Check `src` package installation, CLI fixture-only mode, quality JSON and README instructions from a fresh environment.

Keep the example `sql/validation.sql` accurate to the actual DDL. Produce sample synthetic JSON and concise quality report with clearly separated parser, domain, spatial and database outcome counters. Do not claim live site functionality was validated.

## 10. Interface / local setup / documentation

- **Approved mode and database isolation contract:** `FIXTURE_MODE=true` is the
  default and uses local `FIXTURE_PATHS` (default
  `tests/fixtures/planning_basic.html`). Repeated `--fixture PATH` overrides these
  paths only in fixture mode. With `FIXTURE_MODE=false`, ignore any `--fixture`
  arguments with a notice and use `SOURCE_URL`; `--live` explicitly selects this
  interface. Never fall back from failed live acquisition to fixture input.
- Fixture writes use **only `TEST_DATABASE_URL`**, never `DATABASE_URL`. Require a
  dedicated database name ending in `_test` or `_fixture`, different from the live
  database name. Create that database if missing using a separate PostgreSQL
  maintenance/autocommit connection, then initialize PostGIS/schema; reuse it on
  later runs. Do not drop/reset existing databases automatically. Fail clearly on
  unavailable permissions or connection failures. Dry runs must neither create
  nor write databases. Live writes select only `DATABASE_URL`.
- Keep the live interface visible, but **do not adapt the parser to the real
  portal or access the real URL during this implementation's verification**.
  Tests may mock acquisition failures and unrecognized HTML. Availability does
  not verify source rights, selectors or dates. `raw_record` must not receive a
  `synthetic` marker; retain fixture origin in namespaces and exported reports.
- CLI example: `uv run thuringia-harvester --fixture tests/fixtures/planning_basic.html --dry-run`. Database URLs come from `DATABASE_URL` / `TEST_DATABASE_URL`; there is no `--database-url` option. Document implemented commands exactly.
- Allow fixture mode with no network. `--live` is optional and must never be default; do not silently hit inaccessible site.
- `.env.example`: `DATABASE_URL=postgresql+psycopg://...` (placeholders only), `SOURCE_URL=...`, `A4_GEOJSON_PATH=data/reference/a4_thueringen.geojson`, `STATE_GEOJSON_PATH=data/reference/thueringen_boundary.geojson`, `A4_BUFFER_METERS=10000`, request timeout/retries, optional fixture path. Config paths must work independent of current shell working directory when practical.
- For database setup, use **native Postgres.app PostgreSQL 16 / PostGIS 3.4**. `CREATE EXTENSION IF NOT EXISTS postgis; CREATE SCHEMA IF NOT EXISTS iris_staging;` before creating table. No Docker requirement. A single `sql/init.sql` can substitute for Alembic in this short prototype; explain it. Don't introduce both initialization systems unless necessary.
- README must explain the blocked assigned source, synthetic fixture nature, source-vs-approval ambiguity, the original state-clipped **A4 gap through Hessen**, how to obtain and validate **both** real OSM GeoJSON files and their provenance/ODbL attribution, state-boundary intersection and buffer assumption, model/NULL/exclusion policy, stable identity, timestamp semantics, run/test steps, database version, quality summary and realistic future live integration. Clearly distinguish real OSM road data from fictitious planning notices.
- Document any public alternative as a **potential source only** until its accessible HTML, rights, publication-date semantics and relevant signal types have been verified.

## 11. Codex working protocol

**Explicitly deferred by the candidate:** removal of conclusively excluded
existing rows and independent reference-only recalculation remain requirements,
but their implementations are deferred. Strict expected-failure regression tests
record these gaps; they must not be presented as successful acceptance checks.

1. **This is an existing, already implemented project, not a blank repository.** First inspect current code, tests, schema and both reference files; provide a **short gap analysis**, then make minimal targeted updates. Do not regenerate/restructure functioning modules just to match a conceptual tree.
2. **Two-pass development:** verify and test `planning_basic.html` end-to-end first, using both real OSM geographic references if provided, and database repeat runs. Only after that works, incrementally tackle `planning_edge_cases.html`; do not let its 32 cases delay a working baseline.
3. Keep the smallest independently testable vertical slice: fixture -> parser -> normalized objects -> dry-run JSON; then both real GeoJSON loaders/state-and-corridor checks, then DB upsert/timestamps and tests. If either geographic file is missing, spatial acceptance is unverified; continue nonspatial work only in an explicit no-spatial mode.
4. Work in small, readable changes. Run Ruff and pytest after meaningful edits. State what passed, failed, was skipped or couldn't be validated.
5. Do not commit automatically without the candidate's approval. Do not destroy or overwrite existing work. No speculative scraping, credential use, network bypass or fabricated validation success.
6. Favor exact behavior and careful error reporting over elaborate inheritance, generalized plug-in systems or premature optimization.
7. Avoid time-consuming setup tangents. If source access stays blocked, finish the offline demonstrator and document known limitations rather than weakening tests.

## 12. Acceptance review before delivery

- [ ] Required signal interpretation documented; draft vs approval treated honestly.
- [ ] Both real OSM reference files validated and reprojected: complete A4 line (including the section through Hessen) **and** Thüringen administrative polygon; provenance/ODbL/10 km assumption documented; neither missing file may silently become synthetic or imply confirmed eligibility.
- [ ] `state_status` and `corridor_status` checked separately; `accepted` requires both `inside`; records in Hessen but close to A4 excluded; uncertain locations retained for review.
- [ ] Both synthetic HTML fixtures committed and parsable offline.
- [ ] Source ID / title / publication date / source URL / location provenance preserved when present.
- [ ] EPSG:25832 point handling correct, invalid/ambiguous geometry flagged.
- [ ] `iris_staging.signal_ingest` enforces unique `(source_system,source_key)` and only `accepted`/`needs_review`; excluded identities appear in quality reports, not staging rows. Repeat/corrected/reference-only scans respect `first_seen_at`, `last_seen_at`, `content_updated_at` and missing-data rules.
- [ ] Re-run/changed-record/partial-scan/not-observed tests, failures, duplicates, pagination, empty and malformed fixtures tested.
- [ ] README, `pyproject.toml`, `.env.example`, tests, validation SQL, sample output and quality report present.
- [ ] No claims of live integration or dates that weren't actually verified; no access restrictions bypassed.
- [ ] No secrets, private datasets, unlicensed copied code, unnecessary Docker/UI/AI components.
- [ ] README and all other documentation use plain professional English with no emojis, pictograms or decorative Unicode symbols.

## 13. Documentation and presentation standards

- All documentation must use professional, concise English.
- Do not use emojis, decorative Unicode symbols, or pictograms
  in README.md or other documentation.
- Use standard Markdown headings, lists, tables, and code blocks.
- Avoid excessive comments, visual separators, and verbose explanations.
- Clearly distinguish implemented and tested functionality from
  prototype assumptions and unverified live-source behavior.
- Keep the README focused on installation, usage, architecture,
  testing, limitations, and validation results.
