// The one hook every player wrapper uses: once its root has rendered, it mounts the player
// on it with the config the block wrote, and runs the player's cleanup when the root goes
// (or when React mounts it twice in development).

import { useEffect, useRef, type CSSProperties, type ReactNode, type RefObject } from "react";
import type { Mount } from "@stage-gen/ui/players/dom";

/**
 * A ref for a player's root. `config` is the JSON the block wrote into the root's data-*
 * hook, parsed here for the player; a player without a config gets nothing.
 */
export function usePlayer<E extends HTMLElement, T>(mount: Mount<T>, config?: string): RefObject<E | null> {
  const ref = useRef<E>(null);
  useEffect(() => {
    const root = ref.current;
    if (root === null) return;
    return mount(root, (config === undefined ? undefined : JSON.parse(config)) as T);
  }, [mount, config]);
  return ref;
}

/** The attributes a player root passes through, besides its data-* hook. */
export interface RootProps {
  readonly className?: string;
  readonly style?: CSSProperties;
  readonly children?: ReactNode;
}
