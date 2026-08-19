import type { Metadata } from "next";
import DialogueSceneDemo from "./DialogueSceneDemo";
import { dialogueSceneDemoFixture } from "@/lib/dialogue-scene/demo-fixture";

export const metadata: Metadata = {
  title: "Signal at Blue Hour · Anime dating-sim demo",
  description:
    "A playable 15+ slow-burn romance vignette starring adult astronomy researcher Mio Amamiya, with state-driven expression variants.",
  alternates: { canonical: "/dialogue-scene/demo" },
  openGraph: {
    type: "website",
    title: "Signal at Blue Hour · Anime dating-sim demo",
    description:
      "A playable Visual Novel Scene Kit vignette with an adult heroine and four expression variants.",
    url: "/dialogue-scene/demo",
    siteName: "stage-gen",
    images: [
      {
        url: "/dialogue-scene/demo/anime/concept-key-art.png",
        alt: "Signal at Blue Hour · Mio Amamiya concept key art",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Signal at Blue Hour · Anime dating-sim demo",
    description:
      "A playable Visual Novel Scene Kit vignette with an adult heroine and four expression variants.",
    images: [
      {
        url: "/dialogue-scene/demo/anime/concept-key-art.png",
        alt: "Signal at Blue Hour · Mio Amamiya concept key art",
      },
    ],
  },
  icons: {
    icon: [
      {
        type: "image/svg+xml",
        url: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%230a0a0a'/%3E%3Ccircle cx='32' cy='32' r='18' fill='none' stroke='%2300ff88' stroke-width='4'/%3E%3Cpath d='M32 8v10M32 46v10M8 32h10M46 32h10' stroke='%2300ff88' stroke-width='4'/%3E%3C/svg%3E",
      },
    ],
  },
};

export default function DialogueSceneDemoPage() {
  return <DialogueSceneDemo fixture={dialogueSceneDemoFixture} />;
}
