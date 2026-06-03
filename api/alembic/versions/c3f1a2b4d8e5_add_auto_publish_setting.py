"""add auto_publish_to_ghost setting

Revision ID: c3f1a2b4d8e5
Revises: b9e70425e616
Create Date: 2026-06-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3f1a2b4d8e5'
down_revision: Union[str, None] = '899b0edc74e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c["name"] for c in inspector.get_columns("settings")]
    if "auto_publish_to_ghost" not in existing_cols:
        op.add_column(
            "settings",
            sa.Column("auto_publish_to_ghost", sa.Boolean(), nullable=False, server_default="true"),
        )


def downgrade() -> None:
    op.drop_column("settings", "auto_publish_to_ghost")
