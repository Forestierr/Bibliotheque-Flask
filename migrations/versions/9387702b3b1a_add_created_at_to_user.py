"""add created_at to user

Revision ID: 9387702b3b1a
Revises: 68d39397aa15
Create Date: 2026-08-16 21:03:41.413136

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9387702b3b1a'
down_revision = '68d39397aa15'
branch_labels = None
depends_on = None


def upgrade():
    # server_default permet à SQLite d'affecter une valeur aux lignes existantes
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('created_at')
