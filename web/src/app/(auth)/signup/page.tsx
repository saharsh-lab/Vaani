import type { Metadata } from "next";

import SignupForm from "./form";

export const metadata: Metadata = {
  title: "Set up your business",
  description:
    "Create a Vaani account for your clinic or salon: add services and hours, and an AI receptionist starts answering in Telugu, Hindi and English.",
  alternates: { canonical: "/signup" },
};

export default function Page() {
  return <SignupForm />;
}
