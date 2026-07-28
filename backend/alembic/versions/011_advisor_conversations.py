"""Advisor conversations for ChatGPT-style multi-chat history."""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advisor_conversation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False, server_default="New chat"),
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
    )
    with op.batch_alter_table("advisor_chat_message") as batch:
        batch.add_column(sa.Column("conversation_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_advisor_chat_message_conversation",
            "advisor_conversation",
            ["conversation_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_advisor_chat_message_conversation_id", ["conversation_id"])

    # Move any existing messages into a single legacy conversation.
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT COUNT(*) FROM advisor_chat_message")).scalar() or 0
    if count:
        conn.execute(
            sa.text(
                "INSERT INTO advisor_conversation (title) VALUES ('Previous chat')"
            )
        )
        conv_id = conn.execute(sa.text("SELECT id FROM advisor_conversation ORDER BY id DESC LIMIT 1")).scalar()
        conn.execute(
            sa.text("UPDATE advisor_chat_message SET conversation_id = :cid"),
            {"cid": conv_id},
        )
        # Drop empty assistant stubs from the tools bug.
        conn.execute(
            sa.text(
                "DELETE FROM advisor_chat_message WHERE role = 'assistant' AND (content IS NULL OR content = '')"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("advisor_chat_message") as batch:
        batch.drop_index("ix_advisor_chat_message_conversation_id")
        batch.drop_constraint("fk_advisor_chat_message_conversation", type_="foreignkey")
        batch.drop_column("conversation_id")
    op.drop_table("advisor_conversation")
