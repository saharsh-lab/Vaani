"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNote, Field } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const me = await api<Me>("/v1/auth/login", {
        json: { email: form.get("email"), password: form.get("password") },
      });
      const next = new URLSearchParams(window.location.search).get("next");
      const fallback = me.user.role === "owner" ? "/dashboard" : "/dashboard/bookings";
      router.replace(next?.startsWith("/dashboard") ? next : fallback);
    } catch (err) {
      setError(err as ApiError);
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>Owners and staff use the same sign-in.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4">
          <Field label="Email" htmlFor="email">
            <Input id="email" name="email" type="email" autoComplete="email" required />
          </Field>
          <Field label="Password" htmlFor="password">
            <Input id="password" name="password" type="password" autoComplete="current-password" required />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            New business?{" "}
            <Link href="/signup" className="text-primary underline-offset-4 hover:underline">
              Set it up
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
