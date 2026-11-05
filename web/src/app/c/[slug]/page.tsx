import type { Metadata } from "next";
import { Suspense } from "react";

import { getClinic } from "@/lib/clinic";
import { joinAnd, languageName } from "@/lib/format";

import View from "./view";

// The page loads the business in the browser, so a navigation here waits for it by
// design. Client Components can't set this, so this server wrapper does.
export const instant = false;

export async function generateMetadata({ params }: PageProps<"/c/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const clinic = await getClinic(slug);
  if (!clinic) return { title: "Book an appointment", robots: { index: false } };
  const languages = joinAnd(clinic.languages.map(languageName));
  const rest = `See prices and free times, or talk to our assistant in ${languages}.`;
  const withAddress = `Book online with ${clinic.name}, ${clinic.address}. ${rest}`;
  const description = clinic.address && withAddress.length <= 160 ? withAddress : `Book online with ${clinic.name}. ${rest}`;
  return {
    title: `${clinic.name}: book an appointment`,
    description,
    alternates: { canonical: `/c/${clinic.slug}` },
    openGraph: {
      type: "website",
      siteName: "Vaani",
      title: `${clinic.name}: book an appointment`,
      description,
      url: `/c/${clinic.slug}`,
    },
  };
}

export default function Page() {
  return (
    <Suspense>
      <View />
    </Suspense>
  );
}
