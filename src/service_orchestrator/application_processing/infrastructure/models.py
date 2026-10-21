from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from service_orchestrator.shared.infrastructure.database import Base


class ApplicationModel(Base):
    __tablename__ = "applications"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    service_version_id: Mapped[UUID] = mapped_column(ForeignKey("service_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fee_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'submitted')", name="status_valid"),
        CheckConstraint(
            "(status = 'submitted') = (submitted_at IS NOT NULL AND fee_snapshot IS NOT NULL)",
            name="submission_complete",
        ),
    )


class ApplicationEventModel(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"))
    event_type: Mapped[str] = mapped_column(String(64))
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index(None, "application_id", "id"),)
