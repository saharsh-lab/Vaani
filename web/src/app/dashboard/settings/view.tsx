"use client";

import { Plus, Trash2, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { useSWRConfig } from "swr";

import { Empty, ErrorNote, Field, NativeSelect, PageHeader } from "@/components/kit";
import { OwnerOnly } from "@/components/owner-only";
import { useSession } from "@/components/session";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, useApi } from "@/lib/api";
import { dayLabel, hhmm, LANGUAGES, rupees, WEEKDAYS } from "@/lib/format";
import { PHONE_ERROR, PHONE_PATTERN } from "@/lib/validation";
import type { Blocked, Business, Hours, Service, StaffMember } from "@/lib/types";

const TABS = ["business", "hours", "services", "staff", "days-off"] as const;
type Tab = (typeof TABS)[number];

export default function SettingsPage() {
  return (
    <OwnerOnly>
      <Settings />
    </OwnerOnly>
  );
}

function Settings() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>(() => {
    const wanted = params.get("tab");
    return wanted && (TABS as readonly string[]).includes(wanted) ? (wanted as Tab) : "business";
  });

  return (
    <>
      <PageHeader title="Settings" description="What Vaani knows about your business. Changes apply to the next conversation." />
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList className="mb-4 flex-wrap">
          <TabsTrigger value="business">Business</TabsTrigger>
          <TabsTrigger value="hours">Hours</TabsTrigger>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="staff">Staff</TabsTrigger>
          <TabsTrigger value="days-off">Days off</TabsTrigger>
        </TabsList>
        <TabsContent value="business">
          <BusinessForm />
        </TabsContent>
        <TabsContent value="hours">
          <HoursEditor />
        </TabsContent>
        <TabsContent value="services">
          <Services />
        </TabsContent>
        <TabsContent value="staff">
          <StaffList />
        </TabsContent>
        <TabsContent value="days-off">
          <DaysOff />
        </TabsContent>
      </Tabs>
    </>
  );
}

// Business ---------------------------------------------------------------------------

