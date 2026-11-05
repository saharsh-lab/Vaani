// Drawing for the generated PNGs (home-screen icon and link previews). These run
// in next/og's renderer, which supports inline styles and flexbox only.

import { SITE } from "@/lib/site";

const BARS = [
  { x: 14, y: 26, h: 12 },
  { x: 24, y: 17, h: 30 },
  { x: 34, y: 22, h: 20 },
  { x: 44, y: 27, h: 10 },
];

/** The sound-wave mark from icon.svg. `inverted` is white with teal bars, for dark backgrounds. */
export function Mark({ size, inverted = false, square = false }: { size: number; inverted?: boolean; square?: boolean }) {
  const k = size / 64;
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: square ? 0 : 14 * k,
        background: inverted ? "#ffffff" : SITE.brandColor,
        position: "relative",
        display: "flex",
      }}
    >
      {BARS.map((b) => (
        <div
          key={b.x}
          style={{
            position: "absolute",
            left: b.x * k,
            top: b.y * k,
            width: 6 * k,
            height: b.h * k,
            borderRadius: 3 * k,
            background: inverted ? SITE.brandColor : "#ffffff",
          }}
        />
      ))}
    </div>
  );
}

/** A 1200x630 link preview: brand at the top, a headline and a line below it. */
export function Preview({ eyebrow, title, subtitle }: { eyebrow?: string; title: string; subtitle: string }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: 72,
        background: "linear-gradient(135deg, #042f2e 0%, #0f766e 100%)",
        color: "#ffffff",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <Mark size={64} inverted />
        <span style={{ fontSize: 40, fontWeight: 700 }}>Vaani</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {eyebrow && <div style={{ fontSize: 30, color: "#99f6e4", textTransform: "capitalize" }}>{eyebrow}</div>}
        <div style={{ fontSize: 66, fontWeight: 700, lineHeight: 1.1, maxWidth: 1000 }}>{title}</div>
        <div style={{ fontSize: 32, color: "#ccfbf1", maxWidth: 1000 }}>{subtitle}</div>
      </div>
    </div>
  );
}
