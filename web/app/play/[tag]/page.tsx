import PlayCanvas from "./PlayCanvas";

// Per-tag playable stage. The Phaser scene is mounted client-side because
// Phaser touches `window` at construct time.
export default async function PlayPage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  return (
    <main style={{ padding: 0, margin: 0, background: "#0a0a0a" }}>
      <div style={{ padding: "8px 16px", color: "#666", fontSize: 12 }}>
        stage-gen / play / <span style={{ color: "#e6e6e6" }}>{tag}</span>
      </div>
      <PlayCanvas tag={tag} />
    </main>
  );
}
