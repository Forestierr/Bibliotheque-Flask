"""add admin_note to feedback

Revision ID: c317cbfa328d
Revises: 0bfc4975d730
Create Date: 2026-11-13 20:41:04.885936

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c317cbfa328d"
down_revision = "0bfc4975d730"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("feedback", schema=None) as batch_op:
        batch_op.add_column(sa.Column("admin_note", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("feedback", schema=None) as batch_op:
        batch_op.drop_column("admin_note")
