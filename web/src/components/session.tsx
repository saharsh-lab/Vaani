"use client";

import { createContext, useContext } from "react";

import type { Me } from "@/lib/types";

const SessionContext = createContext<Me | null>(null);

export const SessionProvider = SessionContext.Provider;

/** The signed-in user and their business. Only usable inside the dashboard. */
export function useSession(): Me {
  const me = useContext(SessionContext);
  if (!me) throw new Error("useSession must be used inside the dashboard layout");
  return me;
}

export function useIsOwner(): boolean {
  return useSession().user.role === "owner";
}
