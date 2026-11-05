import type { Metadata } from "next";
import Link from "next/link";

import { LegalPage } from "@/components/legal-page";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Terms of service",
  description: "The terms for businesses using Vaani and for customers who call, message or book through it.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  const email = SITE.contactEmail;
  return (
    <LegalPage title="Terms of service" updated="5 November 2026">
      <p>
        These terms apply when you use Vaani: as a business that sets up an AI receptionist (an owner or staff
        member), or as a customer who calls, messages or books with a business through it. By using Vaani you agree
        to them.
      </p>

      <h2 id="service">What Vaani does</h2>
      <p>
        Vaani answers a business&apos;s customers on website calls, WhatsApp and an online booking page, in Telugu,
        Hindi and English. It answers questions from the information the business provides, checks the
        business&apos;s schedule, makes, changes and cancels bookings, and passes conversations to the
        business&apos;s team when needed. Vaani is in early access: features may change, and we may add limits to
        keep it reliable.
      </p>

      <h2 id="ai">The assistant can make mistakes</h2>
      <ul>
        <li>
          Vaani is an AI. It can mishear speech or misunderstand a request. It reads bookings back before confirming
          them, and the business should check its bookings in the dashboard.
        </li>
        <li>
          <strong>It does not give medical, legal or financial advice</strong>, and is not for emergencies. In a
          medical emergency, call 108 or go to the nearest hospital.
        </li>
        <li>
          Prices, policies and hours come from the business. The business, not Vaani, is responsible for its
          services and for honouring the bookings it accepts.
        </li>
      </ul>

      <h2 id="business">If you run a business on Vaani</h2>
      <ul>
        <li>Keep your account details and your staff&apos;s logins secure, and give staff only the access they need.</li>
        <li>
          Keep your services, prices, hours and FAQs accurate. The assistant tells customers what you have entered.
        </li>
        <li>
          Tell your customers that an AI assistant answers on your behalf and link to this site&apos;s{" "}
          <Link href="/privacy">privacy policy</Link>, for example on your website or booking page.
        </li>
        <li>
          Use Vaani lawfully: no spam, no misleading customers, and nothing that breaks WhatsApp&apos;s or other
          providers&apos; rules.
        </li>
      </ul>

      <h2 id="customers">If you call, message or book</h2>
      <ul>
        <li>Give your real name and a mobile number you use, so the business can reach you about the booking.</li>
        <li>
          Don&apos;t make bookings you don&apos;t intend to keep, book for others without their permission, or try
          to overload or misuse the service. We limit how many calls and bookings come from one connection.
        </li>
        <li>To change or cancel a booking, contact the business, by calling or through its assistant.</li>
      </ul>

      <h2 id="fees">Fees</h2>
      <p>
        Vaani is free during early access. If we introduce paid plans, we will tell account holders at least 30 days
        before any charge, and you can close your account instead.
      </p>

      <h2 id="data">Your data</h2>
      <p>
        A business owns the information it enters and the bookings and conversations with its customers. We use it
        only to provide Vaani, as described in the <Link href="/privacy">privacy policy</Link>.
      </p>

      <h2 id="ending">Closing an account</h2>
      <p>
        A business can stop using Vaani at any time and ask us to delete its data. We may suspend or close an
        account that breaks these terms or puts the service or other users at risk, and will tell you why where we
        can.
      </p>

      <h2 id="liability">Liability</h2>
      <p>
        We work to keep Vaani accurate and available, but provide it as it is, without guarantees that it will always
        be available or error-free. As far as the law allows, we are not liable for indirect losses such as lost
        business, and our total liability to a business is limited to what it paid us in the 12 months before the
        claim. Nothing in these terms limits rights you have under consumer protection law.
      </p>

      <h2 id="law">Law and changes</h2>
      <p>
        These terms are governed by the laws of India, and disputes go to the courts of Hyderabad, Telangana. If we
        change these terms, we will update the date at the top and tell account holders about important changes
        before they apply.
      </p>

      <h2 id="contact">Contact</h2>
      <p>
        Questions about these terms: <a href={`mailto:${email}`}>{email}</a>.
      </p>
    </LegalPage>
  );
}
