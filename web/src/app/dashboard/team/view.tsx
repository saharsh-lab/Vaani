"use client";

import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorNote, Field, NativeSelect, PageHeader } from "@/components/kit";
import { OwnerOnly } from "@/components/owner-only";
import { useSession } from "@/components/session";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, useApi } from "@/lib/api";
import type { Role, User } from "@/lib/types";

export default function TeamPage() {
  return (
    <OwnerOnly>
      <Team />
    </OwnerOnly>
  );
}

function Team() {
  const { user: me } = useSession();
  const { data, mutate } = useApi<User[]>("/v1/dashboard/team");
  const [adding, setAdding] = useState(false);

  async function update(member: User, json: { active?: boolean; role?: Role }) {
    try {
      await api(`/v1/dashboard/team/${member.id}`, { method: "PATCH", json });
      mutate();
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  }

  return (
    <>
      <PageHeader
        title="Team"
        description="Who can sign in. Staff see the day's bookings and the callback list; owners see everything."
        actions={
          <Button onClick={() => setAdding(true)}>
            <Plus /> Add person
          </Button>
        }
      />
      {!data ? (
        <Skeleton className="h-48" />
      ) : (
        <div className="rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Can sign in</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((m) => {
                const self = m.id === me.id;
                return (
                  <TableRow key={m.id}>
                    <TableCell>
                      <div className="font-medium">
                        {m.name ?? m.email} {self && <Badge variant="secondary">You</Badge>}
                      </div>
                      <div className="text-xs text-muted-foreground">{m.email}</div>
                    </TableCell>
                    <TableCell>
                      <NativeSelect
                        value={m.role}
                        disabled={self}
                        onChange={(e) => update(m, { role: e.target.value as Role })}
                        aria-label={`Role for ${m.name ?? m.email}`}
                      >
                        <option value="staff">Staff</option>
                        <option value="owner">Owner</option>
                      </NativeSelect>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={m.active}
                        disabled={self}
                        onCheckedChange={(on) => update(m, { active: on })}
                        aria-label={`${m.name ?? m.email} can sign in`}
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <AddMember open={adding} onOpenChange={setAdding} onDone={() => mutate()} />
    </>
  );
}

function AddMember({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => void }) {
  const [error, setError] = useState<ApiError>();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/v1/dashboard/team", {
        json: {
          name: form.get("name"),
          email: form.get("email"),
          password: form.get("password"),
          role: form.get("role"),
        },
      });
      toast.success("Added. Share the email and temporary password with them privately.");
      onOpenChange(false);
      onDone();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (setError(undefined), onOpenChange(o))}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a person</DialogTitle>
          <DialogDescription>They sign in with this email and the temporary password you set.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <Field label="Name" htmlFor="m-name">
            <Input id="m-name" name="name" required maxLength={80} />
          </Field>
          <Field label="Email" htmlFor="m-email">
            <Input id="m-email" name="email" type="email" autoComplete="off" required maxLength={254} />
          </Field>
          <Field label="Temporary password" htmlFor="m-password" hint="At least 8 characters.">
            <Input id="m-password" name="password" type="text" minLength={8} maxLength={200} required autoComplete="off" />
          </Field>
          <Field label="Role" htmlFor="m-role">
            <NativeSelect id="m-role" name="role" defaultValue="staff" className="w-full">
              <option value="staff">Staff: bookings and callbacks</option>
              <option value="owner">Owner: everything</option>
            </NativeSelect>
          </Field>
          <ErrorNote error={error} />
          <DialogFooter>
            <Button type="submit">Add</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
