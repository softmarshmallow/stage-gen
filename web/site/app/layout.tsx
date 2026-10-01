// The document every page shares: the <html> and <body> of the retired showcase's page and
// index templates, with the site's stylesheet.
//
// <html> suppresses the hydration warning for its own attributes only: the page shell's first
// script may set data-view on it before React hydrates (components/PageShell.tsx).

import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Stage Gen showcase",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className="bg-white text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-100">
      <body className="font-sans text-[15px] leading-relaxed">{children}</body>
    </html>
  );
}
