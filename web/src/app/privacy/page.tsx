import type { Metadata } from "next";
import Link from "next/link";

import { LegalPage } from "@/components/legal-page";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Privacy policy",
  description: "What Vaani collects when businesses and their customers use it, why, who processes it, and your rights.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  const email = SITE.contactEmail;
  return (
    <LegalPage title="Privacy policy" updated="5 November 2026">
      <p>
        Vaani is an AI receptionist that businesses such as clinics and salons use to answer their customers on
        website calls, WhatsApp and an online booking page. This policy explains what we collect, why, who
        processes it, how long we keep it, and the choices you have. It is written to meet India&apos;s Digital
        Personal Data Protection Act, 2023.
      </p>

      <h2 id="roles">Who is responsible for your data</h2>
      <ul>
        <li>
          <strong>If you run a business on Vaani</strong> (an owner or staff member), we decide how your account
          data is used and are responsible for it.
        </li>
        <li>
          <strong>If you are a customer of a business</strong> (you called, messaged or booked with a clinic or
          salon), that business decides how your data is used. We process it for them, only to run their
          receptionist. Questions about a booking or your records go to the business first; we will help them
          answer.
        </li>
      </ul>

      <h2 id="collect">What we collect</h2>
      <ul>
        <li>
          <strong>Business accounts:</strong> your name, email address, role, and a scrambled (hashed) version of
          your password. We never store the password itself. Also the business details you enter: name, address,
          phone, opening hours, services, prices, staff names and FAQs.
        </li>
        <li>
          <strong>Bookings:</strong> the name and mobile number given for the booking, the service, time and staff
          member.
        </li>
        <li>
          <strong>Conversations:</strong> a text transcript of each call and chat, the actions the assistant took
          (such as checking free times or booking), the language detected, and its duration and cost.
        </li>
        <li>
          <strong>Voice:</strong> your voice is streamed to our speech provider so it can be turned into text, and
          the assistant&apos;s replies are turned back into speech. We do not record or keep call audio. WhatsApp
          voice notes are fetched from WhatsApp, transcribed, and not kept; only the text is saved.
        </li>
        <li>
          <strong>Technical data:</strong> your IP address, used briefly to limit abuse (such as too many calls or
          bookings from one connection), and error reports. Phone numbers are masked in our logs.
        </li>
      </ul>

      <h2 id="use">Why we use it</h2>
      <ul>
        <li>To answer customers, check availability and make, change or cancel bookings for the business.</li>
        <li>To show the business its bookings, conversations and callback requests in the dashboard.</li>
        <li>To keep the service secure, prevent abuse, fix errors and measure quality and cost.</li>
      </ul>
      <p>
        We do not sell personal data, show advertising, or use it to build profiles for marketing.
      </p>

      <h2 id="processors">Who processes it for us</h2>
      <p>We use these providers to run Vaani. Each receives only what it needs for its part:</p>
      <ul>
        <li>
          <strong>Google (Gemini API):</strong> conversation text, to understand requests and write replies, and
          FAQ text, to search it in any language. Depending on the service tier, Google may keep inputs for a
          limited time to detect abuse, or use them to improve its products, under Google&apos;s terms.
        </li>
        <li>
          <strong>Sarvam AI:</strong> voice audio, to turn speech into text and text into speech.
        </li>
        <li>
          <strong>LiveKit:</strong> carries the live audio of website calls between your browser and the assistant.
        </li>
        <li>
          <strong>Meta (WhatsApp):</strong> delivers WhatsApp messages between customers and the business.
        </li>
        <li>
          <strong>Hosting and monitoring:</strong> our servers, database and website hosts store the data, and an
          error-tracking service receives error reports with personal details removed.
        </li>
      </ul>
      <p>Some of these providers process data outside India.</p>

      <h2 id="cookies">Cookies</h2>
      <p>
        The dashboard sets one cookie to keep you signed in. The site remembers your light or dark theme in your
        browser. We use no advertising or tracking cookies, and customers booking or calling need no cookies at all.
      </p>

      <h2 id="retention">How long we keep it</h2>
      <p>
        We keep a business&apos;s data, including its bookings and conversation transcripts, while it uses Vaani.
        When a business closes its account, or asks us to delete data, we delete it within 30 days, apart from
        anything the law requires us to keep.
      </p>

      <h2 id="rights">Your rights</h2>
      <p>
        You can ask for a summary of the personal data held about you, have it corrected or completed, have it
        erased, withdraw consent, and nominate someone to exercise these rights for you. Customers of a business
        can ask that business, or email us at <a href={`mailto:${email}`}>{email}</a> and we will pass it on and
        help. We reply within 30 days. If you are not satisfied, you can complain to the Data Protection Board of
        India.
      </p>

      <h2 id="security">Security</h2>
      <p>
        Connections are encrypted (HTTPS). Each business can only ever see its own data, which the database itself
        enforces. Passwords are hashed and dashboard actions are limited by role. No system is perfectly secure; if
        a breach affects your data, we will tell you and the Data Protection Board as the law requires.
      </p>

      <h2 id="children">Children</h2>
      <p>
        Vaani is meant for adults. A parent or guardian may book an appointment for a child; please don&apos;t give
        more about the child than the booking needs.
      </p>

      <h2 id="changes">Changes and contact</h2>
      <p>
        If we change this policy, we will update the date at the top, and tell business account holders by email
        about important changes. Questions or requests:{" "}
        <a href={`mailto:${email}`}>{email}</a>. See also our <Link href="/terms">terms of service</Link>.
      </p>
    </LegalPage>
  );
}
