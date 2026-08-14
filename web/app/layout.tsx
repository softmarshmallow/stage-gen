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
      <body>{children}</body>
    </html>
  );
}
