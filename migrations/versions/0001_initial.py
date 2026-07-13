"""initial schema: users, media_events

Revision ID: 0001
Revises:
Create Date: 2026-07-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

media_status_enum = postgresql.ENUM(
    "pending", "downloaded", "uploaded", "failed", name="media_status"
)


def upgrade() -> None:
    media_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("whatsapp_phone_number", sa.String(length=32), nullable=False),
        sa.Column("drive_folder_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("whatsapp_phone_number", name="uq_users_whatsapp_phone_number"),
    )
    op.create_index("ix_users_whatsapp_phone_number", "users", ["whatsapp_phone_number"])

    op.create_table(
        "media_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("whatsapp_message_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sender_phone", sa.String(length=32), nullable=False),
        sa.Column("media_id", sa.String(length=128), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=True),
        sa.Column("status", media_status_enum, nullable=False, server_default="pending"),
        sa.Column("drive_file_id", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("whatsapp_message_id", name="uq_media_events_whatsapp_message_id"),
    )
    op.create_index("ix_media_events_whatsapp_message_id", "media_events", ["whatsapp_message_id"])
    op.create_index("ix_media_events_sender_phone", "media_events", ["sender_phone"])
    op.create_index("ix_media_events_status", "media_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_media_events_status", table_name="media_events")
    op.drop_index("ix_media_events_sender_phone", table_name="media_events")
    op.drop_index("ix_media_events_whatsapp_message_id", table_name="media_events")
    op.drop_table("media_events")

    op.drop_index("ix_users_whatsapp_phone_number", table_name="users")
    op.drop_table("users")

    media_status_enum.drop(op.get_bind(), checkfirst=True)
