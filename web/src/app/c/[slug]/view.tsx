"use client";

import { CalendarCheck, CheckCircle2, Clock, MapPin, Mic, Phone } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api, useApi } from "@/lib/api";
import { addDays, dayOf, languageName, phone as formatPhone, rupees, time } from "@/lib/format";
import type { DaySlots, FreeTime, PublicBooking, PublicBusiness, PublicHours } from "@/lib/types";
import { cn } from "@/lib/utils";

// Where the API (and its /voice page) is reachable from the public internet.
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** YYYY-MM-DD -> 0 (Monday) .. 6 (Sunday) */
function weekdayOf(day: string): number {
  const [y, m, d] = day.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

/** "17:30:00" -> "5:30 PM" */
function clock(value: string): string {
  const [h, m] = value.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

function spansFor(hours: PublicHours[], weekday: number): string {
  const spans = hours.filter((h) => h.weekday === weekday).map((h) => `${clock(h.open_time)}–${clock(h.close_time)}`);
  return spans.length ? spans.join(", ") : "Closed";
}

/** "Telugu, Hindi and English" */
function listOf(items: string[]): string {
  return items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items.at(-1)}` : (items[0] ?? "");
}

/** Consecutive days with the same hours on one line: "Mon–Sat: 10:00 AM–1:30 PM, …". */
function hoursLines(hours: PublicHours[]): { days: string; text: string; weekdays: number[] }[] {
  const lines: { days: string; text: string; weekdays: number[] }[] = [];
  for (let day = 0; day < 7; day++) {
    const text = spansFor(hours, day);
    const last = lines.at(-1);
    if (last && last.text === text) {
      last.weekdays.push(day);
      last.days = `${DAY_NAMES[last.weekdays[0]]}–${DAY_NAMES[day]}`;
    } else {
      lines.push({ days: DAY_NAMES[day], text, weekdays: [day] });
    }
  }
  return lines;
}

function shortDate(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

function longDate(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

function hourIn(iso: string, timeZone: string): number {
  return Number(new Intl.DateTimeFormat("en-GB", { hour: "2-digit", hourCycle: "h23", timeZone }).format(new Date(iso)));
}

function tenDigits(value: string): boolean {
  const digits = value.replace(/\D/g, "");
  return digits.length === 10 || (digits.length === 12 && digits.startsWith("91"));
}

export default function ClinicPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: clinic, error } = useApi<PublicBusiness>(`/v1/public/${slug}`, { revalidateOnFocus: false });

  useEffect(() => {
    if (clinic) document.title = `${clinic.name} · Book an appointment`;
  }, [clinic]);

  if (error) {
    return (
      <main className="mx-auto w-full max-w-md flex-1 px-4 py-24 text-center">
        <h1 className="text-xl font-semibold">{error.status === 404 ? "Page not found" : "Couldn't load this page"}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {error.status === 404 ? "Check the link you were given." : "Please try again in a moment."}
        </p>
      </main>
    );
  }
  if (!clinic) return <PageSkeleton />;
  return <Clinic clinic={clinic} />;
}

function PageSkeleton() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8">
      <Skeleton className="h-4 w-28" />
      <Skeleton className="mt-3 h-8 w-64" />
      <Skeleton className="mt-4 h-4 w-80 max-w-full" />
      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Skeleton className="h-96" />
        <Skeleton className="h-48" />
      </div>
    </div>
  );
}

function Clinic({ clinic }: { clinic: PublicBusiness }) {
  const voiceUrl = `${API}/voice/${clinic.slug}`;
  const today = spansFor(clinic.hours, weekdayOf(clinic.today));
  const languages = listOf(clinic.languages.map(languageName));

  return (
    <div className="flex-1 bg-muted/40">
      <header className="border-b bg-background">
        <div className="mx-auto w-full max-w-5xl px-4 py-8">
          <p className="text-sm font-medium capitalize text-primary">{clinic.type}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">{clinic.name}</h1>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
            {clinic.address && (
              <span className="flex items-center gap-1.5">
                <MapPin className="size-4 shrink-0" />
                {clinic.address}
              </span>
            )}
            {clinic.phone && (
              <a href={`tel:${clinic.phone}`} className="flex items-center gap-1.5 hover:text-foreground">
                <Phone className="size-4 shrink-0" />
                {formatPhone(clinic.phone)}
              </a>
            )}
            <span className="flex items-center gap-1.5">
              <Clock className="size-4 shrink-0" />
              {today === "Closed" ? "Closed today" : `Today ${today}`}
            </span>
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            <a href="#book" className={buttonVariants({ size: "lg" })}>
              <CalendarCheck /> Book an appointment
            </a>
            <a href={voiceUrl} target="_blank" rel="noreferrer" className={buttonVariants({ size: "lg", variant: "outline" })}>
              <Mic /> Talk to us
            </a>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Our assistant answers questions and books appointments in {languages}.
          </p>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-5xl grid-cols-[minmax(0,1fr)] items-start gap-6 px-4 py-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Booking clinic={clinic} />
        <aside className="grid gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Opening hours</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-2 text-sm">
                {hoursLines(clinic.hours).map((line) => (
                  <div
                    key={line.days}
                    className={cn(
                      "flex justify-between gap-4",
                      line.weekdays.includes(weekdayOf(clinic.today)) && "font-medium",
                    )}
                  >
                    <dt className="whitespace-nowrap">{line.days}</dt>
                    <dd className="text-right text-muted-foreground">
                      {line.text.split(", ").map((span) => (
                        <span key={span} className="block whitespace-nowrap">
                          {span}
                        </span>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Services</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="grid gap-2 text-sm">
                {clinic.services.map((s) => (
                  <li key={s.name} className="flex justify-between gap-4">
                    <span>{s.name}</span>
                    <span className="shrink-0 text-muted-foreground tabular-nums">
                      {s.duration_min} min{s.price_inr != null && ` · ${rupees(s.price_inr, 0)}`}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </aside>
      </main>

      <footer className="mx-auto w-full max-w-5xl px-4 pb-10 text-xs text-muted-foreground">
        Appointments and calls by{" "}
        <Link href="/" className="underline underline-offset-4 hover:text-foreground">
          Vaani
        </Link>
      </footer>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="grid min-w-0 gap-3">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <span className="flex size-5 items-center justify-center rounded-full bg-primary text-[11px] text-primary-foreground">
          {n}
        </span>
        {title}
      </h3>
      {children}
    </section>
  );
}

function Choice({
  selected,
  disabled,
  onClick,
  className,
  children,
}: {
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "rounded-lg border bg-background px-3 py-2 text-left text-sm transition-colors outline-none",
        "hover:border-primary/60 focus-visible:ring-3 focus-visible:ring-ring/50",
        "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border",
        selected && "border-primary bg-primary/5 ring-1 ring-primary",
        className,
      )}
    >
      {children}
    </button>
  );
}

function Booking({ clinic }: { clinic: PublicBusiness }) {
  const openDays = new Set(clinic.hours.map((h) => h.weekday));
  const days = Array.from({ length: clinic.book_days_ahead }, (_, i) => addDays(clinic.today, i));
  const firstOpen = days.find((d) => openDays.has(weekdayOf(d))) ?? clinic.today;

  const [service, setService] = useState<string | null>(clinic.services.length === 1 ? clinic.services[0].name : null);
  const [day, setDay] = useState(firstOpen);
  const [slot, setSlot] = useState<FreeTime | null>(null);
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [saving, setSaving] = useState(false);
  const [booked, setBooked] = useState<PublicBooking | null>(null);

  const slotsPath = service
    ? `/v1/public/${clinic.slug}/slots?service=${encodeURIComponent(service)}&date=${day}`
    : null;
  const { data: free, error, isLoading, mutate } = useApi<DaySlots>(slotsPath, { revalidateOnFocus: false });

  function chooseService(value: string) {
    setService(value);
    setSlot(null);
  }

  function chooseDay(value: string) {
    setDay(value);
    setSlot(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!service || !slot) return;
    if (!tenDigits(mobile)) {
      toast.error("Enter a 10-digit mobile number.");
      return;
    }
    setSaving(true);
    try {
      const booking = await api<PublicBooking>(`/v1/public/${clinic.slug}/bookings`, {
        json: { service, start_at: slot.start_at, customer_name: name.trim(), phone: mobile },
      });
      setBooked(booking);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("Someone just booked that time. Please pick another.");
        setSlot(null);
        await mutate();
      } else {
        toast.error(err instanceof Error ? err.message : "Couldn't book. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (booked) {
    const when = `${longDate(dayOf(booked.start_at, clinic.timezone))}, ${time(booked.start_at, clinic.timezone)}`;
    return (
      <Card id="book" className="scroll-mt-4">
        <CardContent className="grid justify-items-center gap-3 py-10 text-center">
          <CheckCircle2 className="size-10 text-primary" />
          <h2 className="text-xl font-semibold">You&apos;re booked</h2>
          <p className="text-sm">
            <span className="font-medium">{booked.service}</span> with {booked.staff}
            <br />
            {when}
          </p>
          <p className="max-w-sm text-sm text-muted-foreground">
            To change or cancel,{" "}
            {clinic.phone ? (
              <>
                call <a href={`tel:${clinic.phone}`} className="underline underline-offset-4">{formatPhone(clinic.phone)}</a> or{" "}
              </>
            ) : null}
            <a href={`${API}/voice/${clinic.slug}`} target="_blank" rel="noreferrer" className="underline underline-offset-4">
              talk to our assistant
            </a>
            .
          </p>
          <Button
            variant="outline"
            className="mt-2"
            onClick={() => {
              setBooked(null);
              setSlot(null);
              void mutate();
            }}
          >
            Book another appointment
          </Button>
        </CardContent>
      </Card>
    );
  }

  const groups = [
    { label: "Morning", slots: [] as FreeTime[] },
    { label: "Afternoon", slots: [] as FreeTime[] },
    { label: "Evening", slots: [] as FreeTime[] },
  ];
  for (const s of free?.slots ?? []) {
    const hour = hourIn(s.start_at, clinic.timezone);
    groups[hour < 12 ? 0 : hour < 17 ? 1 : 2].slots.push(s);
  }

  return (
    <Card id="book" className="scroll-mt-4">
      <CardHeader>
        <CardTitle>Book an appointment</CardTitle>
        <CardDescription>Pick a service and a time that suits you. It takes under a minute.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-7">
          <Step n={1} title="Choose a service">
            <div className="grid gap-2 sm:grid-cols-2">
              {clinic.services.map((s) => (
                <Choice key={s.name} selected={service === s.name} onClick={() => chooseService(s.name)}>
                  <span className="block font-medium">{s.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {s.duration_min} min{s.price_inr != null && ` · ${rupees(s.price_inr, 0)}`}
                  </span>
                </Choice>
              ))}
            </div>
          </Step>

          <Step n={2} title="Pick a day">
            <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
              {days.map((d, i) => (
                <Choice
                  key={d}
                  selected={day === d}
                  disabled={!openDays.has(weekdayOf(d))}
                  onClick={() => chooseDay(d)}
                  className="min-w-16 shrink-0 text-center"
                >
                  <span className="block text-xs text-muted-foreground">
                    {i === 0 ? "Today" : i === 1 ? "Tomorrow" : DAY_NAMES[weekdayOf(d)]}
                  </span>
                  <span className="block font-medium whitespace-nowrap">{shortDate(d)}</span>
                </Choice>
              ))}
            </div>
          </Step>

          <Step n={3} title="Pick a time">
            {!service ? (
              <p className="text-sm text-muted-foreground">Choose a service to see free times.</p>
            ) : error ? (
              <p className="text-sm text-destructive">{error.message}</p>
            ) : isLoading || !free ? (
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                {Array.from({ length: 10 }, (_, i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : free.slots.length === 0 ? (
              <div className="grid justify-items-start gap-2 text-sm">
                <p className="text-muted-foreground">No free times on {longDate(day)}.</p>
                {free.next_free_date && days.includes(free.next_free_date) && (
                  <Button type="button" variant="outline" size="sm" onClick={() => chooseDay(free.next_free_date!)}>
                    See {longDate(free.next_free_date)}
                  </Button>
                )}
              </div>
            ) : (
              <div className="grid gap-4">
                {groups
                  .filter((g) => g.slots.length)
                  .map((g) => (
                    <div key={g.label} className="grid gap-2">
                      <p className="text-xs text-muted-foreground">{g.label}</p>
                      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                        {g.slots.map((s) => (
                          <Choice
                            key={s.start_at}
                            selected={slot?.start_at === s.start_at}
                            onClick={() => setSlot(s)}
                            className="text-center tabular-nums"
                          >
                            {time(s.start_at, clinic.timezone)}
                          </Choice>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </Step>

          {slot && service && (
            <Step n={4} title="Your details">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor="name">Patient&apos;s name</Label>
                  <Input
                    id="name"
                    autoComplete="name"
                    required
                    maxLength={100}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="mobile">Mobile number</Label>
                  <Input
                    id="mobile"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    placeholder="98765 43210"
                    required
                    value={mobile}
                    onChange={(e) => setMobile(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex flex-col gap-3 rounded-lg bg-muted p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                <span>
                  <span className="font-medium">{service}</span> · {DAY_NAMES[weekdayOf(day)]} {shortDate(day)},{" "}
                  {time(slot.start_at, clinic.timezone)}
                </span>
                <Button type="submit" disabled={saving || !name.trim()}>
                  {saving ? "Booking…" : "Confirm booking"}
                </Button>
              </div>
            </Step>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
