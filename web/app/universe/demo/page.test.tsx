import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { loadIllustratedMapFixture } from "@/lib/illustrated-map/load-fixture";
import UniverseDemo from "./UniverseDemo";
import { metadata } from "./page";

describe("universe demo", () => {
  test("renders a technical route shell and accessible feature index", async () => {
    const markup = renderToStaticMarkup(
      <UniverseDemo {...(await loadIllustratedMapFixture())} />,
    );

    expect(markup).toContain("Universe planner and explorer");
    expect(markup).toContain("Current module: illustrated map");
    expect(markup).toContain("The Ashen Reaches");
    expect(markup).toContain("Feature inspector");
    expect(markup).toContain("No feature selected");
    expect(markup).toContain("Fit extent");
    expect(markup).toContain('aria-label="Map features"');
    expect(markup).toContain("Hollow Crown");
    expect(markup).toContain("Frostglass Hold");
    expect(markup).toContain("illustrated-map-manifest-v1");
    expect(markup).toContain("image/png");
    expect(markup).toContain("/demo/map/ashen-reaches.json");
    expect(markup).not.toContain("Case notebook");
    expect(markup).not.toContain("missing courier");
  });

  test("publishes the universe demo route identity", () => {
    expect(metadata.alternates).toEqual({ canonical: "/universe/demo" });
    expect(metadata.openGraph).toMatchObject({ url: "/universe/demo" });
  });
});
