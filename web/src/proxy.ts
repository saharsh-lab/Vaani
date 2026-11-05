import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  // Force HTTPS in production. Vercel already redirects plain HTTP; this also covers
  // hosts that terminate TLS at a proxy and forward with X-Forwarded-Proto. A local
  // `next start` marks its own requests as http, so localhost is left alone.
  // The Host header is the address the browser used (Next's own URL says localhost).
  const host = request.headers.get("host") ?? "";
  const local = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host);
  if (process.env.NODE_ENV === "production" && host && !local && request.headers.get("x-forwarded-proto") === "http") {
    const { pathname, search } = request.nextUrl;
    return NextResponse.redirect(`https://${host.replace(/:\d+$/, "")}${pathname}${search}`, 308);
  }

  // A quick check before rendering dashboard pages: no session cookie, go to login.
  // The API still verifies the session and the role on every request.
  if (request.nextUrl.pathname.startsWith("/dashboard") && !request.cookies.has("vaani_session")) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(login);
  }
}

export const config = {
  // Every page, but not build assets or the generated icons and images.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|apple-icon|opengraph-image).*)"],
};
