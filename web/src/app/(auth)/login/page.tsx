import type { Metadata } from "next";

import LoginForm from "./form";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to your Vaani dashboard to see bookings, callbacks and conversations.",
  alternates: { canonical: "/login" },
};

export default function Page() {
  return <LoginForm />;
}
