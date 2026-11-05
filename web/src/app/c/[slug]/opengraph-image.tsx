import { ImageResponse } from "next/og";

import { getClinic } from "@/lib/clinic";
import { Preview } from "@/lib/og";

export const alt = "Book an appointment online";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// The preview WhatsApp, Google and social apps show when a clinic shares its link.
export default async function ClinicImage({ params }: { params: Promise<{ slug: string }> }) {
  const clinic = await getClinic((await params).slug);
  return new ImageResponse(
    clinic ? (
      <Preview
        eyebrow={clinic.type}
        title={clinic.name}
        subtitle={clinic.address ? `Book online · ${clinic.address}` : "Book an appointment online, any time"}
      />
    ) : (
      <Preview title="Book an appointment" subtitle="Online booking by Vaani" />
    ),
    size,
  );
}
