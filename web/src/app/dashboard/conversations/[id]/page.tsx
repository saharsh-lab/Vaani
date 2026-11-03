"use client";

import { ArrowLeft, Wrench } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ChannelBadge, OUTCOMES, Stat } from "@/components/kit";
import { OwnerOnly } from "@/components/owner-only";
import { useSession } from "@/components/session";
import { Skeleton } from "@/components/ui/skeleton";
import { useApi } from "@/lib/api";
import { dateTime, duration, languageName, phone, rupees, time } from "@/lib/format";
import type { ConversationDetail, TranscriptLine } from "@/lib/types";
import { cn } from "@/lib/utils";

const TOOL_NAMES: Record<string, string> = {
  check_availability: "Checked free slots",
  create_booking: "Made a booking",
  find_booking: "Looked up bookings",
  reschedule_or_cancel: "Changed a booking",
  search_knowledge: "Searched the FAQs",
  handoff_to_human: "Asked the team to call back",
};

export default function ConversationPage() {
  return (
    <OwnerOnly>
      <Conversation />
    </OwnerOnly>
  );
}

function Conversation() {
  const { id } = useParams<{ id: string }>();
  const { business } = useSession();
  const { data: c, error } = useApi<ConversationDetail>(`/v1/dashboard/conversations/${id}`);
  const tz = business.timezone;

  return (
    <>
      <Link href="/dashboard/conversations" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Conversations
      </Link>
      {error && <p className="text-sm text-destructive">{error.message}</p>}
      {!c ? (
        !error && <Skeleton className="h-96" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
          <section className="min-w-0">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight">{c.customer_name ?? "Unknown caller"}</h1>
              <ChannelBadge channel={c.channel} />
            </div>
            {c.handoff && c.handoff_reason && (
              <p className="mb-4 rounded-lg bg-amber-500/10 px-3 py-2 text-sm">
                Handed to the team: {c.handoff_reason}
              </p>
            )}
            <ol className="grid gap-3">
              {c.transcript.map((line, i) => (
                <Line key={i} line={line} tz={tz} />
              ))}
            </ol>
          </section>
          <aside className="grid content-start gap-3">
            <Stat label="Outcome" value={<span className="text-base">{c.handoff ? "Handed to team" : (OUTCOMES[c.outcome ?? ""] ?? "In progress")}</span>} />
            <Stat label="Cost" value={rupees(c.cost_inr, 3)} note={c.llm_input_tokens ? `${c.llm_input_tokens.toLocaleString()} in / ${c.llm_output_tokens.toLocaleString()} out tokens` : undefined} />
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-xl p-4 text-sm ring-1 ring-foreground/10">
              <dt className="text-muted-foreground">Started</dt>
              <dd>{dateTime(c.started_at, tz)}</dd>
              <dt className="text-muted-foreground">Length</dt>
              <dd>{duration(c.duration_s)}</dd>
              <dt className="text-muted-foreground">Language</dt>
              <dd>{languageName(c.language)}</dd>
              <dt className="text-muted-foreground">Phone</dt>
              <dd>{c.customer_phone ? <a className="text-primary hover:underline" href={`tel:${c.customer_phone}`}>{phone(c.customer_phone)}</a> : "–"}</dd>
            </dl>
          </aside>
        </div>
      )}
    </>
  );
}

function Line({ line, tz }: { line: TranscriptLine; tz: string }) {
  if (line.role === "tool") {
    return (
      <li>
        <details className="rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
          <summary className="flex cursor-pointer items-center gap-1.5">
            <Wrench className="size-3.5" />
            {TOOL_NAMES[line.tool_name ?? ""] ?? line.tool_name}
          </summary>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words">
            {JSON.stringify({ asked: line.tool_args, got: line.tool_result }, null, 2)}
          </pre>
        </details>
      </li>
    );
  }
  const customer = line.role === "user";
  return (
    <li className={cn("flex flex-col", customer ? "items-start" : "items-end")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm",
          customer ? "rounded-bl-sm bg-muted" : "rounded-br-sm bg-primary text-primary-foreground",
        )}
      >
        {line.text}
      </div>
      <span className="mt-1 text-xs text-muted-foreground">
        {customer ? "Customer" : "Vaani"} · {time(line.created_at, tz)}
        {line.latency_ms != null && !customer && ` · replied in ${(line.latency_ms / 1000).toFixed(1)} s`}
      </span>
    </li>
  );
}
