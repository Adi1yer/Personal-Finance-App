"""Register ledger: tracking dates, investment fields, category rules, plaid cursor."""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

TRACKING_START = "2026-01-01"


def upgrade() -> None:
    op.add_column("account", sa.Column("tracking_start_date", sa.Date(), nullable=True))
    op.add_column(
        "transaction",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("transaction", sa.Column("investment_type", sa.String(32), nullable=True))
    op.add_column("transaction", sa.Column("investment_subtype", sa.String(64), nullable=True))
    op.add_column("transaction", sa.Column("security_name", sa.String(256), nullable=True))
    op.add_column("transaction", sa.Column("quantity", sa.Numeric(18, 6), nullable=True))
    op.add_column("transaction", sa.Column("price", sa.Numeric(18, 4), nullable=True))
    op.add_column("plaid_item", sa.Column("transactions_cursor", sa.Text(), nullable=True))
    op.add_column(
        "plaid_item",
        sa.Column("last_investment_sync_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "category_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_field", sa.String(16), nullable=False),
        sa.Column("pattern", sa.String(256), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Default tracking start for cash/credit/401k/HSA accounts
    op.execute(
        f"""
        UPDATE account
        SET tracking_start_date = '{TRACKING_START}'
        WHERE subtype IN ('checking', 'credit_card', 'retirement', 'hsa')
        """
    )


def downgrade() -> None:
    op.drop_table("category_rule")
    op.drop_column("plaid_item", "last_investment_sync_at")
    op.drop_column("plaid_item", "transactions_cursor")
    op.drop_column("transaction", "price")
    op.drop_column("transaction", "quantity")
    op.drop_column("transaction", "security_name")
    op.drop_column("transaction", "investment_subtype")
    op.drop_column("transaction", "investment_type")
    op.drop_column("transaction", "voided_at")
    op.drop_column("account", "tracking_start_date")
