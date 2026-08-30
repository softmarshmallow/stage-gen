import "./globals.css";

export const metadata = {
  title: "stage-gen",
  description: "Optional web preview for the stage-gen 2D asset pipeline",
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
      {/* One typeface, one body size, one line height — see DESIGN.md. The
          visual-novel demo route paints its own ground, and says so, so an
          overscroll bounce there does not reveal the terminal black. */}
      <body className="bg-bg font-mono text-sm/[1.5] text-fg antialiased has-[[data-vn-scene]]:bg-vn-night">
        {children}
      </body>
    </html>
  );
}
