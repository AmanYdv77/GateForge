"""add allowed_ips to api_keys

Revision ID: 003_api_keys_allowed_ips
Revises: 002_telemetry_and_rollups
Create Date: 2026-10-23 23:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_api_keys_allowed_ips"
down_revision: str | None = "002_telemetry_and_rollups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("allowed_ips", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "allowed_ips")
