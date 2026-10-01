"use client";

// A copy button of an <Agent>, a <Shell> or a <Try>. The block renders this button with its
// icon and label inside; the player in web/ui/players/copy.ts mounts on it after hydration
// and is torn down with it.

import type { ReactElement } from "react";
import { mount } from "@stage-gen/ui/players/copy";
import { type RootProps, usePlayer } from "./use-player";

export default function CopyPlayer({ code, className, children }: RootProps & { readonly code: string }): ReactElement {
  const ref = usePlayer<HTMLButtonElement, void>(mount);
  return (
    <button ref={ref} data-copy={code} className={className}>
      {children}
    </button>
  );
}
