import type { Metadata } from "next";
import { Suspense } from "react";

import { DashboardShell } from "@/components/dashboard-shell";

// The dashboard renders in the browser (it reads the URL and the session), so it
// sits inside Suspense: Next.js prerenders an empty shell and streams the rest.
// Pages appear only once the session has loaded, so navigations into the
// dashboard wait for it by design. This (and each page's own `instant = false`)
// opts the section out of Next's instant-navigation and static-shell validation;
// the rest of the app is still validated.
export const instant = false;

// Private to each business: never in search results.
export const metadata: Metadata = {
  title: { default: "Dashboard", template: "%s · Vaani dashboard" },
  robots: { index: false, follow: false },
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="flex-1" />}>
      <DashboardShell>{children}</DashboardShell>
    </Suspense>
  );
}
