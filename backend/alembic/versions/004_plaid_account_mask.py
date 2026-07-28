"""Add mask and balance to plaid_account for mapping disambiguation."""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plaid_account", sa.Column("mask", sa.String(8), nullable=True))
    op.add_column(
        "plaid_account",
        sa.Column("balance_current", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plaid_account", "balance_current")
    op.drop_column("plaid_account", "mask")
