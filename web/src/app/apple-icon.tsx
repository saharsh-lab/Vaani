import { ImageResponse } from "next/og";

import { Mark } from "@/lib/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

// iOS rounds the corners itself, so the icon fills the whole square.
export default function AppleIcon() {
  return new ImageResponse(<Mark size={180} square />, size);
}
