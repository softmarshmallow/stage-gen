// The scaffold's own checks, runnable without a staged catalog: Python-faithful number
// formatting, the parity normaliser, and the page binding refusing what a page lacks
// (on the shared catalog fixture of web/ui/contracts).

import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "@stage-gen/ui/contracts/catalog.fixture.json";
import { parseCatalog } from "@stage-gen/ui/contracts/catalog";
import { clock, minutes, money, pyFixed, pyFloat, pyRound, size, stateWords } from "@/blocks/shared";
import { makeComponents } from "@/lib/mdx";
import { gamePage, landingCards, workflowPage } from "@/lib/pages";
import { normalize } from "./html";

describe("Python numbers", () => {
  test("round half to even, on the exact value", () => {
    expect(pyRound(2.5)).toBe(2);
    expect(pyRound(3.5)).toBe(4);
    expect(pyFixed(0.125, 2)).toBe("0.12");
    expect(pyFixed(0.375, 2)).toBe("0.38");
    expect(pyFixed(2.675, 2)).toBe("2.67");
    expect(pyFixed(0.25, 1)).toBe("0.2");
    expect(pyFixed(9.95, 1)).toBe("9.9");
    expect(pyFixed(99.5, 0)).toBe("100");
    expect(pyFixed(-1.25, 1)).toBe("-1.2");
    expect(pyFloat(12)).toBe("12.0");
    expect(pyFloat(12.5)).toBe("12.5");
  });

  test("the showcase's formatters", () => {
    expect(minutes(150)).toBe("2 min");
    expect(minutes(57.4)).toBe("57 s");
    expect(clock(null)).toBeNull();
    expect(clock(400)).toBe("under a second");
    expect(clock(125_000)).toBe("2 min 5 s");
    expect(money(3.655)).toBe("$3.65");
    expect(money(null)).toBeNull();
    expect(size(18_182_338)).toBe("18.2 MB");
    expect(size(2_500)).toBe("2 KB");
    expect(stateWords("eyes", "eyes_half")).toBe("Half");
    expect(stateWords("mouth", "mouth_ah")).toBe("AH");
  });
});

describe("parity normalisation", () => {
  test("spelling differences vanish", () => {
    const python =
      '<div class="b a" data-x="{&quot;k&quot;: 1.0, &quot;a&quot;: [&quot;media/x.webp&quot;]}" style="aspect-ratio: 3/4;background:#fff">' +
      "<img src=\"media/y.webp\" alt=\"\">It&#x27;s</div>";
    const react =
      '<div style="aspect-ratio:3/4;background:#fff" data-x="{&quot;a&quot;:[&quot;/examples/o/i/media/x.webp&quot;],&quot;k&quot;:1}" class="a b">' +
      '<img alt="" src="/examples/o/i/media/y.webp"/>It&#39;s</div>';
    expect(normalize(react)).toEqual(normalize(python));
  });

  test("real differences stay", () => {
    expect(normalize('<p class="mt-6">a</p>')).not.toEqual(normalize('<p class="mt-4">a</p>'));
    expect(normalize("<p>a b</p>")).not.toEqual(normalize("<p>ab</p>"));
    expect(normalize("<pre>a\n b</pre>")).not.toEqual(normalize("<pre>a\nb</pre>"));
  });
});

describe("page binding", () => {
  const catalog = parseCatalog(fixture);

  test("a block prop naming something the example lacks fails the build", () => {
    const page = gamePage("example-game", "harbor-tiles", catalog);
    const components = makeComponents(page);
    const render = (name: string, props: Record<string, unknown>) =>
      renderToStaticMarkup(createElement(components[name], props));
    expect(render("Stat", { metric: "wall_seconds" })).toContain("30 s");
    expect(() => render("Stat", { metric: "nope" })).toThrow(/metric='nope'/);
    expect(() => render("Frame", { node: "nope" })).toThrow(/no node 'nope'/);
    expect(() => render("Hero", { input: "nope", output: "atlas" })).toThrow(/input/);
    expect(() => render("Stat", { metric: "wall_seconds", colour: "red" })).toThrow(/has no prop 'colour'/);
    expect(() => render("Stat", {})).toThrow(/needs 'metric'/);
    expect(() => render("Compare", { node: "harbor-atlas", left: "a", right: "b", at: "50" })).toThrow(
      /must be int/,
    );
    expect(() => render("File", { path: "x" })).toThrow(/belongs inside <Files>/);
  });

  test("a workflow page binds its cover, and the landing lists the cards in order", () => {
    const page = workflowPage("swatch-sheet", catalog);
    expect(page.data.exampleId).toBe("slate-swatches");
    expect(page.hasExample).toBe(true);
    const cards = landingCards(catalog);
    expect(cards.map((card) => card.order)).toEqual([...cards.map((card) => card.order)].sort((a, b) => a - b));
    expect(cards.some((card) => card.madeInside?.startsWith("Made inside the "))).toBe(true);
  });
});
