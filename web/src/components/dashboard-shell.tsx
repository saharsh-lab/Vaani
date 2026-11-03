"use client";

import {
  BookOpen,
  CalendarDays,
  Cog,
  Headset,
  KeyRound,
  LayoutDashboard,
  LogOut,
  MessagesSquare,
  Radio,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { SWRConfig } from "swr";

import { ErrorNote, Field } from "@/components/kit";
import { SessionProvider } from "@/components/session";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, useApi } from "@/lib/api";
import type { Handoff, Me, Role } from "@/lib/types";
import { cn } from "@/lib/utils";

const NAV: { href: string; label: string; icon: typeof Cog; roles: Role[] }[] = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard, roles: ["owner"] },
  { href: "/dashboard/bookings", label: "Bookings", icon: CalendarDays, roles: ["owner", "staff"] },
  { href: "/dashboard/handoffs", label: "Callbacks", icon: Headset, roles: ["owner", "staff"] },
  { href: "/dashboard/conversations", label: "Conversations", icon: MessagesSquare, roles: ["owner"] },
  { href: "/dashboard/knowledge", label: "Knowledge base", icon: BookOpen, roles: ["owner"] },
  { href: "/dashboard/settings", label: "Settings", icon: Cog, roles: ["owner"] },
  { href: "/dashboard/team", label: "Team", icon: Users, roles: ["owner"] },
  { href: "/dashboard/channels", label: "Channels", icon: Radio, roles: ["owner"] },
];

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: me, error } = useApi<Me>("/v1/dashboard/me");
  const [changingPassword, setChangingPassword] = useState(false);
  // Polled so the badge updates when the agent hands a call over.
  const { data: waiting } = useApi<Handoff[]>(me ? "/v1/dashboard/handoffs" : null, {
    refreshInterval: 30_000,
  });

  useEffect(() => {
    if (error?.status === 401) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [error, pathname, router]);

  if (!me) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        {error && error.status !== 401 ? (
          <p className="text-sm text-destructive">{error.message}</p>
        ) : (
          <Skeleton className="h-8 w-48" />
        )}
      </div>
    );
  }

  async function signOut() {
    await api("/v1/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  const items = NAV.filter((item) => item.roles.includes(me.user.role));
  const openCallbacks = waiting?.filter((h) => h.status === "open").length ?? 0;

  return (
    <SWRConfig
      value={{
        onError: (err: ApiError) => {
          if (err.status === 401) router.replace("/login");
        },
      }}
    >
      <SessionProvider value={me}>
        <div className="flex flex-1 flex-col md:flex-row">
          <aside className="border-b bg-sidebar md:sticky md:top-0 md:flex md:h-dvh md:w-60 md:shrink-0 md:flex-col md:border-r md:border-b-0">
            <div className="flex items-center justify-between gap-2 px-4 py-3 md:block md:py-5">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{me.business.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {me.user.name ?? me.user.email} · {me.user.role === "owner" ? "Owner" : "Staff"}
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={signOut} className="md:hidden">
                <LogOut /> Sign out
              </Button>
            </div>
            <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible md:pb-0">
              {items.map(({ href, label, icon: Icon }) => {
                const active = href === "/dashboard" ? pathname === href : pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground",
                      active && "bg-sidebar-accent font-medium text-sidebar-foreground",
                    )}
                  >
                    <Icon className="size-4" />
                    {label}
                    {href.endsWith("handoffs") && openCallbacks > 0 && (
                      <span className="ml-auto rounded-full bg-amber-500 px-1.5 text-xs font-medium text-white">
                        {openCallbacks}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>
            <div className="mt-auto hidden px-2 py-4 md:grid md:gap-1">
              <Button variant="ghost" size="sm" onClick={() => setChangingPassword(true)} className="w-full justify-start">
                <KeyRound /> Change password
              </Button>
              <Button variant="ghost" size="sm" onClick={signOut} className="w-full justify-start">
                <LogOut /> Sign out
              </Button>
            </div>
          </aside>
          <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
        </div>
        <PasswordDialog open={changingPassword} onOpenChange={setChangingPassword} />
      </SessionProvider>
    </SWRConfig>
  );
}

function PasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (form.get("new_password") !== form.get("confirm")) {
      setError(new ApiError("The new passwords don't match", 422, null));
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await api("/v1/auth/password", {
        json: { current_password: form.get("current_password"), new_password: form.get("new_password") },
      });
      toast.success("Password changed");
      onOpenChange(false);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (setError(undefined), onOpenChange(o))}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change password</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <Field label="Current password" htmlFor="current_password">
            <Input id="current_password" name="current_password" type="password" autoComplete="current-password" required />
          </Field>
          <Field label="New password" htmlFor="new_password" hint="At least 8 characters.">
            <Input id="new_password" name="new_password" type="password" autoComplete="new-password" minLength={8} required />
          </Field>
          <Field label="New password again" htmlFor="confirm">
            <Input id="confirm" name="confirm" type="password" autoComplete="new-password" minLength={8} required />
          </Field>
          <ErrorNote error={error} />
          <DialogFooter>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Change password"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
