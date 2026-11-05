import type { Metadata } from "next";

import View from "./view";

export const metadata: Metadata = { title: "Settings" };

// Rendered in the browser once the session has loaded (see app/dashboard/layout.tsx), so a
// navigation here waits for it by design. Client Components can't set this, so
// this server wrapper does.
export const instant = false;

export default function Page() {
  return <View />;
}
