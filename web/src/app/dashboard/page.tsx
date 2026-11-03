"use client";

import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ChannelBadge, Empty, PageHeader, Stat } from "@/components/kit";
import { useSession } from "@/components/session";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useApi } from "@/lib/api";
import { dateTime, dayLabel, languageName, rupees } from "@/lib/format";
import type { Overview } from "@/lib/types";

const SETUP = [
  { key: "services", label: "Add the services customers can book", href: "/dashboard/settings?tab=services" },
  { key: "hours", label: "Set your opening hours", href: "/dashboard/settings?tab=hours" },
  { key: "staff", label: "Add staff and what each one does", href: "/dashboard/settings?tab=staff" },
  { key: "faqs", label: "Add answers to common questions", href: "/dashboard/knowledge" },
  { key: "greeting", label: "Write the greeting callers hear", href: "/dashboard/settings" },
  { key: "whatsapp", label: "Connect your WhatsApp number", href: "/dashboard/channels" },
] as const;

function Bars({ data, label }: { data: Record<string, number>; label: (key: string) => string }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  if (!total) return <p className="text-sm text-muted-foreground">No conversations yet.</p>;
  return (
    <ul className="grid gap-2">
      {entries.map(([key, n]) => (
        <li key={key} className="grid gap-1">
          <div className="flex justify-between text-sm">
            <span>{label(key)}</span>
            <span className="tabular-nums text-muted-foreground">{n}</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted">
            <div className="h-1.5 rounded-full bg-primary" style={{ width: `${(n / total) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** "Dr. Lakshmi Reddy" -> "Lakshmi" */
function firstName(name: string | null): string {
  const first = name?.replace(/^(dr|mr|mrs|ms|prof)\.?\s+/i, "").split(" ")[0];
  return first || "there";
}

const CHANNEL_NAMES: Record<string, string> = { voice: "Calls", whatsapp: "WhatsApp", web_chat: "Web chat" };

export default function OverviewPage() {
  const { user, business } = useSession();
  const router = useRouter();
  const isOwner = user.role === "owner";
  const { data } = useApi<Overview>(isOwner ? "/v1/dashboard/overview" : null, { refreshInterval: 60_000 });

  useEffect(() => {
    if (!isOwner) router.replace("/dashboard/bookings");
  }, [isOwner, router]);

  if (!isOwner) return null;
  const missing = data ? SETUP.filter((s) => !data.setup[s.key]) : [];

  return (
    <>
      <PageHeader title={`Good to see you, ${firstName(user.name)}`} description={data && dayLabel(data.date)} />

      {data && missing.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Finish setting up</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-2 sm:grid-cols-2">
              {SETUP.map((step) => {
                const done = data.setup[step.key];
                return (
                  <li key={step.key}>
                    <Link href={step.href} className="flex items-center gap-2 text-sm hover:underline">
                      {done ? (
                        <CheckCircle2 className="size-4 text-primary" />
                      ) : (
                        <Circle className="size-4 text-muted-foreground" />
                      )}
                      <span className={done ? "text-muted-foreground line-through" : ""}>{step.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      )}

      {!data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Bookings today" value={data.bookings_today} />
            <Stat
              label="Waiting for a callback"
              value={<Link href="/dashboard/handoffs" className="hover:underline">{data.open_handoffs}</Link>}
            />
            <Stat
              label="Booked by Vaani"
              value={data.agent_bookings_7d}
              note={`${data.conversations_7d} conversations in 7 days`}
            />
            <Stat
              label="Cost, last 7 days"
              value={rupees(data.cost_7d_inr)}
              note={
                data.voice_p50_ms != null
                  ? `Calls reply in ${(data.voice_p50_ms / 1000).toFixed(1)} s (p95 ${((data.voice_p95_ms ?? 0) / 1000).toFixed(1)} s)`
                  : "Speech, AI and voice costs"
              }
            />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Coming up</CardTitle>
              </CardHeader>
              <CardContent>
                {data.next_bookings.length === 0 ? (
                  <Empty title="No upcoming bookings" />
                ) : (
                  <ul className="divide-y">
                    {data.next_bookings.map((b) => (
                      <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                        <div>
                          <p className="font-medium">{b.customer_name ?? "Customer"}</p>
                          <p className="text-muted-foreground">
                            {b.service} · {b.staff}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <ChannelBadge channel={b.source} />
                          <span className="tabular-nums">{dateTime(b.start_at, business.timezone)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <div className="grid content-start gap-6">
              <Card>
                <CardHeader>
                  <CardTitle>Channels, last 7 days</CardTitle>
                </CardHeader>
                <CardContent>
                  <Bars data={data.by_channel_7d} label={(k) => CHANNEL_NAMES[k] ?? k} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Languages</CardTitle>
                </CardHeader>
                <CardContent>
                  <Bars data={data.languages_7d} label={languageName} />
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}
    </>
  );
}
