// Header and footer for the public pages (home, legal pages, 404, sign-in).

import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <Link href="/" className={cn("flex items-center gap-2 font-semibold", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- a 1 KB SVG, nothing to optimise */}
      <img src="/icon.svg" alt="" width={24} height={24} className="size-6" />
      Vaani
    </Link>
  );
}

export function SiteHeader() {
  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between gap-4 px-4">
        <Logo />
        <nav aria-label="Main" className="flex items-center gap-1 text-sm">
          <Link href={`/c/${SITE.demoSlug}`} className="hidden rounded-md px-3 py-2 text-muted-foreground hover:text-foreground sm:block">
            Demo clinic
          </Link>
          <Link href="/login" className="rounded-md px-3 py-2 text-muted-foreground hover:text-foreground">
            Sign in
          </Link>
          <Link href="/signup" className={buttonVariants({ size: "sm" })}>
            Get started
          </Link>
        </nav>
      </div>
    </header>
  );
}

const FOOTER_LINKS = [
  { href: `/c/${SITE.demoSlug}`, label: "Demo clinic" },
  { href: "/signup", label: "Set up your business" },
  { href: "/login", label: "Sign in" },
  { href: "/privacy", label: "Privacy policy" },
  { href: "/terms", label: "Terms of service" },
];

export function SiteFooter({ className }: { className?: string }) {
  return (
    <footer className={cn("border-t", className)}>
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <Logo className="text-foreground" />
        <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-2">
          {FOOTER_LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-foreground">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
