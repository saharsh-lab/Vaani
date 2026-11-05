import type { MetadataRoute } from "next";

import { SITE } from "@/lib/site";

// Public pages only; the dashboard is behind a login and kept out of search results.
export default function sitemap(): MetadataRoute.Sitemap {
  const page = (path: string, priority: number, changeFrequency: "weekly" | "monthly" | "yearly") => ({
    url: `${SITE.url}${path}`,
    changeFrequency,
    priority,
  });
  return [
    page("/", 1, "weekly"),
    page(`/c/${SITE.demoSlug}`, 0.8, "weekly"),
    page("/signup", 0.6, "monthly"),
    page("/login", 0.3, "yearly"),
    page("/privacy", 0.2, "yearly"),
    page("/terms", 0.2, "yearly"),
  ];
}
