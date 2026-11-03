// Mirrors backend/app/schemas_dashboard.py.

export type Role = "owner" | "staff";

export type User = { id: string; name: string | null; email: string; role: Role; active: boolean };

export type Business = {
  id: string;
  slug: string;
  name: string;
  type: string;
  timezone: string;
  languages: string[];
  greeting: string | null;
  address: string | null;
  phone: string | null;
  whatsapp_connected: boolean;
};

export type Me = { user: User; business: Business };

export type Booking = {
  id: string;
  start_at: string;
  end_at: string;
  status: "confirmed" | "cancelled" | "completed" | "no_show";
  source: "voice" | "whatsapp" | "web_chat" | "dashboard";
  service: string;
  staff: string;
  staff_id: string;
  customer_name: string | null;
  customer_phone: string;
  conversation_id: string | null;
};

export type Handoff = {
  conversation_id: string;
  status: "open" | "claimed" | "resolved";
  reason: string | null;
  summary: string | null;
  channel: string;
  customer_name: string | null;
  customer_phone: string | null;
  started_at: string;
  updated_at: string | null;
  assignee: string | null;
  note: string | null;
};

export type ConversationRow = {
  id: string;
  channel: "voice" | "whatsapp" | "web_chat";
  language: string | null;
  started_at: string;
  duration_s: number | null;
  outcome: string | null;
  handoff: boolean;
  cost_inr: number;
  customer_name: string | null;
  customer_phone: string | null;
  messages: number;
};

export type TranscriptLine = {
  role: "user" | "assistant" | "tool";
  text: string | null;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: Record<string, unknown> | null;
  latency_ms: number | null;
  created_at: string;
};

export type ConversationDetail = ConversationRow & {
  summary: string | null;
  handoff_reason: string | null;
  llm_input_tokens: number;
  llm_output_tokens: number;
  transcript: TranscriptLine[];
};

export type Overview = {
  date: string;
  bookings_today: number;
  next_bookings: Booking[];
  open_handoffs: number;
  conversations_7d: number;
  by_channel_7d: Record<string, number>;
  agent_bookings_7d: number;
  cost_7d_inr: number;
  voice_p50_ms: number | null;
  voice_p95_ms: number | null;
  languages_7d: Record<string, number>;
  setup: Record<"services" | "hours" | "staff" | "faqs" | "greeting" | "whatsapp", boolean>;
};

export type Hours = { weekday: number; open_time: string; close_time: string };

export type Service = {
  id: string;
  name: string;
  duration_min: number;
  price_inr: number | null;
  description: string | null;
  active: boolean;
};

export type StaffMember = {
  id: string;
  name: string;
  active: boolean;
  service_ids: string[];
  custom_hours: boolean;
};

export type Blocked = {
  id: string;
  start_date: string;
  end_date: string;
  staff_id: string | null;
  staff: string | null;
  reason: string | null;
};

export type Faq = {
  id: string;
  title: string;
  content: string;
  source_type: "faq" | "pdf" | "text";
  chunks: number;
  uploaded_at: string;
};
