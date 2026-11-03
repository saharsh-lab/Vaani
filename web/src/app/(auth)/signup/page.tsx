"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNote, Field } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { LANGUAGES } from "@/lib/format";

export default function SignupPage() {
  const router = useRouter();
  const [languages, setLanguages] = useState<string[]>(["te", "en"]);
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);

  function toggle(code: string, on: boolean) {
    setLanguages((current) => (on ? [...current, code] : current.filter((c) => c !== code)));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!languages.length) {
      setError(new ApiError("Pick at least one language", 422, null));
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await api("/v1/auth/signup", {
        json: {
          business_name: form.get("business_name"),
          business_type: form.get("business_type"),
          languages,
          owner_name: form.get("owner_name"),
          email: form.get("email"),
          password: form.get("password"),
        },
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(err as ApiError);
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set up your business</CardTitle>
        <CardDescription>About 5 minutes. You can change everything later.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4">
          <Field label="Business name" htmlFor="business_name">
            <Input id="business_name" name="business_name" placeholder="Sri Dental Clinic" required minLength={2} />
          </Field>
          <Field label="Type of business" htmlFor="business_type">
            <Input id="business_type" name="business_type" placeholder="dental clinic, salon, coaching centre" required minLength={2} />
          </Field>
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium">Languages your customers speak</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {Object.entries(LANGUAGES).map(([code, name]) => (
                <Label key={code} className="font-normal">
                  <Checkbox checked={languages.includes(code)} onCheckedChange={(on) => toggle(code, on)} />
                  {name}
                </Label>
              ))}
            </div>
          </fieldset>
          <Field label="Your name" htmlFor="owner_name">
            <Input id="owner_name" name="owner_name" autoComplete="name" required />
          </Field>
          <Field label="Email" htmlFor="email">
            <Input id="email" name="email" type="email" autoComplete="email" required />
          </Field>
          <Field label="Password" htmlFor="password" hint="At least 8 characters.">
            <Input id="password" name="password" type="password" autoComplete="new-password" required minLength={8} />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Already set up?{" "}
            <Link href="/login" className="text-primary underline-offset-4 hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
