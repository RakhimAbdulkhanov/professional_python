"""add student email column

Revision ID: 0002_student_email
Revises: 0001_initial
Create Date: 2026-03-01 10:05:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_student_email"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # додавання опціонального стовпця email до таблиці students
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    # видалення стовпця email зі збереженням решти даних
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.drop_column("email")
