"use client";

import { Phone } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelBadge, Empty, ErrorNote, Field, PageHeader, StatusBadge } from "@/components/kit";
import { useSession } from "@/components/session";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, useApi } from "@/lib/api";
import { ago, dateTime, phone } from "@/lib/format";
import type { Handoff } from "@/lib/types";

export default function HandoffsPage() {
  const { user, business } = useSession();
  const [tab, setTab] = useState<"active" | "resolved">("active");
  const { data, mutate } = useApi<Handoff[]>(`/v1/dashboard/handoffs?status=${tab}`, { refreshInterval: 20_000 });
  const [resolving, setResolving] = useState<Handoff | null>(null);

  async function claim(h: Handoff) {
    try {
      await api(`/v1/dashboard/handoffs/${h.conversation_id}/claim`, { method: "POST" });
      toast.success("It's yours. Call them back.");
      mutate();
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  }

  return (
    <>
      <PageHeader
        title="Callbacks"
        description="Customers Vaani handed to the team: they asked for a person, were upset, or needed something Vaani can't do."
      />
      <Tabs value={tab} onValueChange={(v) => setTab(v as "active" | "resolved")} className="mb-4">
        <TabsList>
          <TabsTrigger value="active">To do</TabsTrigger>
          <TabsTrigger value="resolved">Resolved</TabsTrigger>
        </TabsList>
      </Tabs>

      {!data ? (
        <Skeleton className="h-40" />
      ) : data.length === 0 ? (
        <Empty title={tab === "active" ? "No one is waiting for a callback" : "Nothing resolved yet"} />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {data.map((h) => (
            <Card key={h.conversation_id}>
              <CardContent className="grid gap-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{h.customer_name ?? "Unknown caller"}</p>
                    {h.customer_phone ? (
                      <a href={`tel:${h.customer_phone}`} className="flex items-center gap-1 text-sm text-primary hover:underline">
                        <Phone className="size-3.5" /> {phone(h.customer_phone)}
                      </a>
                    ) : (
                      <p className="text-sm text-muted-foreground">No number (web caller)</p>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={h.status} />
                    <ChannelBadge channel={h.channel} />
                  </div>
                </div>
                {h.reason && (
                  <p className="text-sm">
                    <span className="text-muted-foreground">Why: </span>
                    {h.reason}
                  </p>
                )}
                {h.summary && h.summary !== h.reason && <p className="rounded-lg bg-muted px-3 py-2 text-sm">{h.summary}</p>}
                {h.note && (
                  <p className="text-sm">
                    <span className="text-muted-foreground">Note: </span>
                    {h.note}
                  </p>
                )}
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>
                    {dateTime(h.started_at, business.timezone)} · {ago(h.updated_at ?? h.started_at)}
                    {h.assignee && ` · ${h.status === "resolved" ? "resolved by" : "with"} ${h.assignee}`}
                  </span>
                  <div className="flex gap-2">
                    {user.role === "owner" && (
                      <Link href={`/dashboard/conversations/${h.conversation_id}`} className="text-primary underline underline-offset-4 hover:decoration-2">
                        Transcript
                      </Link>
                    )}
                  </div>
                </div>
                {h.status !== "resolved" && (
                  <div className="flex gap-2">
                    {h.status === "open" && (
                      <Button variant="outline" onClick={() => claim(h)}>
                        {"I'll call them"}
                      </Button>
                    )}
                    <Button onClick={() => setResolving(h)}>Mark resolved</Button>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <ResolveDialog handoff={resolving} onClose={() => setResolving(null)} onDone={() => mutate()} />
    </>
  );
}

function ResolveDialog({ handoff, onClose, onDone }: { handoff: Handoff | null; onClose: () => void; onDone: () => void }) {
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!handoff) return;
    setBusy(true);
    try {
      const note = new FormData(event.currentTarget).get("note");
      await api(`/v1/dashboard/handoffs/${handoff.conversation_id}/resolve`, { json: { note } });
      toast.success("Resolved");
      onClose();
      onDone();
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={handoff !== null} onOpenChange={(open) => !open && (setError(undefined), onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Mark resolved</DialogTitle>
          <DialogDescription>{handoff?.customer_name ?? "This caller"} will drop off the to-do list.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <Field label="What happened (optional)" htmlFor="note">
            <Textarea id="note" name="note" placeholder="Called back, booked a check-up for Friday." maxLength={1000} />
          </Field>
          <ErrorNote error={error} />
          <DialogFooter>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Resolve"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
