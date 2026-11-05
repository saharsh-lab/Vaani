import type { NextConfig } from "next";

// The FastAPI backend. The browser calls /api/* on this site and Next.js forwards
// it there, so the session cookie is first-party and there's no CORS to set up.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The browser tests build into their own folder, so they don't replace your build.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  cacheComponents: true,
  // Crawlers and link-preview fetchers that get the title, description and preview
  // image in the first bytes (others get them streamed in, which JavaScript-running
  // crawlers like Google's read fine). Next's own list, plus Telegram, which clinics in
  // India share links on. Don't widen this to everyone: Next's prefetches then never finish.
  htmlLimitedBots:
    /[\w-]+-Google|Google-[\w-]+|Chrome-Lighthouse|Slurp|DuckDuckBot|baiduspider|yandex|sogou|bitlybot|tumblr|vkShare|quora link preview|redditbot|ia_archiver|Bingbot|BingPreview|applebot|facebookexternalhit|facebookcatalog|Twitterbot|LinkedInBot|Slackbot|Discordbot|WhatsApp|SkypeUriPreview|Yeti|googleweblight|TelegramBot/i,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
  async headers() {
    const security = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      // The site never needs these; the talk-to-us page that uses the microphone is on the API.
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ];
    if (process.env.NODE_ENV === "production") {
      // Browsers remember to use HTTPS for two years (ignored on plain-HTTP responses).
      security.push({ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" });
    }
    return [
      { source: "/:path*", headers: security },
      // Only a clinic's booking page may be shown inside another site (its own website).
      { source: "/((?!c/).*)", headers: [{ key: "X-Frame-Options", value: "DENY" }] },
    ];
  },
};

export default nextConfig;
