"""Initial schema: tenants, scheduling, bookings, knowledge base, conversations.

Three rules hold across the whole schema:

1. Every tenant table has business_id, and row-level security limits the
   vaani_app role to rows where business_id = app_current_business().
2. Child rows reference parents through composite (business_id, id) foreign keys,
   so a booking can't point at another business's service, staff or customer,
   even if the application has a bug.
3. bookings_no_overlap makes double-booking a staff member impossible at the
   database level, including under concurrent requests.

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "users",
    "services",
    "staff",
    "staff_services",
    "working_hours",
    "blocked_slots",
    "customers",
    "conversations",
    "bookings",
    "kb_documents",
    "kb_chunks",
    "messages",
]

UPGRADE_SQL = """
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS vector;

-- The tenant for the current transaction, set by the API with
-- set_config('app.business_id', ..., true). NULLIF guards against the empty
-- string a pooled connection keeps after a transaction-local setting ends.
CREATE FUNCTION app_current_business() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.business_id', true), '')::uuid
$$;

CREATE TABLE businesses (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{2,39}$'),
  name        text NOT NULL,
  type        text NOT NULL,
  timezone    text NOT NULL DEFAULT 'Asia/Kolkata',
  languages   text[] NOT NULL DEFAULT '{en}',
  greeting    text,
  agent_voice text,
  plan        text NOT NULL DEFAULT 'free',
  phone       text,
  address     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  email       text NOT NULL UNIQUE,
  role        text NOT NULL CHECK (role IN ('owner', 'staff')),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE services (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id  uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  name         text NOT NULL,
  description  text,
  duration_min integer NOT NULL CHECK (duration_min BETWEEN 5 AND 480),
  price_inr    numeric(10, 2) CHECK (price_inr >= 0),
  active       boolean NOT NULL DEFAULT true,
  UNIQUE (business_id, id),
  UNIQUE (business_id, name)
);

CREATE TABLE staff (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  name        text NOT NULL,
  active      boolean NOT NULL DEFAULT true,
  UNIQUE (business_id, id)
);

-- Which staff can perform which service (a join table rather than an array,
-- so every link is checked by a foreign key).
CREATE TABLE staff_services (
  business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  staff_id    uuid NOT NULL,
  service_id  uuid NOT NULL,
  PRIMARY KEY (staff_id, service_id),
  FOREIGN KEY (business_id, staff_id) REFERENCES staff (business_id, id) ON DELETE CASCADE,
  FOREIGN KEY (business_id, service_id) REFERENCES services (business_id, id) ON DELETE CASCADE
);

-- staff_id NULL = the business's default hours. A staff member with any rows of
-- their own uses only those (a weekday with no row is their day off).
CREATE TABLE working_hours (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  staff_id    uuid,
  weekday     smallint NOT NULL CHECK (weekday BETWEEN 0 AND 6),  -- 0 = Monday
  open_time   time NOT NULL,
  close_time  time NOT NULL,
  CHECK (close_time > open_time),
  FOREIGN KEY (business_id, staff_id) REFERENCES staff (business_id, id) ON DELETE CASCADE
);

-- staff_id NULL = the whole business is closed (holiday).
CREATE TABLE blocked_slots (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  staff_id    uuid,
  start_at    timestamptz NOT NULL,
  end_at      timestamptz NOT NULL,
  reason      text,
  CHECK (end_at > start_at),
  FOREIGN KEY (business_id, staff_id) REFERENCES staff (business_id, id) ON DELETE CASCADE
);

CREATE TABLE customers (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id        uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  name               text,
  phone              text NOT NULL,
  preferred_language text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (business_id, id),
  UNIQUE (business_id, phone)
);

CREATE TABLE conversations (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id       uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  customer_id       uuid,
  channel           text NOT NULL CHECK (channel IN ('voice', 'whatsapp', 'web_chat')),
  language          text,
  started_at        timestamptz NOT NULL DEFAULT now(),
  ended_at          timestamptz,
  duration_s        integer,
  outcome           text,
  handoff           boolean NOT NULL DEFAULT false,
  handoff_reason    text,
  summary           text,
  llm_input_tokens  integer NOT NULL DEFAULT 0,
  llm_output_tokens integer NOT NULL DEFAULT 0,
  cost_inr          numeric(10, 4) NOT NULL DEFAULT 0,
  recording_url     text,
  UNIQUE (business_id, id),
  FOREIGN KEY (business_id, customer_id) REFERENCES customers (business_id, id)
    ON DELETE SET NULL (customer_id)
);
CREATE INDEX conversations_business_started_idx ON conversations (business_id, started_at DESC);

CREATE TABLE bookings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id     uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  customer_id     uuid NOT NULL,
  service_id      uuid NOT NULL,
  staff_id        uuid NOT NULL,
  conversation_id uuid,
  start_at        timestamptz NOT NULL,
  end_at          timestamptz NOT NULL,
  status          text NOT NULL DEFAULT 'confirmed'
                  CHECK (status IN ('confirmed', 'cancelled', 'completed', 'no_show')),
  source          text NOT NULL CHECK (source IN ('voice', 'whatsapp', 'web_chat', 'dashboard')),
  notes           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (end_at > start_at),
  FOREIGN KEY (business_id, customer_id) REFERENCES customers (business_id, id),
  FOREIGN KEY (business_id, service_id) REFERENCES services (business_id, id),
  FOREIGN KEY (business_id, staff_id) REFERENCES staff (business_id, id),
  FOREIGN KEY (business_id, conversation_id) REFERENCES conversations (business_id, id)
    ON DELETE SET NULL (conversation_id),
  CONSTRAINT bookings_no_overlap EXCLUDE USING gist (
    staff_id WITH =,
    tstzrange(start_at, end_at, '[)') WITH &&
  ) WHERE (status = 'confirmed')
);
CREATE INDEX bookings_business_start_idx ON bookings (business_id, start_at);
CREATE INDEX bookings_customer_idx ON bookings (business_id, customer_id, start_at);

