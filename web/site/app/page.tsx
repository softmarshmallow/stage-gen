// "/": the landing, eight cards in the owner's order (amendment A1).

import Landing from "@/components/Landing";
import { landingCards } from "@/lib/pages";

export default function Home() {
  return <Landing cards={landingCards()} />;
}
