import rawFixture from "./demo-fixture.json";
import { parseDialogueSceneThemeFixture } from "./schema";

export const dialogueSceneDemoFixture = parseDialogueSceneThemeFixture(rawFixture);
