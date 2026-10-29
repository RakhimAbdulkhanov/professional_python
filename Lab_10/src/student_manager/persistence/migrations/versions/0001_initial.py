"""initial groups and students schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-01 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # створення початкових таблиць groups та students без колонки email
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="check_group_name_nonempty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_groups_name"), "groups", ["name"], unique=True)

    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("average_grade", sa.Float(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "average_grade >= 0.0 AND average_grade <= 100.0",
            name="check_student_average_grade_range",
        ),
        sa.CheckConstraint(
            "length(trim(first_name)) > 0",
            name="check_student_first_name_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(last_name)) > 0",
            name="check_student_last_name_nonempty",
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_students_first_name"), "students", ["first_name"], unique=False
    )
    op.create_index(
        op.f("ix_students_group_id"), "students", ["group_id"], unique=False
    )
    op.create_index(
        op.f("ix_students_last_name"), "students", ["last_name"], unique=False
    )


def downgrade() -> None:
    # повне видалення таблиць у зворотному порядку
    op.drop_index(op.f("ix_students_last_name"), table_name="students")
    op.drop_index(op.f("ix_students_group_id"), table_name="students")
    op.drop_index(op.f("ix_students_first_name"), table_name="students")
    op.drop_table("students")
    op.drop_index(op.f("ix_groups_name"), table_name="groups")
    op.drop_table("groups")
