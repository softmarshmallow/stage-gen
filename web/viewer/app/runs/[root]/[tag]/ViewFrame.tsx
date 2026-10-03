"use client";

// A step's or a workflow's own view: the template its run keeps, in a sandboxed frame of its
// own origin, handed its context and nothing else. The frame asks for the context when it is
// ready; files arrive as URLs the asset route serves, and the frame cannot reach the
// viewer, the run's other files or the network beyond the origins its run declares.

import { useEffect, useRef } from "react";
import { type ViewContext, withUrls } from "@stage-gen/ui/contracts/view-context";
import { preparedAssetUrl, type RunRef } from "@/lib/shell/run-ref";

export default function ViewFrame({
  run,
  view,
  fill = false,
}: {
  run: RunRef;
  view: ViewContext;
  /** Fill the space it is given (a workflow's own view is the page), rather than a panel. */
  fill?: boolean;
}) {
  const frame = useRef<HTMLIFrameElement | null>(null);
  useEffect(() => {
    const target = frame.current;
    if (target === null) return;
    const context = withUrls(view, (ref) => new URL(preparedAssetUrl(run, ref), window.location.href).href);
    // The frame's origin is opaque, so no narrower target than "*" can name it.
    const send = () => target.contentWindow?.postMessage(context, "*");
    function answer(event: MessageEvent) {
      if (event.source !== target?.contentWindow) return;
      if ((event.data as { kind?: unknown } | null)?.kind === "gnode-view-ready") send();
    }
    // A frame that announced itself before this listener existed still gets its context
    // once it has loaded; a view reads the first context it receives.
    window.addEventListener("message", answer);
    target.addEventListener("load", send);
    return () => {
      window.removeEventListener("message", answer);
      target.removeEventListener("load", send);
    };
  }, [run, view]);
  return (
    <div
      className={fill ? "h-full overflow-hidden" : "mb-2 resize-y overflow-hidden border border-border"}
      style={fill ? undefined : { height: 320 }}
    >
      <iframe
        ref={frame}
        title={view.title}
        src={preparedAssetUrl(run, view.template)}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        className="block h-full w-full border-0"
      />
    </div>
  );
}