function BusinessForm() {
  const { business } = useSession();
  const { mutate } = useSWRConfig();
  const [languages, setLanguages] = useState(business.languages);
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      await api<Business>("/v1/dashboard/business", {
        method: "PATCH",
        json: {
          name: form.get("name"),
          type: form.get("type"),
          greeting: form.get("greeting"),
          address: form.get("address") || null,
          phone: form.get("phone") || null,
          languages,
        },
      });
      await mutate("/v1/dashboard/me");
      toast.success("Saved");
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-2xl">
      <CardContent>
        <form onSubmit={submit} className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Business name" htmlFor="name">
              <Input id="name" name="name" defaultValue={business.name} required minLength={2} maxLength={80} />
            </Field>
            <Field label="Type of business" htmlFor="type">
              <Input id="type" name="type" defaultValue={business.type} required minLength={2} maxLength={60} />
            </Field>
          </div>
          <Field label="Greeting" htmlFor="greeting" hint="The first thing callers hear. On WhatsApp, Vaani starts its first reply this way.">
            <Textarea id="greeting" name="greeting" defaultValue={business.greeting ?? ""} rows={2} maxLength={300} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Address" htmlFor="address">
              <Input id="address" name="address" defaultValue={business.address ?? ""} maxLength={200} />
            </Field>
            <Field label="Phone" htmlFor="phone">
              <Input
                id="phone"
                name="phone"
                type="tel"
                inputMode="tel"
                defaultValue={business.phone ?? ""}
                maxLength={20}
                pattern={PHONE_PATTERN}
                data-error={PHONE_ERROR}
              />
            </Field>
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Languages</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {Object.entries(LANGUAGES).map(([code, name]) => (
                <Label key={code} className="font-normal">
                  <Checkbox
                    checked={languages.includes(code)}
                    onCheckedChange={(on) => setLanguages(on ? [...languages, code] : languages.filter((c) => c !== code))}
                  />
                  {name}
                </Label>
              ))}
            </div>
          </fieldset>
          <ErrorNote error={error} />
          <div>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// Hours ------------------------------------------------------------------------------

type Interval = { open: string; close: string };

function HoursEditor() {
  const { data: staff } = useApi<StaffMember[]>("/v1/dashboard/staff");
  const [who, setWho] = useState("");
  const key = `/v1/dashboard/hours${who ? `?staff_id=${who}` : ""}`;
  const { data, mutate } = useApi<Hours[]>(key);
  const person = staff?.find((s) => s.id === who);

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Opening hours</CardTitle>
        <CardDescription>Vaani only offers slots inside these hours. Add a second shift for split hours, like 10–1:30 and 5–9.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <Field label="Hours for" htmlFor="who">
          <NativeSelect id="who" value={who} onChange={(e) => setWho(e.target.value)} className="w-full sm:w-72">
            <option value="">The business</option>
            {staff?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {!data ? (
          <Skeleton className="h-64" />
        ) : (
          // Re-mounts (and so resets) whenever the person or the saved hours change.
          <WeekForm key={`${who}:${JSON.stringify(data)}`} url={key} saved={data} person={who ? person?.name : undefined} onSaved={() => mutate()} />
        )}
      </CardContent>
    </Card>
  );
}

function WeekForm({ url, saved, person, onSaved }: { url: string; saved: Hours[]; person?: string; onSaved: () => void }) {
  const [week, setWeek] = useState<Interval[][]>(() => {
    const days: Interval[][] = WEEKDAYS.map(() => []);
    for (const h of saved) days[h.weekday].push({ open: hhmm(h.open_time), close: hhmm(h.close_time) });
    return days;
  });
  const [custom, setCustom] = useState(person === undefined || saved.length > 0);
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);

  function update(day: number, fn: (list: Interval[]) => Interval[]) {
    setWeek((w) => w.map((list, i) => (i === day ? fn(list) : list)));
  }

  async function save() {
    const rows = custom
      ? week.flatMap((list, weekday) => list.map((iv) => ({ weekday, open_time: iv.open, close_time: iv.close })))
      : [];
    setBusy(true);
    setError(undefined);
    try {
      await api(url, { method: "PUT", json: rows });
      toast.success("Hours saved");
      onSaved();
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {person !== undefined && (
        <Label className="font-normal">
          <Switch checked={custom} onCheckedChange={setCustom} />
          {person} works different hours from the business
        </Label>
      )}
      {custom && (
        <ul className="divide-y">
          {WEEKDAYS.map((name, day) => (
            <li key={name} className="flex flex-wrap items-start gap-3 py-2.5">
              <span className="w-24 pt-1 text-sm font-medium">{name}</span>
              <div className="grid flex-1 gap-2">
                {week[day].length === 0 && <span className="pt-1 text-sm text-muted-foreground">Closed</span>}
                {week[day].map((iv, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input
                      type="time"
                      value={iv.open}
                      aria-label={`${name} opens`}
                      onChange={(e) => update(day, (l) => l.map((x, j) => (j === i ? { ...x, open: e.target.value } : x)))}
                      className="w-32"
                    />
                    <span className="text-muted-foreground">to</span>
                    <Input
                      type="time"
                      value={iv.close}
                      aria-label={`${name} closes`}
                      onChange={(e) => update(day, (l) => l.map((x, j) => (j === i ? { ...x, close: e.target.value } : x)))}
                      className="w-32"
                    />
                    <Button variant="ghost" size="icon" aria-label="Remove shift" onClick={() => update(day, (l) => l.filter((_, j) => j !== i))}>
                      <X />
                    </Button>
                  </div>
                ))}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => update(day, (l) => [...l, l.length ? { open: "17:00", close: "21:00" } : { open: "10:00", close: "19:00" }])}
              >
                <Plus /> {week[day].length ? "Shift" : "Open"}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ErrorNote error={error} />
      <div>
        <Button onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Save hours"}
        </Button>
      </div>
    </>
  );
}

// Services ---------------------------------------------------------------------------

function Services() {
  const { data, mutate } = useApi<Service[]>("/v1/dashboard/services");
  const [editing, setEditing] = useState<Service | "new" | null>(null);

  async function toggle(service: Service, active: boolean) {
    try {
      await api(`/v1/dashboard/services/${service.id}`, { method: "PATCH", json: { active } });
      mutate();
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  }

  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button onClick={() => setEditing("new")}>
          <Plus /> Add service
        </Button>
      </div>
      {!data ? (
        <Skeleton className="h-48" />
      ) : data.length === 0 ? (
        <Empty title="No services yet">Add what customers can book, with how long it takes.</Empty>
      ) : (
        <div className="rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Service</TableHead>
                <TableHead>Length</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Bookable</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <button className="text-left font-medium hover:underline" onClick={() => setEditing(s)}>
                      {s.name}
                    </button>
                    {s.description && <div className="text-xs text-muted-foreground">{s.description}</div>}
                  </TableCell>
                  <TableCell className="tabular-nums">{s.duration_min} min</TableCell>
                  <TableCell className="tabular-nums">{rupees(s.price_inr, 0)}</TableCell>
                  <TableCell>
                    <Switch checked={s.active} onCheckedChange={(on) => toggle(s, on)} aria-label={`${s.name} bookable`} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <ServiceDialog service={editing} onClose={() => setEditing(null)} onDone={() => mutate()} />
    </>
  );
}

function ServiceDialog({ service, onClose, onDone }: { service: Service | "new" | null; onClose: () => void; onDone: () => void }) {
  const [error, setError] = useState<ApiError>();
  const existing = service && service !== "new" ? service : null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const price = form.get("price") as string;
    const json = {
      name: form.get("name"),
      duration_min: Number(form.get("duration")),
      price_inr: price === "" ? null : Number(price),
      description: (form.get("description") as string) || null,
    };
    try {
      await (existing
        ? api(`/v1/dashboard/services/${existing.id}`, { method: "PATCH", json })
        : api("/v1/dashboard/services", { json }));
      toast.success("Saved");
      onClose();
      onDone();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <Dialog open={service !== null} onOpenChange={(open) => !open && (setError(undefined), onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{existing ? existing.name : "Add a service"}</DialogTitle>
        </DialogHeader>
        <form key={existing?.id ?? "new"} onSubmit={submit} className="grid gap-3">
          <Field label="Name" htmlFor="svc-name" hint="Customers and Vaani use this name.">
            <Input id="svc-name" name="name" defaultValue={existing?.name} required minLength={2} maxLength={80} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Length (minutes)" htmlFor="svc-duration">
              <Input id="svc-duration" name="duration" type="number" min={5} max={480} step={5} defaultValue={existing?.duration_min ?? 30} required />
            </Field>
            <Field label="Price (₹)" htmlFor="svc-price" hint="Leave empty if it varies.">
              <Input id="svc-price" name="price" type="number" min={0} step="any" defaultValue={existing?.price_inr ?? ""} />
            </Field>
          </div>
          <Field label="Description (optional)" htmlFor="svc-description">
            <Input id="svc-description" name="description" defaultValue={existing?.description ?? ""} maxLength={300} />
          </Field>
          <ErrorNote error={error} />
          <DialogFooter>
            <Button type="submit">Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// Staff ------------------------------------------------------------------------------

function StaffList() {
  const { data: staff, mutate } = useApi<StaffMember[]>("/v1/dashboard/staff");
  const { data: services } = useApi<Service[]>("/v1/dashboard/services");
  const [editing, setEditing] = useState<StaffMember | "new" | null>(null);

  async function toggle(member: StaffMember, active: boolean) {
    try {
      await api(`/v1/dashboard/staff/${member.id}`, { method: "PATCH", json: { active } });
      mutate();
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  }

  const name = (id: string) => services?.find((s) => s.id === id)?.name ?? "";
  return (
    <>
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">The people customers book with, and what each one does.</p>
        <Button onClick={() => setEditing("new")}>
          <Plus /> Add staff
        </Button>
      </div>
      {!staff || !services ? (
        <Skeleton className="h-48" />
      ) : staff.length === 0 ? (
        <Empty title="No staff yet" />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {staff.map((m) => (
            <Card key={m.id} className={m.active ? "" : "opacity-60"}>
              <CardContent className="grid gap-2">
                <div className="flex items-center justify-between gap-2">
                  <button className="text-left font-medium hover:underline" onClick={() => setEditing(m)}>
                    {m.name}
                  </button>
                  <Switch checked={m.active} onCheckedChange={(on) => toggle(m, on)} aria-label={`${m.name} takes bookings`} />
                </div>
                <p className="text-sm text-muted-foreground">
                  {m.service_ids.length ? m.service_ids.map(name).join(", ") : "No services yet: can't be booked"}
                </p>
                <p className="text-xs text-muted-foreground">{m.custom_hours ? "Own hours (see Hours tab)" : "Business hours"}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <StaffDialog member={editing} services={services ?? []} onClose={() => setEditing(null)} onDone={() => mutate()} />
    </>
  );
}

function StaffDialog({
  member,
  services,
  onClose,
  onDone,
}: {
  member: StaffMember | "new" | null;
  services: Service[];
  onClose: () => void;
  onDone: () => void;
}) {
  const existing = member && member !== "new" ? member : null;
  return (
    <Dialog open={member !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{existing ? existing.name : "Add staff"}</DialogTitle>
        </DialogHeader>
        <StaffForm key={existing?.id ?? "new"} existing={existing} services={services} onClose={onClose} onDone={onDone} />
      </DialogContent>
    </Dialog>
  );
}

function StaffForm({
  existing,
  services,
  onClose,
  onDone,
}: {
  existing: StaffMember | null;
  services: Service[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [chosen, setChosen] = useState<string[]>(existing?.service_ids ?? []);
  const [error, setError] = useState<ApiError>();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const json = { name: new FormData(event.currentTarget).get("name"), service_ids: chosen };
    try {
      await (existing
        ? api(`/v1/dashboard/staff/${existing.id}`, { method: "PATCH", json })
        : api("/v1/dashboard/staff", { json }));
      toast.success("Saved");
      onClose();
      onDone();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3">
      <Field label="Name" htmlFor="staff-name">
        <Input id="staff-name" name="name" defaultValue={existing?.name} placeholder="Dr. Lakshmi Reddy" required minLength={2} maxLength={80} />
      </Field>
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Does these services</legend>
        <div className="grid gap-2">
          {services.filter((s) => s.active).map((s) => (
            <Label key={s.id} className="font-normal">
              <Checkbox
                checked={chosen.includes(s.id)}
                onCheckedChange={(on) => setChosen(on ? [...chosen, s.id] : chosen.filter((id) => id !== s.id))}
              />
              {s.name}
            </Label>
          ))}
        </div>
      </fieldset>
      <ErrorNote error={error} />
      <DialogFooter>
        <Button type="submit">Save</Button>
      </DialogFooter>
    </form>
  );
}

// Days off ---------------------------------------------------------------------------

function DaysOff() {
  const { data, mutate } = useApi<Blocked[]>("/v1/dashboard/blocked");
  const { data: staff } = useApi<StaffMember[]>("/v1/dashboard/staff");
  const [error, setError] = useState<ApiError>();

  async function add(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setError(undefined);
    try {
      await api("/v1/dashboard/blocked", {
        json: {
          start_date: form.get("start"),
          end_date: form.get("end") || form.get("start"),
          staff_id: form.get("staff") || null,
          reason: form.get("reason") || null,
        },
      });
      formEl.reset();
      toast.success("Added. Vaani won't offer those days.");
      mutate();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  async function remove(id: string) {
    await api(`/v1/dashboard/blocked/${id}`, { method: "DELETE" });
    mutate();
  }

  return (
    <div className="grid max-w-3xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Add days off</CardTitle>
          <CardDescription>{"Holidays for everyone, or leave for one person. Existing bookings aren't moved."}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={add} className="grid gap-3 sm:grid-cols-2">
            <Field label="From" htmlFor="start">
              <Input
                id="start"
                name="start"
                type="date"
                required
                onChange={(e) => {
                  // "To" can't be before "From".
                  const end = e.currentTarget.form?.elements.namedItem("end");
                  if (end instanceof HTMLInputElement) end.min = e.currentTarget.value;
                }}
              />
            </Field>
            <Field label="To (optional)" htmlFor="end">
              <Input id="end" name="end" type="date" data-error="The last day can't be before the first." />
            </Field>
            <Field label="Who" htmlFor="staff">
              <NativeSelect id="staff" name="staff" className="w-full">
                <option value="">Everyone (business closed)</option>
                {staff?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Reason (optional)" htmlFor="reason">
              <Input id="reason" name="reason" placeholder="Diwali" maxLength={120} />
            </Field>
            <div className="sm:col-span-2">
              <ErrorNote error={error} />
              <Button type="submit" className="mt-1">
                Add
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      {!data ? (
        <Skeleton className="h-24" />
      ) : data.length === 0 ? (
        <Empty title="No upcoming days off" />
      ) : (
        <ul className="divide-y rounded-xl ring-1 ring-foreground/10">
          {data.map((b) => (
            <li key={b.id} className="flex items-center justify-between gap-2 px-4 py-2.5 text-sm">
              <div>
                <p className="font-medium">
                  {dayLabel(b.start_date)}
                  {b.end_date !== b.start_date && ` – ${dayLabel(b.end_date)}`}
                </p>
                <p className="text-muted-foreground">
                  {b.staff ?? "Everyone"}
                  {b.reason && ` · ${b.reason}`}
                </p>
              </div>
              <Button variant="ghost" size="icon" aria-label="Remove" onClick={() => remove(b.id)}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
