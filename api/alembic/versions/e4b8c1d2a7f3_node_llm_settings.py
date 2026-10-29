"""replace llm_temperature with per-node llm_node_settings

Revision ID: e4b8c1d2a7f3
Revises: d7e2a9c41f60
Create Date: 2026-10-28

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'e4b8c1d2a7f3'
down_revision: Union[str, None] = 'd7e2a9c41f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c["name"] for c in inspector.get_columns("settings")]
    if "llm_node_settings" not in existing_cols:
        op.add_column(
            "settings",
            sa.Column("llm_node_settings", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
    if "llm_temperature" in existing_cols:
        op.drop_column("settings", "llm_temperature")
    op.alter_column("settings", "llm_model", server_default="anthropic/claude-sonnet-5.5")


def downgrade() -> None:
    op.alter_column("settings", "llm_model", server_default="anthropic/claude-sonnet-4-5")
    op.add_column("settings", sa.Column("llm_temperature", sa.Float(), nullable=False, server_default="0.7"))
    op.drop_column("settings", "llm_node_settings")
