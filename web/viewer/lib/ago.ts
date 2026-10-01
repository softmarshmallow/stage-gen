// When something last changed, the way a reader scans a list: "4m ago", "3d ago".
// Past a month the date itself reads better than a count.

export function ago(iso: string | null, now: number): string {
  if (iso === null) return "";
  const written = Date.parse(iso);
  if (Number.isNaN(written)) return "";
  const seconds = Math.max(0, (now - written) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 30 * 86_400) return `${Math.floor(seconds / 86_400)}d ago`;
  return iso.slice(0, 10);
}
