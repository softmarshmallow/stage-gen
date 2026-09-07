// The storefront viewer's home: every storefront run under out/.
//
// A storefront is not a playable scene, so it does not register in
// SCENE_MODULES and does not appear in the home page's genre sections. It gets
// its own index here, listing what the run drew and what review made of it.

import Link from "next/link";
import { cx, h1, metaLine, page } from "@/app/ui";
import {
  listStorefrontRuns,
  type StorefrontRunListEntry,
} from "@/lib/shell/storefront";
import { preparedAssetUrl } from "@/lib/shell/asset-url";

export const dynamic = "force-dynamic";

function outcome(entry: StorefrontRunListEntry): string {
  const parts = [`${entry.admitted}/${entry.surfaceCount} admitted`];
  if (entry.rejected > 0) parts.push(`${entry.rejected} rejected`);
  return parts.join(" · ");
}

export default async function StorefrontIndexPage() {
  const runs = await listStorefrontRuns();
  return (
    <main className={page}>
      <p className={metaLine}>
        <Link className="text-dim no-underline hover:text-accent" href="/">
          ← stage-gen
        </Link>
      </p>
      <h1 className={h1}>Storefronts</h1>
      <p className={cx(metaLine, "mb-4")}>
        {runs.length} storefront run{runs.length === 1 ? "" : "s"} under{" "}
        <code>out/</code> · generate one with{" "}
        <code>stage-gen storefront generate</code>
      </p>
      {runs.length === 0 ? (
        <p className="text-dim">
          No storefronts found. Author a <code>storefront.toml</code> beside a
          game package, run the recipe, and reload.
        </p>
      ) : (
        <ol className="m-0 list-none border-t border-border">
          {runs.map((entry) => (
            <li key={entry.tag}>
              <Link
                className="grid grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-x-4 border-b border-border px-2 py-2.5 text-fg no-underline hover:bg-hover max-[700px]:grid-cols-[56px_minmax(0,1fr)]"
                href={`/storefront/${encodeURIComponent(entry.tag)}`}
              >
                <div className="flex h-[72px] w-[72px] items-center justify-center overflow-hidden bg-well text-dim max-[700px]:h-14 max-[700px]:w-14">
                  {entry.iconRef === null ? null : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      className="h-full w-full object-cover"
                      src={preparedAssetUrl(entry.tag, entry.iconRef)}
                      alt=""
                      aria-hidden
                    />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg">
                    {entry.displayName}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-dim">
                    {entry.tag} · {outcome(entry)}
                  </div>
                </div>
                <span className="text-xs text-dim max-[700px]:hidden">
                  {entry.surfaceCount} surface
                  {entry.surfaceCount === 1 ? "" : "s"}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
