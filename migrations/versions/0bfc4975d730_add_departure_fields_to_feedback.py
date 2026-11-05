"""add_departure_fields_to_feedback

Revision ID: 0bfc4975d730
Revises: f68b297bc5dd
Create Date: 2026-11-05 12:45:32.051734

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0bfc4975d730'
down_revision = 'f68b297bc5dd'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.add_column(sa.Column('author_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('author_email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('departure_reason', sa.String(length=50), nullable=True))
        batch_op.alter_column('user_id',
               existing_type=sa.INTEGER(),
               nullable=True)


def downgrade():
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.alter_column('user_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.drop_column('departure_reason')
        batch_op.drop_column('author_email')
        batch_op.drop_column('author_name')
