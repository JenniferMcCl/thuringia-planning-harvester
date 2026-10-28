"""Source observations and the prototype staging contract."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


@dataclass
class Observation:
    """Only present keys were supplied; None explicitly clears a supplied field."""

    values: dict[str, Any]
    flags: list[str] = field(default_factory=list)
    source_system: str = "thueringen_planning_fixture"
    synthetic: bool = True

    @property
    def source_key(self) -> str | None:
        source_id = self.values.get("source_id")
        if source_id and source_id.strip():
            return "id:" + source_id.strip()
        url = self.values.get("source_url")
        return "url:" + url if url else None


class Base(DeclarativeBase):
    pass


class SignalIngest(Base):
    __tablename__ = "signal_ingest"
    __table_args__ = (
        UniqueConstraint("source_system", "source_key", name="uq_signal_source"),
        CheckConstraint("length(source_key) > 0", name="ck_source_key"),
        CheckConstraint(
            "approval_status IN ('approved', 'not_approved', 'unknown')",
            name="ck_approval_status",
        ),
        CheckConstraint(
            "industrial_status IN ('industrial', 'non_industrial', 'unknown')",
            name="ck_industrial_status",
        ),
        CheckConstraint(
            "corridor_status IN ('inside', 'outside', 'unknown')",
            name="ck_corridor_status",
        ),
        CheckConstraint(
            "state_status IN ('inside', 'outside', 'unknown')",
            name="ck_state_status",
        ),
        CheckConstraint(
            "state_status = 'unknown' OR geom IS NOT NULL",
            name="ck_state_geometry",
        ),
        CheckConstraint(
            "screening_status IN ('accepted', 'needs_review')",
            name="ck_screening_status",
        ),
        CheckConstraint(
            "distance_to_a4_m IS NULL OR "
            "(distance_to_a4_m >= 0 AND distance_to_a4_m < 'Infinity'::float8)",
            name="ck_distance",
        ),
        CheckConstraint(
            "(corridor_status = 'unknown' AND distance_to_a4_m IS NULL) OR "
            "(corridor_status != 'unknown' AND distance_to_a4_m IS NOT NULL "
            "AND geom IS NOT NULL)",
            name="ck_corridor_geometry",
        ),
        CheckConstraint(
            "screening_status != 'accepted' OR "
            "(approval_status = 'approved' AND industrial_status = 'industrial' "
            "AND corridor_status = 'inside' AND state_status = 'inside' "
            "AND geom IS NOT NULL)",
            name="ck_accepted",
        ),
        CheckConstraint("jsonb_typeof(quality_flags) = 'array'", name="ck_flags"),
        CheckConstraint(
            "jsonb_typeof(ingest_metadata) = 'object'", name="ck_ingest_metadata"
        ),
        CheckConstraint(
            "first_seen_at <= last_seen_at AND first_seen_at <= content_updated_at",
            name="ck_chronology",
        ),
        {"schema": "iris_staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_system: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[date | None]
    publication_date_raw: Mapped[str | None] = mapped_column(Text)
    municipality: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    procedure_status: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(Text)
    industrial_status: Mapped[str] = mapped_column(Text)
    signal_type: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=25832, spatial_index=True)
    )
    distance_to_a4_m: Mapped[float | None]
    corridor_status: Mapped[str] = mapped_column(Text)
    state_status: Mapped[str] = mapped_column(Text, server_default="unknown")
    screening_status: Mapped[str] = mapped_column(Text)
    quality_flags: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    raw_record: Mapped[dict | None] = mapped_column(JSONB)
    ingest_metadata: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
