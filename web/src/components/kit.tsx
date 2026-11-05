// Small building blocks shared by the dashboard pages.

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Field({
  label,
  htmlFor,
  hint,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** The browser's own <select>, styled to match the inputs. */
export function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30",
        className,
      )}
      {...props}
    />
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <Card size="sm">
      <CardContent>
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        {note && <p className="mt-0.5 text-xs text-muted-foreground">{note}</p>}
      </CardContent>
    </Card>
  );
}

export function ErrorNote({ error }: { error: Error | undefined }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {error.message}
    </p>
  );
}

const STATUS: Record<string, { label: string; className: string }> = {
  confirmed: { label: "Confirmed", className: "bg-primary/10 text-primary" },
  completed: { label: "Done", className: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" },
  no_show: { label: "No-show", className: "bg-amber-500/15 text-amber-700 dark:text-amber-400" },
  cancelled: { label: "Cancelled", className: "bg-muted text-muted-foreground line-through" },
  open: { label: "Waiting", className: "bg-amber-500/15 text-amber-700 dark:text-amber-400" },
  claimed: { label: "In progress", className: "bg-primary/10 text-primary" },
  resolved: { label: "Resolved", className: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, className: "" };
  return <Badge className={cn("border-0", s.className)}>{s.label}</Badge>;
}

const CHANNELS: Record<string, string> = {
  voice: "Call",
  whatsapp: "WhatsApp",
  web_chat: "Web chat",
  dashboard: "Front desk",
  online: "Online",
};

export function ChannelBadge({ channel }: { channel: string }) {
  return <Badge variant="outline">{CHANNELS[channel] ?? channel}</Badge>;
}

export const OUTCOMES: Record<string, string> = {
  booked: "Booked",
  changed: "Changed a booking",
  handoff: "Handed to team",
  info: "Answered a question",
};
