// Public facts about the site, used by page metadata, the sitemap, the sharing
// images and the legal pages. Set the NEXT_PUBLIC_* values on the host before deploying.

export const SITE = {
  name: "Vaani",
  /** Where this site is served, without a trailing slash, e.g. https://vaani.in */
  url: (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000").replace(/\/$/, ""),
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
