import "./globals.css";

export const metadata = {
  title: "stage-gen",
  description: "The local, read-only viewer for stage-gen runs and workflows",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      {/* One typeface, one body size, one line height — see docs/plans/2026-05-prototype-design.md. */}
      <body className="bg-bg font-mono text-sm/[1.5] text-fg antialiased">
        {children}
      </body>
    </html>
  );
}
