// Server-side helper: read and enumerate point-and-click room runs.

import { promises as fs } from "node:fs";
import {
  parseRoomManifest,
  POINTCLICK_RUNTIME_KIND,
  type RoomManifest,
} from "@/lib/pointclick/contract";
import { readRunManifestDocument } from "./manifest-io";
import { assertSafeOutRoot, isSafeRunTag, OUT_ROOT } from "./runs";

/**
 * A manifest published under any other identity is not a room run here,
 * exactly as an absent one is not. A manifest that claims this identity and
 * then fails validation still throws, because that is a contract violation
 * rather than a run this build does not read.
 */
export async function readRoomManifest(tag: string): Promise<RoomManifest | null> {
  const document = await readRunManifestDocument(tag);
  if (document === null || document.kind !== POINTCLICK_RUNTIME_KIND) return null;
  return parseRoomManifest(document.declared);
}

export interface ReadyRoom {
  tag: string;
  displayName: string;
  roomId: string;
}

export async function listReadyRooms(): Promise<ReadyRoom[]> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const out: ReadyRoom[] = [];
  await Promise.all(
    entries.map(async (entry) => {
      if (!entry.isDirectory()) return;
      const tag = entry.name;
      if (!isSafeRunTag(tag)) return;
      try {
        const manifest = await readRoomManifest(tag);
        if (manifest) {
          out.push({ tag, displayName: manifest.displayName, roomId: manifest.roomId });
        }
      } catch {
        // An invalid room manifest is not a ready room.
      }
    }),
  );
  out.sort((a, b) => a.tag.localeCompare(b.tag));
  return out;
}
