"""add_school_invoice_and_user_invoice_fields

Revision ID: 87a1c9e3b4d2
Revises: 0bfc4975d730
Create Date: 2026-11-12 11:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "87a1c9e3b4d2"
down_revision = "0efcc1dfde7a"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Ajout des colonnes de suivi de facture sur la table user
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("stripe_latest_invoice_id", sa.String(length=120), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stripe_latest_invoice_pdf", sa.String(length=500), nullable=True)
        )

    # 2. Création de la table school_invoice pour le suivi des factures école (Flux B)
    op.create_table(
        "school_invoice",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("stripe_invoice_id", sa.String(length=120), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=120), nullable=False),
        sa.Column("school_name", sa.String(length=255), nullable=False),
        sa.Column("school_address", sa.Text(), nullable=False),
        sa.Column("school_billing_email", sa.String(length=120), nullable=False),
        sa.Column("siret_or_tax_id", sa.String(length=50), nullable=True),
        sa.Column("order_reference", sa.String(length=100), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="eur"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("hosted_invoice_url", sa.String(length=500), nullable=True),
        sa.Column("invoice_pdf_url", sa.String(length=500), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("school_invoice", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_school_invoice_stripe_invoice_id"),
            ["stripe_invoice_id"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_school_invoice_user_id"),
            ["user_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("school_invoice", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_school_invoice_user_id"))
        batch_op.drop_index(batch_op.f("ix_school_invoice_stripe_invoice_id"))
    op.drop_table("school_invoice")

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("stripe_latest_invoice_pdf")
        batch_op.drop_column("stripe_latest_invoice_id")
