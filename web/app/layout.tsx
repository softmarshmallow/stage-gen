import "./globals.css";

export const metadata = {
  title: "stage-gen",
  description: "Prompt-to-playable 2D side-scroller",
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
      <body>{children}</body>
    </html>
  );
}
