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
  artifact_count: 2,
  groups: [
    {
      group_id: "player-hero",
      label: "Player: Hero",
      assets: [
        {
          path: "content/players/hero/concept.png",
          label: "Concept",
          media_type: "image/png",
          width: 128,
          height: 64,
          transparent: true,
        },
      ],
    },
    {
      group_id: "soundtrack",
      label: "Soundtrack",
      assets: [
        {
          path: "soundtrack/day theme.mp3",
          label: "Day Theme",
          media_type: "audio/mpeg",
          transparent: false,
        },
      ],
    },
  ],
};

describe("prepared asset explorer", () => {
  test("renders immutable manifest assets and the active gameplay link", () => {
    const markup = renderToStaticMarkup(<PreparedAssetExplorer model={model} />);

    expect(markup).toContain("prepared asset explorer");
    expect(markup).toContain("2 / 2 manifest-bound artifacts");
    expect(markup).toContain('href="/preview/prepared-fixture-v1"');
    expect(markup).toContain(
      "/api/assets/prepared-fixture-v1/content/players/hero/concept.png",
    );
    expect(markup).toContain(
      "/api/assets/prepared-fixture-v1/soundtrack/day%20theme.mp3",
    );
    expect(markup).toContain("<audio controls=\"\"");
    expect(markup).not.toContain("retry");
    expect(markup).not.toContain("pending");
  });
});
