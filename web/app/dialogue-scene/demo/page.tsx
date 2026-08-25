import type { Metadata } from "next";
import DialogueSceneDemo from "./DialogueSceneDemo";
import { loadDialogueSceneFixture } from "@/lib/dialogue-scene/active-fixture";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Visual Novel Scene · stage-gen",
  description: "Play an interactive visual-novel dialogue scene.",
  alternates: { canonical: "/dialogue-scene/demo" },
  openGraph: {
    type: "website",
    title: "Visual Novel Scene · stage-gen",
    description: "Play an interactive visual-novel dialogue scene.",
    url: "/dialogue-scene/demo",
    siteName: "stage-gen",
  },
  twitter: {
    card: "summary",
    title: "Visual Novel Scene · stage-gen",
    description: "Play an interactive visual-novel dialogue scene.",
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

export default async function DialogueSceneDemoPage() {
  return <DialogueSceneDemo fixture={await loadDialogueSceneFixture()} />;
}
