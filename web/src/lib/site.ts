// Public facts about the site, used by page metadata, the sitemap, the sharing
// images and the legal pages. Set the NEXT_PUBLIC_* values on the host before deploying.

function siteUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicit) return explicit.replace(/\/$/, "");
  // On Vercel, every build is told the project's production domain (its custom
  // domain once one is added), so NEXT_PUBLIC_SITE_URL is optional there.
  const vercel = process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL;
  return vercel ? `https://${vercel}` : "http://localhost:3000";
}

export const SITE = {
  name: "Vaani",
  /** Where this site is served, without a trailing slash, e.g. https://vaani.in */
  url: siteUrl(),
  /** The API, as browsers reach it (the talk-to-us page lives there). */
  apiUrl: (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  /** Where privacy and support questions go; shown on the legal pages. */
  contactEmail: process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "hello@vaani.example",
  title: "Vaani: AI receptionist for clinics and salons",
  description:
    "Vaani answers website calls and WhatsApp in Telugu, Hindi and English, books appointments from your real schedule, and hands tricky calls to your team.",
  demoSlug: "sri-dental",
  brandColor: "#0f766e",
};

/** The API as this server reaches it (server-side fetches for metadata and sharing images). */
export const SERVER_API_URL = (process.env.API_URL ?? SITE.apiUrl).replace(/\/$/, "");
