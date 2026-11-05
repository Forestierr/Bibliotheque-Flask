"""add academic year archive and student soft delete

Revision ID: f68b297bc5dd
Revises: ce07d1a76a04
Create Date: 2026-11-05 09:56:42.452934

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f68b297bc5dd'
down_revision = 'ce07d1a76a04'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "academic_year_archive" not in tables:
        op.create_table(
            "academic_year_archive",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("year_label", sa.String(length=50), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=False),
            sa.Column("total_students", sa.Integer(), nullable=False),
            sa.Column("total_loans", sa.Integer(), nullable=False),
            sa.Column("average_loans_per_student", sa.Float(), nullable=False),
            sa.Column("most_read_book_title", sa.String(length=255), nullable=True),
            sa.Column("most_read_book_author", sa.String(length=255), nullable=True),
            sa.Column("most_read_book_count", sa.Integer(), nullable=False),
            sa.Column("top_reader_name", sa.String(length=255), nullable=True),
            sa.Column("top_reader_count", sa.Integer(), nullable=False),
            sa.Column("top_books_json", sa.Text(), nullable=True),
            sa.Column("top_readers_json", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    with op.batch_alter_table("loan", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notes", sa.String(length=255), nullable=True))

    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_archived", sa.Boolean(), server_default="0", nullable=False
            )
        )
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("archived_year_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_student_is_archived"), ["is_archived"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_student_academic_year_archive",
            "academic_year_archive",
            ["archived_year_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.drop_constraint("fk_student_academic_year_archive", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_student_is_archived"))
        batch_op.drop_column("archived_year_id")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("is_archived")

    with op.batch_alter_table("loan", schema=None) as batch_op:
        batch_op.drop_column("notes")

    op.drop_table("academic_year_archive")
