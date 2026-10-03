// `/_gnode/view.js`: the module every gnode view imports its context from.
//
// A view runs sandboxed in an opaque origin, so it fetches this module cross-origin; it is
// public, constant and carries nothing of any run.

import { VIEW_HELPER_SOURCE } from "@stage-gen/ui/contracts/view-context";

export function GET() {
  return new Response(VIEW_HELPER_SOURCE, {
    status: 200,
    headers: {
      "content-type": "text/javascript; charset=utf-8",
      "access-control-allow-origin": "*",
      "x-content-type-options": "nosniff",
      "cache-control": "no-store",
    },
  });
}
