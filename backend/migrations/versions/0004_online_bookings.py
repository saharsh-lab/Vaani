"""Online bookings: patients book from the business's public page.

bookings.source gains 'online', so those bookings show apart from the ones
Vaani made on calls and chats.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE bookings DROP CONSTRAINT bookings_source_check;
        ALTER TABLE bookings ADD CONSTRAINT bookings_source_check
          CHECK (source IN ('voice', 'whatsapp', 'web_chat', 'dashboard', 'online'));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE bookings SET source = 'dashboard' WHERE source = 'online';
        ALTER TABLE bookings DROP CONSTRAINT bookings_source_check;
        ALTER TABLE bookings ADD CONSTRAINT bookings_source_check
          CHECK (source IN ('voice', 'whatsapp', 'web_chat', 'dashboard'));
        """
    )
