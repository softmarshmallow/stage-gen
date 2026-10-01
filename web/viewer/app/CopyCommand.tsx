"use client";

// One command a reader can copy: the text as it would be typed, and a button that puts
// it on the clipboard. The viewer never runs it; the terminal does.

import { useState } from "react";
import { cx, linkGhost } from "./ui";

export default function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div className="flex items-start gap-2 border border-border bg-well px-2.5 py-1.5">
      <code className="min-w-0 flex-1 text-xs break-all whitespace-pre-wrap text-fg">{command}</code>
      <button
        type="button"
        className={cx(linkGhost, "shrink-0 cursor-pointer bg-transparent")}
        onClick={copy}
        aria-label={`copy: ${command}`}
      >
        {copied ? "[ copied ]" : "[ copy ]"}
      </button>
    </div>
  );
}
