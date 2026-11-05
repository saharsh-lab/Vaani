// The clinic's public details, fetched on the server for page titles and link
// previews. Cached for an hour, so a renamed business updates within the hour.

import { cacheLife } from "next/cache";

import { SERVER_API_URL } from "@/lib/site";
import type { PublicBusiness } from "@/lib/types";

export async function getClinic(slug: string): Promise<PublicBusiness | null> {
  "use cache";
  cacheLife("hours");
  try {
    const res = await fetch(`${SERVER_API_URL}/v1/public/${encodeURIComponent(slug)}`);
    return res.ok ? ((await res.json()) as PublicBusiness) : null;
  } catch {
    return null; // API down: generic title and preview instead of an error page
  }
}
