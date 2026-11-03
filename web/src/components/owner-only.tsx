"use client";

import { useSession } from "@/components/session";

/** Pages only the business owner sees. The API enforces this too. */
export function OwnerOnly({ children }: { children: React.ReactNode }) {
  const { user } = useSession();
  if (user.role !== "owner") {
    return <p className="text-sm text-muted-foreground">Only the business owner can see this page.</p>;
  }
  return <>{children}</>;
}
