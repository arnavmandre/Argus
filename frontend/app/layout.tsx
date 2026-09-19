import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Argus AI — Simulate the human experience before building the city",
  description:
    "A human-centric urban digital twin: deterministic pedestrian simulation over real OpenStreetMap geometry, survey-calibrated synthetic citizens and a deterministic advisor. Prototype estimates, not engineering models.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f1f2f4" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-GB">
      <body className="antialiased">{children}</body>
    </html>
  );
}
