export const metadata = {
  title: "stage-gen",
  description: "Prompt-to-playable 2D side-scroller",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          background: "#0a0a0a",
          color: "#e6e6e6",
          fontFamily:
            'ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
          fontSize: 14,
          lineHeight: 1.5,
        }}
      >
        {children}
      </body>
    </html>
  );
}
