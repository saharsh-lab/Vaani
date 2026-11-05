import Link from "next/link";

import { Logo } from "@/components/site-chrome";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <Logo className="mb-6 justify-center" />
        {children}
        <nav aria-label="Legal" className="mt-6 flex justify-center gap-4 text-xs text-muted-foreground">
          <Link href="/privacy" className="hover:text-foreground">
            Privacy policy
          </Link>
          <Link href="/terms" className="hover:text-foreground">
            Terms of service
          </Link>
        </nav>
      </div>
    </main>
  );
}
