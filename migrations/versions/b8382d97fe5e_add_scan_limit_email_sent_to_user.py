"""add scan_limit_email_sent to user

Revision ID: b8382d97fe5e
Revises: 5be92aaad777
Create Date: 2026-11-23 16:51:38.435141

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b8382d97fe5e"
down_revision = "5be92aaad777"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "scan_limit_email_sent",
                sa.Boolean(),
                server_default="0",
                nullable=False,
            )
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("scan_limit_email_sent")
