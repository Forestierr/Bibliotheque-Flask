"""add renewal_reminder_sent to user

Revision ID: d1987f16b05e
Revises: 87a1c9e3b4d2
Create Date: 2026-11-24 10:18:36.167401

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d1987f16b05e"
down_revision = "87a1c9e3b4d2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "renewal_reminder_sent",
                sa.Boolean(),
                server_default="0",
                nullable=False,
            )
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("renewal_reminder_sent")
