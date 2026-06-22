"""Methodology structured sections + job log/model.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hunts", sa.Column("methodology_sections", sa.JSON(), nullable=True))
    op.add_column("analysis_jobs", sa.Column("model", sa.String(length=120), nullable=True))
    op.add_column("analysis_jobs", sa.Column("log", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_jobs", "log")
    op.drop_column("analysis_jobs", "model")
    op.drop_column("hunts", "methodology_sections")
