"""Client enrichment: profile/account fields + contacts + calendar.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_COLUMNS = [
    ("sector", sa.String(length=120)),
    ("industries", sa.JSON()),
    ("country", sa.String(length=80)),
    ("city", sa.String(length=120)),
    ("internal_domain", sa.String(length=300)),
    ("edr_platform", sa.String(length=120)),
    ("siem_platform", sa.String(length=120)),
    ("xdr_platform", sa.String(length=120)),
    ("other_tech", sa.Text()),
    ("dpe_name", sa.String(length=160)),
    ("dpe_email", sa.String(length=200)),
    ("pm_name", sa.String(length=160)),
    ("pm_email", sa.String(length=200)),
    ("acct_other_name", sa.String(length=160)),
    ("acct_other_role", sa.String(length=120)),
    ("acct_other_email", sa.String(length=200)),
    ("stakeholders", sa.JSON()),
    ("contracted_services", sa.JSON()),
    ("logo_path", sa.String(length=600)),
    ("contract_path", sa.String(length=600)),
    ("contract_start", sa.String(length=20)),
    ("contract_end", sa.String(length=20)),
]


def upgrade() -> None:
    for name, col_type in _TENANT_COLUMNS:
        op.add_column("tenants", sa.Column(name, col_type, nullable=True))
    op.add_column("tenants", sa.Column("is_global", sa.Boolean(), nullable=False,
                                       server_default=sa.false()))
    op.add_column("tenants", sa.Column("sla_hours", sa.Integer(), nullable=False,
                                       server_default="72"))
    op.add_column("tenants", sa.Column("hunt_maturity", sa.Integer(), nullable=False,
                                       server_default="3"))

    op.create_table(
        "client_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=60), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_client_contacts_tenant_id", "client_contacts", ["tenant_id"])

    op.create_table(
        "client_calendar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=True),
        sa.Column("event_date", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_client_calendar_tenant_id", "client_calendar", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_client_calendar_tenant_id", table_name="client_calendar")
    op.drop_table("client_calendar")
    op.drop_index("ix_client_contacts_tenant_id", table_name="client_contacts")
    op.drop_table("client_contacts")
    for name in ("hunt_maturity", "sla_hours", "is_global"):
        op.drop_column("tenants", name)
    for name, _ in reversed(_TENANT_COLUMNS):
        op.drop_column("tenants", name)
