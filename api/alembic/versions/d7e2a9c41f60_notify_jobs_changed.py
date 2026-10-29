"""notify jobs_changed on job insert/delete/status change

Revision ID: d7e2a9c41f60
Revises: c3f1a2b4d8e5
Create Date: 2026-10-22

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'd7e2a9c41f60'
down_revision: Union[str, None] = 'c3f1a2b4d8e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQL is inlined (not imported from api.models) so this migration stays
    # frozen even if the model-side definition changes later.
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_jobs_changed() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('jobs_changed', '');
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER jobs_changed_notify
        AFTER INSERT OR DELETE OR UPDATE OF status, current_node ON jobs
        FOR EACH ROW EXECUTE FUNCTION notify_jobs_changed()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS jobs_changed_notify ON jobs")
    op.execute("DROP FUNCTION IF EXISTS notify_jobs_changed()")
