from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from service_orchestrator.shared.infrastructure.database import Base


class ServiceModel(Base):
    __tablename__ = "services"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, server_default="")
    current_version_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["current_version_id", "id"],
            ["service_versions.id", "service_versions.service_id"],
            name="fk_services_current_version",
            use_alter=True,
        ),
    )


class ServiceVersionModel(Base):
    __tablename__ = "service_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    service_id: Mapped[UUID] = mapped_column(ForeignKey("services.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("service_id", "version"),
        UniqueConstraint("id", "service_id"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("status IN ('draft', 'published')", name="status_valid"),
        CheckConstraint(
            "(status = 'published') = (published_at IS NOT NULL)", name="published_at_matches"
        ),
        Index(
            "uq_service_versions_one_draft",
            "service_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )
