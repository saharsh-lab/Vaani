import type { Metadata } from "next";
import { Suspense } from "react";

import View from "./view";

export const metadata: Metadata = { title: "Book an appointment" };

// The page loads the business in the browser, so a navigation here waits for it by
// design. Client Components can't set this, so this server wrapper does.
export const instant = false;

export default function Page() {
  return (
    <Suspense>
      <View />
    </Suspense>
  );
}
