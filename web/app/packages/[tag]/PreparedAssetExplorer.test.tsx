import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import PreparedAssetExplorer, {
  type PreparedAssetExplorerModel,
} from "./PreparedAssetExplorer";

const model: PreparedAssetExplorerModel = {
  tag: "prepared-fixture-v1",
  game_id: "prepared_fixture",
  display_name: "Prepared Fixture",
  revision: 3,
  package_sha256: "a".repeat(64),
  artifact_count: 3,
  groups: [
    {
      group_id: "player-hero",
      label: "Player: Hero",
      role: "asset",
      assets: [
        {
          path: "content/players/hero/concept.png",
          label: "Concept",
          media_type: "image/png",
          bytes: 4096,
          width: 128,
          height: 64,
          transparent: true,
        },
      ],
    },
    {
      group_id: "soundtrack",
      label: "Soundtrack",
      role: "asset",
      assets: [
        {
          path: "soundtrack/day theme.mp3",
          label: "Day Theme",
          media_type: "audio/mpeg",
          bytes: 2048,
          transparent: false,
        },
      ],
    },
    {
      group_id: "provenance",
      label: "Provenance",
      role: "provenance",
      assets: [
        {
          path: "maps/village/terrain.json",
          label: "maps/village/terrain.json",
          media_type: "application/json",
          bytes: 3072,
          transparent: true,
        },
      ],
    },
  ],
};

describe("prepared asset explorer", () => {
  test("renders immutable manifest assets and the active gameplay link", () => {
    const markup = renderToStaticMarkup(<PreparedAssetExplorer model={model} />);

    expect(markup).toContain("prepared asset explorer");
    expect(markup).toContain("3 closure artifacts · 2 assets · 1 provenance");
    expect(markup).toContain('href="/preview/prepared-fixture-v1"');
    expect(markup).toContain(
      "/api/assets/prepared-fixture-v1/content/players/hero/concept.png",
    );
    expect(markup).toContain(
      "/api/assets/prepared-fixture-v1/soundtrack/day%20theme.mp3",
    );
    expect(markup).toMatch(/<audio [^>]*controls=""/);
    expect(markup).not.toContain("retry");
    expect(markup).not.toContain("pending");
  });

  test("lists a provenance record as a file rather than a broken image", () => {
    const markup = renderToStaticMarkup(<PreparedAssetExplorer model={model} />);

    // A link to the bytes, not an image element that would render broken.
    expect(markup).toMatch(
      /<a [^>]*href="\/api\/assets\/prepared-fixture-v1\/maps\/village\/terrain\.json"/,
    );
    expect(markup).toContain("terrain.json · 3 KB");
    expect(markup).toContain("nothing loads them to play");
    expect(markup).not.toContain('alt="maps/village/terrain.json"');
  });

  test("says so on the page when an asset has no group yet", () => {
    const behind: PreparedAssetExplorerModel = {
      ...model,
      artifact_count: 4,
      groups: [
        ...model.groups,
        {
          group_id: "ungrouped",
          label: "Ungrouped assets",
          role: "asset",
          assets: [
            {
              path: "content/pets/moth.png",
              label: "content/pets/moth.png",
              media_type: "image/png",
              bytes: 1024,
              transparent: true,
            },
          ],
        },
      ],
    };

    const markup = renderToStaticMarkup(<PreparedAssetExplorer model={behind} />);

    expect(markup).toContain("1 ungrouped");
    expect(markup).toContain("this view has no place for it yet");
    expect(markup).toContain(
      "/api/assets/prepared-fixture-v1/content/pets/moth.png",
    );
  });
});
