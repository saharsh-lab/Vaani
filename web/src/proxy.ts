import { NextResponse, type NextRequest } from "next/server";

// A quick check before rendering dashboard pages: no session cookie, go to login.
// The API still verifies the session and the role on every request.
export function proxy(request: NextRequest) {
  if (!request.cookies.has("vaani_session")) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(login);
  }
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
