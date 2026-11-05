import type { ReactNode } from "react";

import { SiteFooter, SiteHeader } from "@/components/site-chrome";

/** Layout for the privacy policy and terms: readable line length, plain headings. */
export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated {updated}</p>
        <div
          className={[
            "mt-8 text-[15px] leading-7",
            "[&_h2]:mt-10 [&_h2]:scroll-mt-4 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:tracking-tight",
            "[&_p]:mt-3 [&_p]:text-muted-foreground",
            "[&_ul]:mt-3 [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5 [&_ul]:text-muted-foreground",
            "[&_strong]:font-medium [&_strong]:text-foreground",
            "[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 hover:[&_a]:decoration-2",
          ].join(" ")}
        >
          {children}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
