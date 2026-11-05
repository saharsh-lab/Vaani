"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChannelBadge, Empty, NativeSelect, OUTCOMES, PageHeader } from "@/components/kit";
import { OwnerOnly } from "@/components/owner-only";
import { useSession } from "@/components/session";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/lib/api";
import { dateTime, duration, languageName, phone, rupees } from "@/lib/format";
import type { ConversationRow } from "@/lib/types";

const PAGE = 25;

export default function ConversationsPage() {
  return (
    <OwnerOnly>
      <Conversations />
    </OwnerOnly>
  );
}

function Conversations() {
  const { business } = useSession();
  const router = useRouter();
  const [channel, setChannel] = useState("");
  const [outcome, setOutcome] = useState("");
  const [page, setPage] = useState(0);
  const query = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
  if (channel) query.set("channel", channel);
  if (outcome) query.set("outcome", outcome);
  const { data } = useApi<{ total: number; items: ConversationRow[] }>(`/v1/dashboard/conversations?${query}`);

  return (
    <>
      <PageHeader title="Conversations" description="Every call and chat Vaani handled, with the full transcript." />
      <div className="mb-4 flex flex-wrap gap-2">
        <NativeSelect value={channel} onChange={(e) => (setChannel(e.target.value), setPage(0))} aria-label="Channel">
          <option value="">All channels</option>
          <option value="voice">Calls</option>
          <option value="whatsapp">WhatsApp</option>
          <option value="web_chat">Web chat</option>
        </NativeSelect>
        <NativeSelect value={outcome} onChange={(e) => (setOutcome(e.target.value), setPage(0))} aria-label="Outcome">
          <option value="">Any outcome</option>
          {Object.entries(OUTCOMES).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </div>

      {!data ? (
        <Skeleton className="h-64" />
      ) : data.items.length === 0 ? (
        <Empty title="No conversations yet">They appear here as soon as someone calls or messages.</Empty>
      ) : (
        <>
          <div className="rounded-xl ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Channel</TableHead>
                  <TableHead className="hidden md:table-cell">Language</TableHead>
                  <TableHead className="hidden md:table-cell">Length</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((c) => (
                  <TableRow
                    key={c.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/dashboard/conversations/${c.id}`)}
                  >
                    <TableCell className="tabular-nums">{dateTime(c.started_at, business.timezone)}</TableCell>
                    <TableCell>
                      {/* A real link too, for the keyboard, screen readers and "open in new tab". */}
                      <Link
                        href={`/dashboard/conversations/${c.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-medium underline-offset-4 hover:underline"
                      >
                        {c.customer_name ?? "Unknown"}
                      </Link>
                      <div className="text-xs text-muted-foreground">{phone(c.customer_phone)}</div>
                    </TableCell>
                    <TableCell>
                      <ChannelBadge channel={c.channel} />
                    </TableCell>
                    <TableCell className="hidden md:table-cell">{languageName(c.language)}</TableCell>
                    <TableCell className="hidden tabular-nums md:table-cell">{duration(c.duration_s)}</TableCell>
                    <TableCell>
                      {c.handoff ? (
                        <Badge className="border-0 bg-amber-500/15 text-amber-700 dark:text-amber-400">Handed to team</Badge>
                      ) : (
                        <span className="text-sm">{OUTCOMES[c.outcome ?? ""] ?? "In progress"}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{rupees(c.cost_inr, 3)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {page * PAGE + 1}–{Math.min((page + 1) * PAGE, data.total)} of {data.total}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(page + 1) * PAGE >= data.total}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
