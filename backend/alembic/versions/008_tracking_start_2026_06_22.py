"""Set tracking_start_date to 2026-06-22 for all accounts."""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE account SET tracking_start_date = '2026-06-22' "
        "WHERE slug NOT IN ('uncategorized_expense', 'salary_income', 'other_income', 'opening_equity')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE account SET tracking_start_date = '2026-01-01' "
        "WHERE subtype IN ('checking', 'credit_card', 'retirement', 'hsa') "
        "AND slug NOT IN ('uncategorized_expense', 'salary_income', 'other_income', 'opening_equity')"
    )
    op.execute(
        "UPDATE account SET tracking_start_date = NULL "
        "WHERE subtype = 'brokerage' "
        "AND slug NOT IN ('uncategorized_expense', 'salary_income', 'other_income', 'opening_equity')"
    )
