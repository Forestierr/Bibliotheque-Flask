"""add is_test to user and created_at to book and student

Revision ID: 5be92aaad777
Revises: c317cbfa328d
Create Date: 2026-11-13 20:56:30.262776

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "5be92aaad777"
down_revision = "c317cbfa328d"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("book", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_test", sa.Boolean(), server_default="0", nullable=False)
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("is_test")

    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.drop_column("created_at")

    with op.batch_alter_table("book", schema=None) as batch_op:
        batch_op.drop_column("created_at")
