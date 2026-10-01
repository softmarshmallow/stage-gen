import { describe, expect, test } from "bun:test";
import path from "node:path";
import { loadIllustratedMapFixture } from "./load-fixture";

// The route reads public/ from the viewer's working directory; a test may start anywhere.
const MAP_DIRECTORY = path.resolve(import.meta.dir, "../../public/demo/map");

describe("illustrated map fixture", () => {
  test("binds the PNG manifest, raster digest, and dimensions", async () => {
    const fixture = await loadIllustratedMapFixture({ asset_directory: MAP_DIRECTORY });

    expect(fixture.manifest.map_id).toBe("ashen-reaches");
    expect(fixture.manifest.raster.sha256).toBe(
      "4dbf0250304f86362b2df5b2f18d6f871552bfb8a1e478bc9e54a37d428266cd",
    );
    expect(fixture.manifest.raster.media_type).toBe("image/png");
    expect(fixture.raster_url).toBe("/demo/map/ashen-reaches.png");
    expect(fixture.manifest_url).toBe("/demo/map/ashen-reaches.json");
  });
});
