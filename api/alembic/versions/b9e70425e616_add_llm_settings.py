"""add_llm_settings

Revision ID: b9e70425e616
Revises: 22ddf89ce690
Create Date: 2026-06-02 20:13:23.737727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9e70425e616'
down_revision: Union[str, Sequence[str], None] = '22ddf89ce690'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c["name"] for c in inspector.get_columns("settings")]
    if "llm_temperature" not in existing_cols:
        op.add_column("settings", sa.Column("llm_temperature", sa.Float(), nullable=False, server_default="0.7"))
    if "llm_model" not in existing_cols:
        op.add_column("settings", sa.Column("llm_model", sa.Text(), nullable=False, server_default="anthropic/claude-sonnet-4-5"))


def downgrade() -> None:
    op.drop_column("settings", "llm_model")
    op.drop_column("settings", "llm_temperature")
