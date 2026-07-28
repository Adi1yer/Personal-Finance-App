"""Plaid investments metadata and holdings sync timestamp

Revision ID: 003
Revises: 002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("plaid_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_holdings_sync_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("plaid_account", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plaid_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("plaid_subtype", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("plaid_account", schema=None) as batch_op:
        batch_op.drop_column("plaid_subtype")
        batch_op.drop_column("plaid_type")

    with op.batch_alter_table("plaid_item", schema=None) as batch_op:
        batch_op.drop_column("last_holdings_sync_at")
