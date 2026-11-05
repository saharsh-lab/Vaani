"use client";

import { ChevronLeft, ChevronRight, MoreHorizontal, Phone, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ChannelBadge, Empty, ErrorNote, Field, NativeSelect, PageHeader, StatusBadge } from "@/components/kit";
import { useSession } from "@/components/session";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, useApi } from "@/lib/api";
import { addDays, dayLabel, dayOf, phone, time, todayIn } from "@/lib/format";
import { MOBILE_ERROR, MOBILE_PATTERN } from "@/lib/validation";
import type { Booking, Service, StaffMember } from "@/lib/types";

type Alternative = { start_at: string; label: string; staff: string };

export default function BookingsPage() {
  const { business } = useSession();
  const tz = business.timezone;
  const [day, setDay] = useState(() => todayIn(tz));
  const [view, setView] = useState<"day" | "week">("day");
  const [staffId, setStaffId] = useState("");
  const [creating, setCreating] = useState(false);
  const [moving, setMoving] = useState<Booking | null>(null);

  const days = view === "day" ? 1 : 7;
  const key = `/v1/dashboard/bookings?start=${day}&days=${days}${staffId ? `&staff_id=${staffId}` : ""}`;
  const { data: bookings, mutate } = useApi<Booking[]>(key, { refreshInterval: 30_000 });
  const { data: staff } = useApi<StaffMember[]>("/v1/dashboard/staff");
  const { data: services } = useApi<Service[]>("/v1/dashboard/services");

  async function setStatus(booking: Booking, status: "completed" | "no_show" | "cancelled") {
    try {
      await api(`/v1/dashboard/bookings/${booking.id}/status`, { json: { status } });
      toast.success(
        { completed: "Marked as done", no_show: "Marked as no-show", cancelled: "Booking cancelled" }[status],
      );
      mutate();
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  }

  const columns = useMemo(() => {
    const list = bookings ?? [];
    if (view === "week") {
      return Array.from({ length: 7 }, (_, i) => {
        const d = addDays(day, i);
        return { key: d, title: dayLabel(d), items: list.filter((b) => dayOf(b.start_at, tz) === d) };
      });
    }
    const people = (staff ?? []).filter((s) => s.active && (!staffId || s.id === staffId));
    return people.map((s) => ({ key: s.id, title: s.name, items: list.filter((b) => b.staff_id === s.id) }));
  }, [bookings, view, day, staff, staffId, tz]);

  const today = todayIn(tz);
  return (
    <>
      <PageHeader
        title="Bookings"
        description={view === "day" ? dayLabel(day) : `${dayLabel(day)} – ${dayLabel(addDays(day, 6))}`}
        actions={
          <>
            <Button onClick={() => setCreating(true)}>
              <Plus /> New booking
            </Button>
          </>
        }
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" aria-label="Previous" onClick={() => setDay(addDays(day, -days))}>
            <ChevronLeft />
          </Button>
          <Button variant="outline" onClick={() => setDay(today)} disabled={day === today}>
            Today
          </Button>
          <Button variant="outline" size="icon" aria-label="Next" onClick={() => setDay(addDays(day, days))}>
            <ChevronRight />
          </Button>
        </div>
        <Input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} className="w-auto" aria-label="Date" />
        <Tabs value={view} onValueChange={(v) => setView(v as "day" | "week")}>
          <TabsList>
            <TabsTrigger value="day">Day</TabsTrigger>
            <TabsTrigger value="week">Week</TabsTrigger>
          </TabsList>
        </Tabs>
        <NativeSelect value={staffId} onChange={(e) => setStaffId(e.target.value)} aria-label="Staff">
          <option value="">Everyone</option>
          {staff?.filter((s) => s.active).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </NativeSelect>
      </div>

      {!bookings || !staff ? (
        <Skeleton className="h-64" />
      ) : columns.length === 0 ? (
        <Empty title="No staff yet">Add staff in Settings to start taking bookings.</Empty>
      ) : (
        <div className={view === "week" ? "grid gap-3 md:grid-cols-7" : "grid gap-4 md:grid-cols-2 xl:grid-cols-3"}>
          {columns.map((col) => (
            <section key={col.key} className="min-w-0">
              <h2 className="mb-2 text-sm font-medium text-muted-foreground">
                {col.title} <span className="tabular-nums">· {col.items.filter((b) => b.status !== "cancelled").length}</span>
              </h2>
              <div className="grid gap-2">
                {col.items.length === 0 && <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">Nothing booked</p>}
                {col.items.map((b) => (
                  <BookingCard
                    key={b.id}
                    booking={b}
                    tz={tz}
                    compact={view === "week"}
                    onStatus={(s) => setStatus(b, s)}
                    onMove={() => setMoving(b)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <NewBookingDialog
        open={creating}
        onOpenChange={setCreating}
        day={day}
        services={services ?? []}
        staff={staff ?? []}
        onDone={() => mutate()}
      />
      <MoveDialog booking={moving} onClose={() => setMoving(null)} tz={tz} onDone={() => mutate()} />
    </>
  );
}

function BookingCard({
  booking: b,
  tz,
  compact,
  onStatus,
  onMove,
}: {
  booking: Booking;
  tz: string;
  compact: boolean;
  onStatus: (s: "completed" | "no_show" | "cancelled") => void;
  onMove: () => void;
}) {
  const live = b.status === "confirmed";
  return (
    <Card size="sm" className={b.status === "cancelled" ? "opacity-60" : ""}>
      <CardContent className="grid gap-1.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium tabular-nums">
              {time(b.start_at, tz)}
              {!compact && <span className="text-muted-foreground"> – {time(b.end_at, tz)}</span>}
            </p>
            <p className="truncate font-medium">{b.customer_name ?? "Customer"}</p>
          </div>
          {live && (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="Booking actions" />}>
                <MoreHorizontal />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onStatus("completed")}>Mark as done</DropdownMenuItem>
                <DropdownMenuItem onClick={() => onStatus("no_show")}>Mark as no-show</DropdownMenuItem>
                <DropdownMenuItem onClick={onMove}>Move…</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onClick={() => onStatus("cancelled")}>
                  Cancel booking
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
        <p className="truncate text-sm text-muted-foreground">
          {b.service}
          {compact && ` · ${b.staff}`}
        </p>
        {!compact && (
          <a href={`tel:${b.customer_phone}`} className="flex items-center gap-1 text-sm text-primary hover:underline">
            <Phone className="size-3.5" /> {phone(b.customer_phone)}
          </a>
        )}
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge status={b.status} />
          <ChannelBadge channel={b.source} />
        </div>
      </CardContent>
    </Card>
  );
}

function NewBookingDialog({
  open,
  onOpenChange,
  day,
  services,
  staff,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  day: string;
  services: Service[];
  staff: StaffMember[];
  onDone: () => void;
}) {
  const [error, setError] = useState<ApiError>();
  const [alternatives, setAlternatives] = useState<Alternative[]>([]);
  const [busy, setBusy] = useState(false);
  const [date, setDate] = useState(day);
  const [clock, setClock] = useState("10:00");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    setAlternatives([]);
    try {
      const result = await api<{ label: string }>("/v1/dashboard/bookings", {
        json: {
          service: form.get("service"),
          staff: form.get("staff") || null,
          start_at: `${date}T${clock}:00`,
          customer_name: form.get("customer_name"),
          phone: form.get("phone"),
        },
      });
      toast.success(`Booked for ${result.label}`);
      onOpenChange(false);
      onDone();
    } catch (err) {
      const e = err as ApiError;
      setError(e);
      const body = e.body as { alternatives?: Alternative[] } | null;
      setAlternatives(body?.alternatives ?? []);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) setDate(day);
        setError(undefined);
        setAlternatives([]);
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New booking</DialogTitle>
          <DialogDescription>For walk-ins and phone calls the front desk takes.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <Field label="Service" htmlFor="service">
            <NativeSelect id="service" name="service" required>
              {services.filter((s) => s.active).map((s) => (
                <option key={s.id} value={s.name}>
                  {s.name} · {s.duration_min} min
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="With" htmlFor="staff">
            <NativeSelect id="staff" name="staff">
              <option value="">Whoever is free</option>
              {staff.filter((s) => s.active).map((s) => (
                <option key={s.id} value={s.name}>
                  {s.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date" htmlFor="date">
              <Input id="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
            </Field>
            <Field label="Time" htmlFor="time">
              <Input id="time" type="time" step={900} value={clock} onChange={(e) => setClock(e.target.value)} required />
            </Field>
          </div>
          <Field label="Customer name" htmlFor="customer_name">
            <Input id="customer_name" name="customer_name" autoComplete="off" required maxLength={100} />
          </Field>
          <Field label="Mobile number" htmlFor="phone">
            <Input
              id="phone"
              name="phone"
              type="tel"
              inputMode="tel"
              placeholder="98765 43210"
              required
              maxLength={20}
              pattern={MOBILE_PATTERN}
              data-error={MOBILE_ERROR}
            />
          </Field>
          <ErrorNote error={error} />
          {alternatives.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Free nearby:</span>
              {alternatives.map((a) => (
                <Button
                  key={a.start_at}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setDate(a.start_at.slice(0, 10));
                    setClock(a.start_at.slice(11, 16));
                    setError(undefined);
                    setAlternatives([]);
                  }}
                >
                  {a.label}
                </Button>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button type="submit" disabled={busy}>
              {busy ? "Booking…" : "Book"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MoveDialog({
  booking,
  onClose,
  tz,
  onDone,
}: {
  booking: Booking | null;
  onClose: () => void;
  tz: string;
  onDone: () => void;
}) {
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!booking) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const result = await api<{ label: string }>(`/v1/dashboard/bookings/${booking.id}/move`, {
        json: { start_at: `${form.get("date")}T${form.get("time")}:00` },
      });
      toast.success(`Moved to ${result.label}`);
      onClose();
      onDone();
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={booking !== null} onOpenChange={(open) => !open && (setError(undefined), onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Move booking</DialogTitle>
          {booking && (
            <DialogDescription>
              {booking.customer_name} · {booking.service}, now at {time(booking.start_at, tz)} on{" "}
              {dayLabel(dayOf(booking.start_at, tz))}
            </DialogDescription>
          )}
        </DialogHeader>
        {booking && (
          <form onSubmit={submit} className="grid gap-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="New date" htmlFor="move-date">
                <Input id="move-date" name="date" type="date" defaultValue={dayOf(booking.start_at, tz)} required />
              </Field>
              <Field label="New time" htmlFor="move-time">
                <Input id="move-time" name="time" type="time" step={900} defaultValue="10:00" required />
              </Field>
            </div>
            <ErrorNote error={error} />
            <DialogFooter>
              <Button type="submit" disabled={busy}>
                {busy ? "Moving…" : "Move"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
