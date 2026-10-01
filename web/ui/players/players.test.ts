// The players' mount/cleanup contract on a few hand-built elements (the workspace has no DOM
// library): a mounted player answers its root's events, and after its cleanup it does not.
// The site's browser checks cover the players over real pages.

import { describe, expect, test } from "bun:test";
import { mount as mountCompare } from "./compare";
import { mount as mountTabs } from "./tabs";

/** Just enough of an element for these players: events, style, attributes, classes, children. */
class Element extends EventTarget {
  readonly style: Record<string, string> = {};
  readonly dataset: Record<string, string> = {};
  readonly attributes = new Map<string, string>();
  readonly classes = new Set<string>();
  readonly classList = {
    toggle: (name: string, on: boolean) => (on ? this.classes.add(name) : this.classes.delete(name)),
    contains: (name: string) => this.classes.has(name),
  };
  value = "";
  constructor(private readonly found: Record<string, Element | Element[]> = {}) {
    super();
  }
  setAttribute(name: string, value: string): void {
    this.attributes.set(name, value);
  }
  querySelector(selector: string): Element | null {
    const hit = this.found[selector];
    return Array.isArray(hit) ? (hit[0] ?? null) : (hit ?? null);
  }
  querySelectorAll(selector: string): Element[] {
    const hit = this.found[selector];
    return Array.isArray(hit) ? hit : hit ? [hit] : [];
  }
}

const asRoot = (el: Element) => el as unknown as HTMLElement;

describe("players unmount", () => {
  test("the compare wipe stops following its range after cleanup", () => {
    const range = new Element(), before = new Element(), handle = new Element();
    const box = new Element({ input: range, "[data-before]": before, "[data-handle]": handle });
    const cleanup = mountCompare(asRoot(box));
    range.value = "30";
    range.dispatchEvent(new Event("input"));
    expect(before.style.clipPath).toBe("inset(0 70% 0 0)");
    expect(handle.style.left).toBe("30%");
    cleanup();
    range.value = "80";
    range.dispatchEvent(new Event("input"));
    expect(handle.style.left).toBe("30%");
  });

  test("the tabs stop switching panes after cleanup, and a second mount works alone", () => {
    const tabs = [new Element(), new Element()], panes = [new Element(), new Element()];
    tabs.forEach((tab, i) => (tab.dataset.tab = String(i)));
    panes.forEach((pane, i) => (pane.dataset.pane = String(i)));
    const box = new Element({ "[data-tab]": tabs, "[data-pane]": panes });
    const first = mountTabs(asRoot(box));
    first();
    const second = mountTabs(asRoot(box));
    let switched = 0;
    tabs[1].addEventListener("click", () => (switched += 1));
    tabs[1].dispatchEvent(new Event("click"));
    expect(switched).toBe(1);
    expect(panes[0].classes.has("hidden")).toBe(true);
    expect(tabs[1].attributes.get("aria-pressed")).toBe("true");
    second();
    panes[0].classes.clear();
    tabs[1].dispatchEvent(new Event("click"));
    expect(panes[0].classes.has("hidden")).toBe(false);
  });
});
