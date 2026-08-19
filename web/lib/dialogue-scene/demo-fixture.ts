import rawFixture from "./demo-fixture.json";
import { parseDialogueSceneDemoFixture } from "./schema";

export const dialogueSceneDemoFixture = parseDialogueSceneDemoFixture(rawFixture);
