import { CalendarCheck, Headset, LayoutDashboard, MessageCircle, Mic } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import { buttonVariants } from "@/components/ui/button";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: { absolute: SITE.title },
  alternates: { canonical: "/" },
};

const STEPS = [
  {
    title: "Add your services and hours",
    text: "Prices, durations, doctors or stylists, days off. About five minutes, and you can change it any time.",
  },
  {
    title: "Share your booking link",
    text: "Put it on Google, Instagram and WhatsApp. Customers book a free time or tap “Talk to us”.",
  },
  {
    title: "Vaani answers and books",
    text: "In the customer's language, from your real calendar. Anything it can't handle comes to your team.",
  },
];

const FEATURES = [
  {
    icon: Mic,
    title: "Talk-to-us button",
    text: "Customers speak to Vaani from your website. It answers questions, checks free times and books, and replies in the language they speak.",
  },
  {
    icon: MessageCircle,
    title: "WhatsApp",
    text: "Text messages and voice notes on your WhatsApp Business number, answered the same way.",
  },
  {
    icon: CalendarCheck,
    title: "Online booking page",
    text: "Every free time for each service, with no app to install and no sign-up for your customers.",
  },
  {
    icon: LayoutDashboard,
    title: "Dashboard for owners and staff",
    text: "Today's bookings, a callback queue, every conversation with its transcript, and what it cost.",
  },
];

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main className="flex-1">
        <section className="mx-auto w-full max-w-5xl px-4 pt-16 pb-12 sm:pt-24">
          <p className="text-sm font-medium text-primary">AI receptionist for clinics and salons</p>
          <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Never miss a customer because the phone was busy.
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-muted-foreground text-pretty">
            Vaani answers your website calls and WhatsApp in Telugu, Hindi and English, books appointments from your
            real schedule, and hands tricky conversations to your team.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/signup" className={buttonVariants({ size: "lg" })}>
              Set up your business
            </Link>
            <Link href={`/c/${SITE.demoSlug}`} className={buttonVariants({ size: "lg", variant: "outline" })}>
              See the demo clinic
            </Link>
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            Or{" "}
            <a href={`${SITE.apiUrl}/voice/${SITE.demoSlug}`} className="text-primary underline underline-offset-4 hover:decoration-2">
              talk to the demo clinic&apos;s receptionist
            </a>{" "}
            in your browser. Try “Repu evening RCT consultation ki appointment kavali”.
          </p>
        </section>

        <section aria-labelledby="how" className="border-y bg-muted/40">
          <div className="mx-auto w-full max-w-5xl px-4 py-14">
            <h2 id="how" className="text-2xl font-semibold tracking-tight">
              How it works
            </h2>
            <ol className="mt-8 grid gap-6 sm:grid-cols-3">
              {STEPS.map((step, i) => (
                <li key={step.title} className="grid content-start gap-2">
                  <span className="flex size-8 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground">
                    {i + 1}
                  </span>
                  <h3 className="font-medium">{step.title}</h3>
                  <p className="text-sm text-muted-foreground">{step.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section aria-labelledby="features" className="mx-auto w-full max-w-5xl px-4 py-14">
          <h2 id="features" className="text-2xl font-semibold tracking-tight">
            One receptionist, everywhere your customers are
          </h2>
          <ul className="mt-8 grid gap-4 sm:grid-cols-2">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="rounded-xl border p-5">
                <Icon className="size-5 text-primary" aria-hidden />
                <h3 className="mt-3 font-medium">{title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{text}</p>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="team" className="mx-auto w-full max-w-5xl px-4 pb-16">
          <div className="flex flex-col gap-5 rounded-2xl bg-primary px-6 py-10 text-primary-foreground sm:flex-row sm:items-center sm:justify-between sm:px-10">
            <div className="max-w-xl">
              <h2 id="team" className="flex items-center gap-2 text-xl font-semibold">
                <Headset className="size-5" aria-hidden /> Your team stays in charge
              </h2>
              <p className="mt-2 text-sm opacity-90">
                Vaani only quotes prices and policies you&apos;ve given it, reads every booking back before confirming,
                doesn&apos;t give medical advice, and passes upset customers to a person.
              </p>
            </div>
            <Link
              href="/signup"
              className={buttonVariants({ size: "lg", variant: "secondary", className: "shrink-0" })}
            >
              Get started
            </Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
