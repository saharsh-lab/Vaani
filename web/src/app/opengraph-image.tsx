import { ImageResponse } from "next/og";

import { Preview } from "@/lib/og";

export const alt = "Vaani: the AI receptionist for clinics and salons";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <Preview
      title="The receptionist that never misses a call"
      subtitle="Website calls, WhatsApp and online booking in Telugu, Hindi and English"
    />,
    size,
  );
}
