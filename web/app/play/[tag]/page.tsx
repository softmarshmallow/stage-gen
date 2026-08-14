import { notFound, redirect } from "next/navigation";
import { isSafeRunTag } from "@/lib/shell/runs";

// Compatibility route for old local links. The public consumer boundary is
// `/preview/<tag>`; no preview implementation lives under `/play`.
export default async function LegacyPlayRedirect({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  redirect(`/preview/${tag}`);
}
