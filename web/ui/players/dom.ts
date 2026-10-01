// The helpers the retired showcase's page script defined once at its top and every section
// used, moved verbatim and typed. A player imports them instead of defining its own.

/**
 * A player: mounted on its root element with the config its block wrote, it returns the
 * cleanup that removes every listener, timer, observer and frame loop the mount started.
 */
export type Mount<T = void> = (el: HTMLElement, config: T) => () => void;

export const $ = <E extends Element = HTMLElement>(s: string, r: ParentNode = document): E | null =>
  r.querySelector<E>(s);

export const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] ?? c);

export const CHECKER =
  "background-color:#fff;background-image:conic-gradient(#e4e4e7 25%,transparent 0 50%,#e4e4e7 0 75%,transparent 0);background-size:16px 16px";

export const human = (s: unknown): string => {
  const t = String(s).replaceAll("_", " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
};
