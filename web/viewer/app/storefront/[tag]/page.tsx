// One storefront, presented the way the App Store presents a product page.
//
// The palette, the type scale and the section order are Apple's light
// appearance — #fff ground, #1d1d1f copy, #6e6e73 secondary, #06c links,
// #d2d2d7 rules — because the whole point of the page is to show these
// surfaces in the context they were drawn for. It is a *format* borrowed for
// preview, not a disguise: nothing here carries Apple's name or marks, and the
// facts in the information strip are measured from the run rather than
// invented. A store shows a star rating and an age gate in that strip; putting
// numbers there that no one measured would be a fabricated record, so the
// strip shows what the run actually knows.
//
// A reader's page, per DESIGN.md: no status borders anywhere. A surface review
// can only refuse, so a refusal takes a red dot beside its name, and every
// grade sits in the disclosure at the foot for whoever wants it.

import Link from "next/link";
import { notFound } from "next/navigation";
import { cx } from "@/app/ui";
import { preparedAssetUrl } from "@/lib/shell/asset-url";
import { isSafeRunTag } from "@/lib/shell/runs";
import { readStorefront, type Storefront } from "@/lib/shell/storefront";
import { REVIEW_CHECKS, type SurfaceRecord } from "@/lib/storefront/contract";

export const dynamic = "force-dynamic";

/** Apple's light appearance, named once so no value is guessed twice. */
const INK = "text-[#1d1d1f]";
const MUTED = "text-[#6e6e73]";
const LINK = "text-[#0066cc] no-underline hover:underline";
const RULE = "border-[#d2d2d7]";
/** SF first, then the platform's own — never a webfont for a preview surface. */
const FONT =
  "font-[-apple-system,BlinkMacSystemFont,'SF_Pro_Text','Helvetica_Neue',Arial,sans-serif]";

/** The order a store presents surfaces, whatever order the package declared. */
const PRESENTATION_ORDER = [
  "feature_graphic",
  "app_icon",
  "store_still_portrait",
  "store_still_landscape",
] as const;

function ordered(storefront: Storefront): readonly SurfaceRecord[] {
  const records = storefront.inventory.surfaces
    .map((surface) => storefront.records[surface.surfaceId])
    .filter((record): record is SurfaceRecord => record !== undefined);
  return [...records].sort(
    (a, b) =>
      PRESENTATION_ORDER.indexOf(a.surfaceKind) -
      PRESENTATION_ORDER.indexOf(b.surfaceKind),
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className={cx("mb-3 text-[22px] font-semibold tracking-[-0.01em]", INK)}>
      {children}
    </h2>
  );
}

