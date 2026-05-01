// Quick BGM player — picks a random looping pack from fixtures/bgm/index.json
// and plays it via a singleton HTMLAudioElement. No AI selection yet.
//
// Browsers block audio autoplay until a user gesture, so we attach a
// one-shot listener for the first keydown / pointerdown that calls play().

interface BgmPack {
  id: string;
  file: string;
  title: string;
  loop?: boolean;
}

interface BgmIndex {
  packs: BgmPack[];
}

let current: HTMLAudioElement | null = null;

export async function startRandomBgm(): Promise<{
  pickedId: string;
  pickedTitle: string;
} | null> {
  if (current) return null; // already running

  let index: BgmIndex;
  try {
    const res = await fetch("/api/bgm/index.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`bgm index ${res.status}`);
    index = (await res.json()) as BgmIndex;
  } catch (e) {
    console.warn("[bgm] failed to load index:", e);
    return null;
  }

  // Prefer looping packs; fall back to any pack if none flagged.
  const loopable = index.packs.filter((p) => p.loop !== false);
  const pool = loopable.length > 0 ? loopable : index.packs;
  if (pool.length === 0) return null;
  const pick = pool[Math.floor(Math.random() * pool.length)];

  const audio = new Audio(`/api/bgm/${pick.file}`);
  audio.loop = true;
  audio.volume = 0.5;
  current = audio;

  const tryPlay = () => {
    audio.play().catch(() => {
      // Autoplay blocked — wait for user gesture.
      const unlock = () => {
        audio.play().catch((err) => console.warn("[bgm] play failed:", err));
        window.removeEventListener("keydown", unlock);
        window.removeEventListener("pointerdown", unlock);
      };
      window.addEventListener("keydown", unlock, { once: true });
      window.addEventListener("pointerdown", unlock, { once: true });
    });
  };
  tryPlay();

  console.log(`[bgm] picked: ${pick.id} (${pick.title})`);
  return { pickedId: pick.id, pickedTitle: pick.title };
}

export function stopBgm(): void {
  if (current) {
    current.pause();
    current.src = "";
    current = null;
  }
}
