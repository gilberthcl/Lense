"""Module config store + hunt session fields (language, EDR, SIEM, brief).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "module_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module", sa.String(length=60), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("module", "key", name="uq_module_config_key"),
    )
    op.create_index("ix_module_config_module", "module_config", ["module"])

    op.add_column(
        "hunts",
        sa.Column("report_language", sa.String(length=40), nullable=False,
                  server_default="English"),
    )
    op.add_column("hunts", sa.Column("edr", sa.String(length=120), nullable=True))
    op.add_column("hunts", sa.Column("siem", sa.String(length=120), nullable=True))
    op.add_column("hunts", sa.Column("methodology_brief", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("hunts", "methodology_brief")
    op.drop_column("hunts", "siem")
    op.drop_column("hunts", "edr")
    op.drop_column("hunts", "report_language")
    op.drop_index("ix_module_config_module", table_name="module_config")
    op.drop_table("module_config")