/** One `label / value` pair in the strip a store runs under its header. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-col items-center justify-center px-4 py-1 text-center">
      <div
        className={cx(
          "text-[11px] font-semibold uppercase tracking-[0.06em]",
          MUTED,
        )}
      >
        {label}
      </div>
      <div className={cx("mt-1 truncate text-[17px] font-semibold", INK)}>
        {value}
      </div>
    </div>
  );
}

export default async function StorefrontPage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();

  let storefront: Storefront | null = null;
  let refusal: string | null = null;
  try {
    storefront = await readStorefront(tag);
  } catch (error) {
    refusal = error instanceof Error ? error.message : String(error);
  }

  if (refusal !== null) {
    return (
      <main className={cx("min-h-screen bg-white", FONT, INK)}>
        <div className="mx-auto max-w-[980px] px-6 py-8">
        <p className="mb-4 text-[13px]">
          <Link className={LINK} href="/storefront">
            ← Storefronts
          </Link>
        </p>
        <h1 className="mb-3 text-[28px] font-semibold">{tag}</h1>
          <p className="text-[#d70015]">{refusal}</p>
        </div>
      </main>
    );
  }
  if (!storefront) notFound();

  const { inventory, listing, records, unreadableRecords } = storefront;
  const surfaces = ordered(storefront);
  const banner = surfaces.find((r) => r.surfaceKind === "feature_graphic");
  const icon = surfaces.find((r) => r.surfaceKind === "app_icon");
  const stills = surfaces.filter((r) => r.surfaceKind.startsWith("store_still"));
  const rejected = surfaces.filter((r) => r.review.verdict !== "pass");
  const totalBytes = surfaces.reduce((sum, r) => sum + r.bytes, 0);

  return (
    <div className={cx("min-h-screen bg-white", FONT, INK)}>
      <main className="mx-auto max-w-[980px] px-6 pb-16 pt-6 max-[560px]:px-4">
        <p className="mb-6 text-[13px]">
          <Link className={LINK} href="/storefront">
            ← Storefronts
          </Link>
        </p>

        {banner ? (
          <div className="mb-8 overflow-hidden rounded-[18px]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              className="block h-auto w-full"
              src={preparedAssetUrl(tag, banner.artifactRef)}
              alt="Feature graphic for this storefront"
            />
          </div>
        ) : null}

        {/* The product header. Icon, name, subtitle, then the call to action —
            the one row a person reads before anything else. */}
        <header className="flex items-start gap-6 max-[560px]:gap-4">
          {icon ? (
            <div className="w-[128px] shrink-0 max-[560px]:w-[96px]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                className="block h-auto w-full rounded-[22.37%] ring-1 ring-inset ring-black/10"
                src={preparedAssetUrl(tag, icon.artifactRef)}
                alt={`${listing.appName} app icon`}
              />
            </div>
          ) : null}
          <div className="min-w-0 flex-1 pt-1">
            <h1 className="text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] max-[560px]:text-[24px]">
              {listing.appName}
            </h1>
            <p
              className={cx(
                "mt-1 text-[19px] leading-snug max-[560px]:text-[15px]",
                MUTED,
              )}
            >
              {listing.subtitle}
            </p>
            <div className="mt-4 flex items-center gap-4">
              <Link
                className="rounded-full bg-[#0071e3] px-[26px] py-[5px] text-[17px] font-semibold text-white no-underline hover:bg-[#0077ed]"
                href={
                  storefront.hasExecutionView
                    ? `/runs/${encodeURIComponent(tag)}`
                    : "/storefront"
                }
              >
                OPEN
              </Link>
              <span className={cx("text-[12px]", MUTED)}>
                Unreviewed · not published
              </span>
            </div>
          </div>
        </header>

        {/* The information strip: hairline-separated columns, exactly where a
            store puts ratings and an age gate. Every value is measured. */}
        <div
          className={cx(
            "mt-8 grid grid-cols-4 divide-x border-y py-3 max-[560px]:grid-cols-2 max-[560px]:divide-x-0 max-[560px]:gap-y-3",
            RULE,
            "divide-[#d2d2d7]",
          )}
        >
          <Fact label="Surfaces" value={String(surfaces.length)} />
          <Fact
            label="Admitted"
            value={`${inventory.admitted}/${inventory.surfaces.length}`}
          />
          <Fact label="Size" value={`${(totalBytes / 1_048_576).toFixed(1)} MB`} />
          <Fact label="Category" value={listing.keywords[0] ?? "—"} />
        </div>

        {stills.length > 0 ? (
          <section className="mt-10">
            <SectionHeading>Preview</SectionHeading>
            <div className="flex snap-x snap-mandatory items-start gap-4 overflow-x-auto pb-3">
              {stills.map((record) => (
                <div
                  key={record.surfaceId}
                  className={cx(
                    "shrink-0 snap-start overflow-hidden rounded-[18px] ring-1 ring-inset ring-black/10",
                    record.surfaceKind === "store_still_portrait"
                      ? "w-[240px]"
                      : "w-[534px] max-[700px]:w-[400px]",
                  )}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    className="block h-auto w-full"
                    src={preparedAssetUrl(tag, record.artifactRef)}
                    alt={`${record.title} for ${listing.appName}`}
                  />
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className={cx("mt-10 border-t pt-8", RULE)}>
          <SectionHeading>Description</SectionHeading>
          <div className="max-w-[680px] whitespace-pre-line text-[17px] leading-[1.47]">
            {listing.longDescription}
          </div>
          <p className={cx("mt-5 text-[17px] leading-[1.47]", MUTED)}>
            {listing.promotionalText}
          </p>
        </section>

        <section className={cx("mt-10 border-t pt-8", RULE)}>
          <SectionHeading>Information</SectionHeading>
          <dl className="max-w-[680px] text-[15px]">
            {(
              [
                ["Provider", inventory.displayName],
                ["Size", `${(totalBytes / 1_048_576).toFixed(1)} MB`],
                ["Category", listing.keywords.slice(0, 3).join(", ")],
                ["Tagline", listing.shortDescription],
                ["Run", tag],
                [
                  "Rights",
                  inventory.publicationAuthorized
                    ? "publication authorized"
                    : "unreviewed · publication not authorized",
                ],
              ] as const
            ).map(([label, value]) => (
              <div
                key={label}
                className={cx(
                  "grid grid-cols-[160px_minmax(0,1fr)] gap-4 border-t py-3 max-[560px]:grid-cols-1 max-[560px]:gap-1",
                  RULE,
                )}
              >
                <dt className={MUTED}>{label}</dt>
                <dd className="min-w-0 break-words">{value}</dd>
              </div>
            ))}
          </dl>
          <ul className="mt-6 flex list-none flex-wrap gap-2 p-0">
            {listing.keywords.map((keyword) => (
              <li
                key={keyword}
                className={cx(
                  "rounded-full bg-[#f5f5f7] px-3.5 py-1.5 text-[13px]",
                  INK,
                )}
              >
                {keyword}
              </li>
            ))}
          </ul>
        </section>

        <details className={cx("mt-10 border-t pt-6 text-[13px]", RULE, MUTED)}>
          <summary
            className={cx("cursor-pointer list-item hover:text-[#1d1d1f]")}
          >
            Production notes
          </summary>
          <p className="mt-4">
            {inventory.admitted} of {inventory.surfaces.length} surfaces admitted
            {inventory.rejected > 0 ? `, ${inventory.rejected} rejected` : ""}
            {storefront.hasExecutionView ? (
              <>
                {" · "}
                <Link
                  className={LINK}
                  href={`/runs/${encodeURIComponent(tag)}`}
                >
                  run view
                </Link>
              </>
            ) : null}
          </p>
          {!inventory.publicationAuthorized ? (
            <p className="mt-2">
              Every artifact here is unreviewed exploration. The review below
              admits a run; it is not a human semantic review, and publication is
              a separate decision this recipe cannot make.
            </p>
          ) : null}
          <ul className="mt-4 list-none space-y-4 p-0">
            {surfaces.map((record) => (
              <li key={record.surfaceId} className={cx("border-t pt-3", RULE)}>
                <div className={INK}>
                  {record.review.verdict === "pass" ? null : (
                    <span
                      className="mr-1.5 text-[#d70015]"
                      title="this surface was refused by review"
                    >
                      ●
                    </span>
                  )}
                  {record.title}
                  <span className={cx("ml-2", MUTED)}>{record.surfaceId}</span>
                </div>
                <div className="mt-1">
                  drawn {record.drawSize} → ships {record.shipSize} ·{" "}
                  {(record.bytes / 1_048_576).toFixed(1)} MiB · {record.source}
                  {record.draw > 0 ? ` · draw ${record.draw}` : ""}
                </div>
                <div className="mt-1">
                  {REVIEW_CHECKS.map((check) => (
                    <span key={check} className="mr-3">
                      {check.replace(/_/g, " ")}{" "}
                      <span
                        className={
                          record.review.checks[check] === "pass"
                            ? INK
                            : "text-[#d70015]"
                        }
                      >
                        {record.review.checks[check]}
                      </span>
                    </span>
                  ))}
                </div>
                <ul className="mt-1 list-none space-y-0.5 p-0">
                  {record.review.notes.map((note) => (
                    <li key={note}>— {note}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
          {unreadableRecords.length > 0 ? (
            <p className="mt-4 text-[#d70015]">
              {unreadableRecords.length} surface record
              {unreadableRecords.length === 1 ? "" : "s"} could not be read:{" "}
              {unreadableRecords
                .map((entry) => `${entry.surfaceId} (${entry.reason})`)
                .join("; ")}
            </p>
          ) : null}
          {rejected.length === 0 ? null : (
            <p className="mt-4">
              Redraw a refused surface with{" "}
              <code>
                --draw-ledger out/{tag}/draw-ledger.json --reroll{" "}
                {rejected[0].surfaceId}
              </code>
              .
            </p>
          )}
          <p className="mt-4">
            Drawn against{" "}
            {inventory.references.map((r) => r.referenceId).join(", ")}.
          </p>
        </details>
      </main>
    </div>
  );
}
