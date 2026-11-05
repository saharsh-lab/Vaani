import type { MetadataRoute } from "next";

import { SITE } from "@/lib/site";

// Lets owners and staff add the dashboard to their phone's home screen.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Vaani",
    short_name: "Vaani",
    description: SITE.description,
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: SITE.brandColor,
    icons: [
      { src: "/icon.svg", type: "image/svg+xml", sizes: "any" },
      { src: "/apple-icon", type: "image/png", sizes: "180x180" },
    ],
  };
}
