"""Add amount_direction to category_rule."""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "category_rule",
        sa.Column("amount_direction", sa.String(8), nullable=False, server_default="any"),
    )


def downgrade() -> None:
    op.drop_column("category_rule", "amount_direction")
