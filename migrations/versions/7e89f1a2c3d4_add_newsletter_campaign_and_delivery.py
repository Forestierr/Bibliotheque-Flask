"""add newsletter campaign and delivery

Revision ID: 7e89f1a2c3d4
Revises: 4b5a2f1c8e90
Create Date: 2026-09-04 22:27:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7e89f1a2c3d4"
down_revision = "4b5a2f1c8e90"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "newsletter_campaign" not in tables:
        op.create_table(
            "newsletter_campaign",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("template", sa.String(length=100), nullable=False),
            sa.Column("target", sa.String(length=50), nullable=False),
            sa.Column(
                "total_recipients", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "newsletter_delivery" not in tables:
        op.create_table(
            "newsletter_delivery",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("campaign_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("tracking_token", sa.String(length=64), nullable=False),
            sa.Column(
                "status", sa.String(length=30), nullable=False, server_default="pending"
            ),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(
                ["campaign_id"],
                ["newsletter_campaign.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["user.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_newsletter_delivery_tracking_token"),
            "newsletter_delivery",
            ["tracking_token"],
            unique=True,
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "newsletter_delivery" in tables:
        op.drop_index(
            op.f("ix_newsletter_delivery_tracking_token"),
            table_name="newsletter_delivery",
        )
        op.drop_table("newsletter_delivery")

    if "newsletter_campaign" in tables:
        op.drop_table("newsletter_campaign")
