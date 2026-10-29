"""add session_notes to jobs

Revision ID: e4b8c2d1a9f3
Revises: e4b8c1d2a7f3
Create Date: 2026-10-28

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e4b8c2d1a9f3'
down_revision: Union[str, None] = 'e4b8c1d2a7f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable session_notes column to jobs."""
    op.add_column('jobs', sa.Column('session_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the session_notes column from jobs."""
    op.drop_column('jobs', 'session_notes')
