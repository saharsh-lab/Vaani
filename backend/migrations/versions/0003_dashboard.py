"""Dashboard: logins for owners and staff, and a handoff workflow.

- users: name, password hash (scrypt), active flag, last login.
- conversations: handoff_status (open -> claimed -> resolved), who claimed it,
  and the note left when resolving, so staff can work a callback queue.
- bookings.customer_name: the patient's name for that booking, which can differ
  from the caller's (booking for a family member).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN name text,
          ADD COLUMN password_hash text,
          ADD COLUMN active boolean NOT NULL DEFAULT true,
          ADD COLUMN last_login_at timestamptz,
          ADD CONSTRAINT users_business_id_id_key UNIQUE (business_id, id);

        ALTER TABLE conversations
          ADD COLUMN handoff_status text
            CHECK (handoff_status IN ('open', 'claimed', 'resolved')),
          ADD COLUMN handoff_assignee_id uuid,
          ADD COLUMN handoff_note text,
          ADD COLUMN handoff_updated_at timestamptz,
          ADD FOREIGN KEY (business_id, handoff_assignee_id) REFERENCES users (business_id, id)
            ON DELETE SET NULL (handoff_assignee_id);
        UPDATE conversations SET handoff_status = 'open' WHERE handoff;

        -- The patient's name per booking (a caller may book for a family member).
        ALTER TABLE bookings ADD COLUMN customer_name text;
        UPDATE bookings SET customer_name = substring(notes FROM '^Booked for (.*)$'), notes = NULL
          WHERE notes LIKE 'Booked for %';
        CREATE INDEX conversations_handoff_idx ON conversations (business_id, handoff_status)
          WHERE handoff;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE bookings DROP COLUMN customer_name;
        DROP INDEX conversations_handoff_idx;
        ALTER TABLE conversations
          DROP COLUMN handoff_updated_at, DROP COLUMN handoff_note,
          DROP COLUMN handoff_assignee_id, DROP COLUMN handoff_status;
        ALTER TABLE users
          DROP CONSTRAINT users_business_id_id_key,
          DROP COLUMN last_login_at, DROP COLUMN active,
          DROP COLUMN password_hash, DROP COLUMN name;
        """
    )
