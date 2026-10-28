from datetime import UTC, datetime
from pathlib import Path

import pytest
from shapely.geometry import LineString, box

from thuringia_harvester.config import FIXTURE_URL, PROJECT_ROOT
from thuringia_harvester.parser import parse_page
from thuringia_harvester.transform import (
    Corridor,
    StateBoundary,
    load_corridor,
    load_state_boundary,
    project_location,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def basic():
    return parse_page((FIXTURES / "planning_basic.html").read_text(), FIXTURE_URL)


@pytest.fixture
def scan_time():
    return datetime(2026, 10, 27, 12, tzinfo=UTC)


@pytest.fixture
def projected_test_corridor():
    # Explicitly synthetic test road; never written to data/reference or used by CLI.
    points = [
        project_location({"crs": "EPSG:4326", "lat": lat, "lon": lon})[0]
        for lon, lat in (
            ("10.704", "50.946"),
            ("11.037", "50.955"),
            ("11.59", "50.923"),
        )
    ]
    return Corridor(LineString(points), {"synthetic_test_road": True})


@pytest.fixture
def projected_test_boundary():
    return StateBoundary(
        box(550000, 5500000, 800000, 5800000), {"synthetic_test_state": True}
    )


@pytest.fixture(scope="session")
def real_boundary():
    path = PROJECT_ROOT / "data/reference/thueringen_boundary.geojson"
    if not path.exists():
        pytest.skip("Real state boundary is not supplied")
    return load_state_boundary(path)


@pytest.fixture(scope="session")
def real_corridor():
    path = PROJECT_ROOT / "data/reference/a4_thueringen.geojson"
    if not path.exists():
        pytest.skip("Real A4 GeoJSON is not supplied")
    return load_corridor(path)
