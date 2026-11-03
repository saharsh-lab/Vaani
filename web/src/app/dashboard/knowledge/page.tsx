"use client";

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Empty, ErrorNote, Field, PageHeader } from "@/components/kit";
import { OwnerOnly } from "@/components/owner-only";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, useApi } from "@/lib/api";
import type { Faq } from "@/lib/types";

export default function KnowledgePage() {
  return (
    <OwnerOnly>
      <Knowledge />
    </OwnerOnly>
  );
}

function Knowledge() {
  const { data, mutate } = useApi<Faq[]>("/v1/dashboard/faqs");
  const [editing, setEditing] = useState<Faq | "new" | null>(null);

  async function remove(faq: Faq) {
    if (!window.confirm(`Delete "${faq.title}"? Vaani will stop using it.`)) return;
    try {
      await api(`/v1/dashboard/faqs/${faq.id}`, { method: "DELETE" });
      toast.success("Deleted");
      mutate();
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  }

  return (
    <>
      <PageHeader
        title="Knowledge base"
        description="What Vaani can tell customers beyond hours, prices and bookings: parking, payment, policies, what to bring. Changes apply to the next conversation."
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus /> Add answer
          </Button>
        }
      />
      {!data ? (
        <Skeleton className="h-64" />
      ) : data.length === 0 ? (
        <Empty title="No answers yet">Add the questions customers ask most, like parking or payment methods.</Empty>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.map((faq) => (
            <Card key={faq.id}>
              <CardHeader className="flex flex-row items-start justify-between gap-2">
                <CardTitle>{faq.title}</CardTitle>
                <div className="flex shrink-0 gap-1">
                  <Button variant="ghost" size="icon" aria-label={`Edit ${faq.title}`} onClick={() => setEditing(faq)}>
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Delete ${faq.title}`} onClick={() => remove(faq)}>
                    <Trash2 />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-line text-sm text-muted-foreground">{faq.content}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <FaqDialog faq={editing} onClose={() => setEditing(null)} onDone={() => mutate()} />
    </>
  );
}

function FaqDialog({ faq, onClose, onDone }: { faq: Faq | "new" | null; onClose: () => void; onDone: () => void }) {
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);
  const existing = faq && faq !== "new" ? faq : null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const json = { title: form.get("title"), content: form.get("content") };
    setBusy(true);
    try {
      await (existing
        ? api(`/v1/dashboard/faqs/${existing.id}`, { method: "PUT", json })
        : api("/v1/dashboard/faqs", { json }));
      toast.success("Saved. Vaani will use it from the next conversation.");
      onClose();
      onDone();
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={faq !== null} onOpenChange={(open) => !open && (setError(undefined), onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{existing ? "Edit answer" : "Add an answer"}</DialogTitle>
          <DialogDescription>Write it in English; Vaani translates when it replies.</DialogDescription>
        </DialogHeader>
        <form key={existing?.id ?? "new"} onSubmit={submit} className="grid gap-3">
          <Field label="Topic" htmlFor="title">
            <Input id="title" name="title" defaultValue={existing?.title} placeholder="Parking" required minLength={2} />
          </Field>
          <Field label="Question and answer" htmlFor="content" hint="e.g. Q: Is there parking? A: Free two-wheeler parking in front.">
            <Textarea id="content" name="content" rows={6} defaultValue={existing?.content} required minLength={2} />
          </Field>
          <ErrorNote error={error} />
          <DialogFooter>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
