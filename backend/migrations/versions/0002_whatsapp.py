"""WhatsApp channel: route numbers to businesses, resumable conversations, dedupe.

- businesses.whatsapp_phone_number_id: Meta's id for the number customers message;
  the webhook uses it to find the business.
- conversations.last_activity_at / agent_state: WhatsApp messages arrive one
  webhook at a time, so the agent's history is saved after each turn and
  restored on the next message. After a gap a new conversation starts.
- channel_events: ids of inbound messages already accepted, so a redelivered
  webhook is processed once.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE businesses ADD COLUMN whatsapp_phone_number_id text UNIQUE;

        ALTER TABLE conversations
          ADD COLUMN last_activity_at timestamptz NOT NULL DEFAULT now(),
          ADD COLUMN agent_state jsonb;
        CREATE INDEX conversations_open_idx ON conversations (business_id, customer_id, channel)
          WHERE ended_at IS NULL;

        CREATE TABLE channel_events (
          business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
          channel     text NOT NULL,
          external_id text NOT NULL,
          received_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (business_id, channel, external_id)
        );
        ALTER TABLE channel_events ENABLE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON channel_events
          USING (business_id = app_current_business())
          WITH CHECK (business_id = app_current_business());
        GRANT SELECT, INSERT, DELETE ON channel_events TO vaani_app;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE channel_events;
        DROP INDEX conversations_open_idx;
        ALTER TABLE conversations DROP COLUMN agent_state, DROP COLUMN last_activity_at;
        ALTER TABLE businesses DROP COLUMN whatsapp_phone_number_id;
        """
    )
