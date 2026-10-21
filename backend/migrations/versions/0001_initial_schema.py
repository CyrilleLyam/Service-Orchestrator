from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)

GUARDS = """
CREATE FUNCTION guard_published_service_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'published' THEN
        RAISE EXCEPTION 'service version % is published and immutable', OLD.id;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER service_versions_published_immutable
BEFORE UPDATE OR DELETE ON service_versions
FOR EACH ROW EXECUTE FUNCTION guard_published_service_version();

CREATE FUNCTION guard_application() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'submitted' THEN
        RAISE EXCEPTION 'application % is submitted and cannot change', OLD.id;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF NEW.service_version_id IS DISTINCT FROM OLD.service_version_id THEN
        RAISE EXCEPTION 'application % cannot change its pinned service version', OLD.id;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER applications_guard
BEFORE UPDATE OR DELETE ON applications
FOR EACH ROW EXECUTE FUNCTION guard_application();

CREATE FUNCTION reject_event_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'application_events is append-only';
END $$;

CREATE TRIGGER application_events_append_only
BEFORE UPDATE OR DELETE ON application_events
FOR EACH ROW EXECUTE FUNCTION reject_event_change();
"""


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_services"),
        sa.UniqueConstraint("code", name="uq_services_code"),
    )
    op.create_table(
        "service_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.Column("published_at", TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_service_versions"),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name="fk_service_versions_service_id"
        ),
        sa.UniqueConstraint("service_id", "version", name="uq_service_versions_service_id_version"),
        sa.UniqueConstraint("id", "service_id", name="uq_service_versions_id_service_id"),
        sa.CheckConstraint("version > 0", name="ck_service_versions_version_positive"),
        sa.CheckConstraint(
            "status IN ('draft', 'published')", name="ck_service_versions_status_valid"
        ),
        sa.CheckConstraint(
            "(status = 'published') = (published_at IS NOT NULL)",
            name="ck_service_versions_published_at_matches",
        ),
    )
    op.create_index(
        "uq_service_versions_one_draft",
        "service_versions",
        ["service_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_foreign_key(
        "fk_services_current_version",
        "services",
        "service_versions",
        ["current_version_id", "id"],
        ["id", "service_id"],
    )

    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("fee_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.Column("submitted_at", TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_applications"),
        sa.ForeignKeyConstraint(
            ["service_version_id"],
            ["service_versions.id"],
            name="fk_applications_service_version_id",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_applications_idempotency_key"),
        sa.CheckConstraint("status IN ('draft', 'submitted')", name="ck_applications_status_valid"),
        sa.CheckConstraint(
            "(status = 'submitted') = (submitted_at IS NOT NULL AND fee_snapshot IS NOT NULL)",
            name="ck_applications_submission_complete",
        ),
    )
    op.create_index("ix_applications_service_version_id", "applications", ["service_version_id"])

    op.create_table(
        "application_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_application_events"),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_application_events_application_id",
        ),
    )
    op.create_index(
        "ix_application_events_application_id_id",
        "application_events",
        ["application_id", "id"],
    )

    op.execute(GUARDS)


def downgrade() -> None:
    op.drop_table("application_events")
    op.drop_table("applications")
    op.drop_constraint("fk_services_current_version", "services", type_="foreignkey")
    op.drop_table("service_versions")
    op.drop_table("services")
    op.execute(
        "DROP FUNCTION reject_event_change(); "
        "DROP FUNCTION guard_application(); "
        "DROP FUNCTION guard_published_service_version();"
    )
