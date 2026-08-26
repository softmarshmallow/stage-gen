import type { Metadata } from "next";
import { loadIllustratedMapFixture } from "@/lib/illustrated-map/load-fixture";
import UniverseDemo from "./UniverseDemo";

export const metadata: Metadata = {
  title: "Universe Planner and Explorer · stage-gen",
  description:
    "Plan and explore a generated universe through technical, data-driven views.",
  alternates: { canonical: "/universe/demo" },
  openGraph: {
    type: "website",
    title: "Universe Planner and Explorer · stage-gen",
    description:
      "Plan and explore a generated universe through technical, data-driven views.",
    url: "/universe/demo",
    siteName: "stage-gen",
  },
};

export default async function UniverseDemoPage() {
  return <UniverseDemo {...(await loadIllustratedMapFixture())} />;
}
