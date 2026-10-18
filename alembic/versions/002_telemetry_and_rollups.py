"""telemetry usage records and hourly rollups schema

Revision ID: 002_telemetry_and_rollups
Revises: 001_initial_schema
Create Date: 2026-10-19 03:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_telemetry_and_rollups"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create usage_records table
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("key_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usage_records_request_id"), "usage_records", ["request_id"], unique=False)
    op.create_index(op.f("ix_usage_records_key_id"), "usage_records", ["key_id"], unique=False)
    op.create_index(op.f("ix_usage_records_user_id"), "usage_records", ["user_id"], unique=False)
    op.create_index(op.f("ix_usage_records_status_code"), "usage_records", ["status_code"], unique=False)
    op.create_index(op.f("ix_usage_records_timestamp"), "usage_records", ["timestamp"], unique=False)
    op.create_index("ix_usage_records_key_timestamp", "usage_records", ["key_id", "timestamp"], unique=False)
    op.create_index("ix_usage_records_user_timestamp", "usage_records", ["user_id", "timestamp"], unique=False)
    op.create_index("ix_usage_records_status_timestamp", "usage_records", ["status_code", "timestamp"], unique=False)

    # 2. Create hourly_usage_rollups table
    op.create_table(
        "hourly_usage_rollups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), nullable=False),
        sa.Column("bucket_hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("client_error_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rate_limited_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("server_error_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_latency_ms", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("p95_latency_ms", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("p99_latency_ms", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id", "bucket_hour", name="uq_hourly_rollup_key_hour"),
    )
    op.create_index(op.f("ix_hourly_usage_rollups_key_id"), "hourly_usage_rollups", ["key_id"], unique=False)
    op.create_index(op.f("ix_hourly_usage_rollups_bucket_hour"), "hourly_usage_rollups", ["bucket_hour"], unique=False)
    op.create_index("ix_hourly_rollup_key_hour", "hourly_usage_rollups", ["key_id", "bucket_hour"], unique=False)


def downgrade() -> None:
    # 1. Drop hourly_usage_rollups
    op.drop_index("ix_hourly_rollup_key_hour", table_name="hourly_usage_rollups")
    op.drop_index(op.f("ix_hourly_usage_rollups_bucket_hour"), table_name="hourly_usage_rollups")
    op.drop_index(op.f("ix_hourly_usage_rollups_key_id"), table_name="hourly_usage_rollups")
    op.drop_table("hourly_usage_rollups")

    # 2. Drop usage_records
    op.drop_index("ix_usage_records_status_timestamp", table_name="usage_records")
    op.drop_index("ix_usage_records_user_timestamp", table_name="usage_records")
    op.drop_index("ix_usage_records_key_timestamp", table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_timestamp"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_status_code"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_user_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_key_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_request_id"), table_name="usage_records")
    op.drop_table("usage_records")
