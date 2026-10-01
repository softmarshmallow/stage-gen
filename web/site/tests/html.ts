// HTML normalisation for the parity harness: the showcase's Python string templates and
// React's renderer spell the same markup differently, and these differences are not
// regressions. Normalising both sides to one token list removes exactly them:
// - attribute order, and how an attribute is quoted or left bare (`disabled` = `disabled=""`);
// - class order (the class set is compared, not the string);
// - entity spelling (`&#x27;` and `&#39;` and `'` are one character);
// - void tags written `<img>` or `<img/>`, comments, and React's <link rel="preload"> hints;
// - whitespace between block tags, and runs of whitespace in text (outside <pre>);
// - style declarations' spacing, and data-* JSON's spacing, key order and number spelling;
// - media URLs, which are reduced to the file's basename (media/x.webp, /examples/o/i/media/x.webp);
// - page links (href), reduced to their last path segment, without index.html.
// Everything else, tag names, attribute values, text and nesting, must match exactly.

export type Token =
  | { readonly kind: "open"; readonly name: string; readonly attrs: readonly (readonly [string, string])[] }
  | { readonly kind: "close"; readonly name: string }
  | { readonly kind: "text"; readonly text: string };

const VOID = new Set([
  "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr",
]);

// Elements whose neighbouring whitespace is never rendered as a space between words.
const BLOCK = new Set([
  "address", "article", "aside", "blockquote", "body", "details", "div", "dl", "dd", "dt", "figcaption",
  "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav",
  "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
  "svg", "path", "rect", "canvas", "script", "template", "html", "head", "title", "model-viewer",
]);

const NAMED: Readonly<Record<string, string>> = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", rarr: "→", larr: "←",
  uarr: "↑", darr: "↓", middot: "·", hellip: "…", mdash: "—", ndash: "–", times: "×", minus: "−",
};

export function decodeEntities(text: string): string {
  return text.replace(/&(#x[0-9a-fA-F]+|#[0-9]+|[a-zA-Z]+);/g, (whole, body: string) => {
    if (body.startsWith("#x") || body.startsWith("#X")) return String.fromCodePoint(parseInt(body.slice(2), 16));
    if (body.startsWith("#")) return String.fromCodePoint(parseInt(body.slice(1), 10));
    return NAMED[body] ?? whole;
  });
}

function escapeText(text: string): string {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function escapeAttr(text: string): string {
  return escapeText(text).replaceAll('"', "&quot;");
}

/** Reads markup into tags and text. Both sides are well formed, so this need not be a full parser. */
export function tokenize(html: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < html.length) {
    if (html.startsWith("<!--", i)) {
      const end = html.indexOf("-->", i + 4);
      i = end < 0 ? html.length : end + 3;
      continue;
    }
    if (html.startsWith("<!", i)) {
      i = html.indexOf(">", i) + 1 || html.length;
      continue;
    }
    if (html[i] === "<" && /[a-zA-Z/]/.test(html[i + 1] ?? "")) {
      if (html[i + 1] === "/") {
        const end = html.indexOf(">", i);
        tokens.push({ kind: "close", name: html.slice(i + 2, end).trim().toLowerCase() });
        i = end + 1;
        continue;
      }
      let j = i + 1;
      while (j < html.length && /[^\s/>]/.test(html[j])) j += 1;
      const name = html.slice(i + 1, j).toLowerCase();
      const attrs: [string, string][] = [];
      let selfClosed = false;
      for (;;) {
        while (j < html.length && /\s/.test(html[j])) j += 1;
        if (html[j] === ">") {
          j += 1;
          break;
        }
        if (html.startsWith("/>", j)) {
          j += 2;
          selfClosed = true;
          break;
        }
        let k = j;
        while (k < html.length && /[^\s=/>]/.test(html[k])) k += 1;
        const attr = html.slice(j, k).toLowerCase();
        j = k;
        while (j < html.length && /\s/.test(html[j])) j += 1;
        let value = "";
        if (html[j] === "=") {
          j += 1;
          while (j < html.length && /\s/.test(html[j])) j += 1;
          const quote = html[j];
          if (quote === '"' || quote === "'") {
            const end = html.indexOf(quote, j + 1);
            value = html.slice(j + 1, end);
            j = end + 1;
          } else {
            k = j;
            while (k < html.length && /[^\s>]/.test(html[k])) k += 1;
            value = html.slice(j, k);
            j = k;
          }
        }
        if (attr) attrs.push([attr, decodeEntities(value)]);
      }
      // A void element has no close tag; a stray one written for it is dropped below.
      tokens.push({ kind: "open", name, attrs });
      // SVG children are foreign content, where `/>` closes the element: <path/> is <path></path>.
      if (selfClosed && !VOID.has(name)) tokens.push({ kind: "close", name });
      if (name === "script" || name === "style") {
        const end = html.indexOf(`</${name}`, j);
        const body = html.slice(j, end < 0 ? html.length : end);
        if (body) tokens.push({ kind: "text", text: body });
        j = end < 0 ? html.length : end;
      }
      i = j;
      continue;
    }
    const next = html.indexOf("<", i + 1);
    const end = next < 0 ? html.length : next;
    tokens.push({ kind: "text", text: decodeEntities(html.slice(i, end)) });
    i = end;
  }
  return tokens.filter(
    (token) =>
      !(token.kind === "close" && VOID.has(token.name)) &&
      // React 19 emits a preload hint for each eager <img>; Next moves them into <head>.
      !(token.kind === "open" && token.name === "link" && token.attrs.some(([n, v]) => n === "rel" && v === "preload")),
  );
}

