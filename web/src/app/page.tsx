import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-16">
      <p className="text-sm font-medium text-primary">Vaani</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
        A receptionist that never misses a call.
      </h1>
      <p className="mt-4 max-w-xl text-muted-foreground">
        Vaani answers phone calls and WhatsApp in Telugu, Hindi and English, books appointments
        from your real schedule, and hands tricky calls to your team.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/signup" className={buttonVariants({ size: "lg" })}>
          Set up your business
        </Link>
        <Link href="/login" className={buttonVariants({ size: "lg", variant: "outline" })}>
          Sign in
        </Link>
        <Link href="/c/sri-dental" className={buttonVariants({ size: "lg", variant: "ghost" })}>
          See the demo clinic
        </Link>
      </div>
    </main>
  );
}
