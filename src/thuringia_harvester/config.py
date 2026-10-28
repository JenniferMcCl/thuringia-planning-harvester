"""Typed configuration; construction has no network or database side effects."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CRS = "EPSG:4326"
TARGET_CRS = "EPSG:25832"
FIXTURE_URL = "https://example.invalid/thueringen/bauleitplanung?page=1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
        validate_assignment=True,
    )

    fixture_mode: bool = True
    fixture_paths: list[Path] = Field(
        default_factory=lambda: [Path("tests/fixtures/planning_basic.html")]
    )
    fixture_base_url: str = FIXTURE_URL
    database_url: SecretStr | None = None
    test_database_url: SecretStr | None = None
    source_url: str = "https://thueringen.de/bauleitplanung"
    a4_geojson_path: Path = PROJECT_ROOT / "data/reference/a4_thueringen.geojson"
    state_geojson_path: Path = (
        PROJECT_ROOT / "data/reference/thueringen_boundary.geojson"
    )
    a4_buffer_meters: float = Field(default=10000, gt=0, allow_inf_nan=False)
    request_timeout: float = Field(default=20, gt=0, allow_inf_nan=False)
    request_retries: int = Field(default=2, ge=0, le=5)
    max_pages: int = Field(default=20, ge=1, le=100)

    def fixture_files(self) -> list[Path]:
        return [
            path if path.is_absolute() else PROJECT_ROOT / path
            for path in self.fixture_paths
        ]

    def selected_database_url(self) -> URL:
        name = "TEST_DATABASE_URL" if self.fixture_mode else "DATABASE_URL"
        value = self.test_database_url if self.fixture_mode else self.database_url
        if value is None:
            raise ValueError(f"Set {name} or use --dry-run")
        target = _database_url(value, name)
        if self.fixture_mode:
            if not target.database.endswith(("_test", "_fixture")):
                raise ValueError(
                    "TEST_DATABASE_URL database must end in _test or _fixture"
                )
            if len(target.database.encode("utf-8")) > 63:
                raise ValueError(
                    "Test database name exceeds PostgreSQL's 63-byte limit"
                )
        other = self.database_url if self.fixture_mode else self.test_database_url
        if (
            other is not None
            and target.database == _database_url(other, "other database").database
        ):
            raise ValueError("Live and test database names must be different")
        return target

    def reference_path(self) -> Path:
        path = self.a4_geojson_path
        return path if path.is_absolute() else PROJECT_ROOT / path

    def boundary_path(self) -> Path:
        path = self.state_geojson_path
        return path if path.is_absolute() else PROJECT_ROOT / path


def _database_url(value: SecretStr, name: str) -> URL:
    try:
        target = make_url(value.get_secret_value())
    except (ArgumentError, ValueError):
        raise ValueError(f"Invalid {name}") from None
    if target.drivername != "postgresql+psycopg" or not target.database:
        raise ValueError(
            f"{name} must name a PostgreSQL database using postgresql+psycopg"
        )
    return target