CREATE TABLE kb_documents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  title       text NOT NULL,
  source_type text NOT NULL CHECK (source_type IN ('faq', 'pdf', 'text', 'url')),
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (business_id, id)
);

CREATE TABLE kb_chunks (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  document_id uuid NOT NULL,
  content     text NOT NULL,
  embedding   vector(768),
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
  FOREIGN KEY (business_id, document_id) REFERENCES kb_documents (business_id, id)
    ON DELETE CASCADE
);
CREATE INDEX kb_chunks_tsv_idx ON kb_chunks USING gin (tsv);
CREATE INDEX kb_chunks_embedding_idx ON kb_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE messages (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  business_id     uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  conversation_id uuid NOT NULL,
  role            text NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
  text            text,
  tool_name       text,
  tool_args       jsonb,
  tool_result     jsonb,
  latency_ms      integer,
  created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (business_id, conversation_id) REFERENCES conversations (business_id, id)
    ON DELETE CASCADE
);
CREATE INDEX messages_conversation_idx ON messages (conversation_id, id);

-- Row-level security ------------------------------------------------------

ALTER TABLE businesses ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON businesses USING (id = app_current_business());

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaani_app') THEN
    CREATE ROLE vaani_app NOLOGIN;  -- login and password are set outside migrations
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO vaani_app;
-- Creating a business is onboarding work, done by the owner connection.
GRANT SELECT, UPDATE ON businesses TO vaani_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO vaani_app;
"""

DOWNGRADE_SQL = """
DROP TABLE IF EXISTS messages, kb_chunks, kb_documents, bookings, conversations, customers,
  blocked_slots, working_hours, staff_services, staff, services, users, businesses CASCADE;
DROP FUNCTION IF EXISTS app_current_business();
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (business_id = app_current_business()) "
            "WITH CHECK (business_id = app_current_business())"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO vaani_app")


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
