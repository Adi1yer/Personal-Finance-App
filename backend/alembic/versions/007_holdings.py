"""Holdings table for per-security investment positions."""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("security_name", sa.String(256), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("cost_basis_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("market_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "ticker", name="uq_holding_account_ticker"),
    )
    op.create_index("ix_holding_account_id", "holding", ["account_id"])


def downgrade() -> None:
    op.drop_table("holding")
