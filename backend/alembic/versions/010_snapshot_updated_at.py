"""Add missing updated_at columns for TimestampMixin tables."""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

_TABLES = (
    "net_worth_snapshot",
    "advisor_action_log",
    "advisor_chat_message",
    "card_payment_mapping",
)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    for table in _TABLES:
        if _has_column(table, "updated_at"):
            continue
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("(CURRENT_TIMESTAMP)"),
                    nullable=False,
                )
            )


def downgrade() -> None:
    for table in reversed(_TABLES):
        if not _has_column(table, "updated_at"):
            continue
        with op.batch_alter_table(table) as batch:
            batch.drop_column("updated_at")