// ------------------------------------------------------------------------------ values

/** A media path (media/x.webp, slug/media/x.webp, /examples/o/i/media/x.webp) as its basename. */
export function reduceMedia(value: string): string {
  return value.replace(/[^\s"'(),;]*\/?\bmedia\/([^\s"'(),;/]+)/g, "$1");
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([key, entry]) => `${JSON.stringify(key)}:${stableJson(entry)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function normalStyle(value: string): string {
  return value
    .split(";")
    .map((declaration) => {
      const colon = declaration.indexOf(":");
      if (colon < 0) return declaration.trim();
      return `${declaration.slice(0, colon).trim().toLowerCase()}:${declaration.slice(colon + 1).trim().replace(/\s+/g, " ")}`;
    })
    .filter(Boolean)
    .join(";");
}

function normalHref(value: string): string {
  if (/^(https?:|mailto:|#)/.test(value)) return value;
  const parts = value.split(/[?#]/)[0].split("/").filter((part) => part && part !== "." && part !== ".." && part !== "index.html");
  return parts.at(-1) ?? "/";
}

export function normalAttr(name: string, value: string): string {
  if (name === "class") return value.split(/\s+/).filter(Boolean).sort().join(" ");
  if (name === "style") return reduceMedia(normalStyle(value));
  if (name === "href") return normalHref(value);
  if (name.startsWith("data-") && /^\s*[[{]/.test(value)) {
    try {
      return reduceMedia(stableJson(JSON.parse(value)));
    } catch {
      return reduceMedia(value);
    }
  }
  return reduceMedia(value);
}

// ------------------------------------------------------------------------------ normalising

/** The markup as one canonical line per tag or text run. */
export function normalize(html: string): string[] {
  const tokens = tokenize(html);
  const lines: string[] = [];
  let inPre = 0;
  const isBlockToken = (token: Token | undefined): boolean =>
    token !== undefined && token.kind !== "text" && BLOCK.has(token.name);
  tokens.forEach((token, index) => {
    if (token.kind === "open") {
      const attrs = [...token.attrs]
        .map(([name, value]) => [name, normalAttr(name, value)] as const)
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([name, value]) => ` ${name}="${escapeAttr(value)}"`)
        .join("");
      lines.push(`<${token.name}${attrs}>`);
      if (token.name === "pre") inPre += 1;
      return;
    }
    if (token.kind === "close") {
      lines.push(`</${token.name}>`);
      if (token.name === "pre") inPre = Math.max(0, inPre - 1);
      return;
    }
    if (inPre > 0) {
      lines.push(escapeText(token.text).replaceAll("\n", "\\n"));
      return;
    }
    let text = token.text.replace(/\s+/g, " ");
    if (isBlockToken(tokens[index - 1]) || index === 0) text = text.replace(/^ /, "");
    if (isBlockToken(tokens[index + 1]) || index === tokens.length - 1) text = text.replace(/ $/, "");
    if (text === "") return;
    lines.push(escapeText(text));
  });
  // Adjacent text runs (split by a dropped comment) read as one.
  const merged: string[] = [];
  for (const line of lines) {
    const previous = merged.at(-1);
    if (previous !== undefined && !previous.startsWith("<") && !line.startsWith("<")) {
      merged[merged.length - 1] = previous + line;
    } else merged.push(line);
  }
  return merged;
}

/**
 * A compact diff of two normalised fragments: the first line that differs, with a few lines
 * of context from each side, or null when they are equal.
 */
export function compactDiff(expected: readonly string[], actual: readonly string[], context = 3): string | null {
  let first = 0;
  while (first < expected.length && first < actual.length && expected[first] === actual[first]) first += 1;
  if (first === expected.length && first === actual.length) return null;
  let tailE = expected.length - 1;
  let tailA = actual.length - 1;
  while (tailE >= first && tailA >= first && expected[tailE] === actual[tailA]) {
    tailE -= 1;
    tailA -= 1;
  }
  const clip = (line: string) => (line.length > 160 ? `${line.slice(0, 157)}...` : line);
  const show = (lines: readonly string[], from: number, to: number, mark: string) => {
    const out: string[] = [];
    const start = Math.max(0, from - context);
    const stop = Math.min(lines.length - 1, Math.max(to, from) + context, from + 12);
    for (let i = start; i <= stop; i += 1) out.push(`${i >= from && i <= to ? mark : " "} ${clip(lines[i])}`);
    return out.join("\n");
  };
  return [
    `first difference at line ${first + 1} (reference ${expected.length} lines, site ${actual.length} lines)`,
    "reference:",
    show(expected, first, tailE, "-"),
    "site:",
    show(actual, first, tailA, "+"),
  ].join("\n");
}
