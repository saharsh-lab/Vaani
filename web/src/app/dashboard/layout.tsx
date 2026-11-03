import { Suspense } from "react";

import { DashboardShell } from "@/components/dashboard-shell";

// The dashboard renders in the browser (it reads the URL and the session), so it
// sits inside Suspense: Next.js prerenders an empty shell and streams the rest.
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="flex-1" />}>
      <DashboardShell>{children}</DashboardShell>
    </Suspense>
  );
}
