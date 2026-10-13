// Command-palette helpers (static/js/ui.js): filtering, keyboard selection,
// rendering, and the escaping that keeps user-typed cow names from becoming HTML.
import { describe, expect, test } from "vitest";

import * as ui from "../../static/js/ui.js";

const items = [
  { label: "Dashboard", href: "/", kind: "page" },
  { label: "Milk Log", href: "/milk", kind: "page" },
  { label: "#101 Lakshmi", href: "/cows#cow-1", kind: "cow" },
  { label: "#102 Gauri", href: "/cows#cow-2", kind: "cow" },
];

describe("escapeHtml", () => {
  test("escapes every HTML-significant character", () => {
    expect(ui.escapeHtml(`<a href="x">Tom & 'Jerry'</a>`))
      .toBe("&lt;a href=&quot;x&quot;&gt;Tom &amp; &#39;Jerry&#39;&lt;/a&gt;");
  });
  test("passes plain text through and stringifies non-strings", () => {
    expect(ui.escapeHtml("Lakshmi 42")).toBe("Lakshmi 42");
    expect(ui.escapeHtml(7)).toBe("7");
    expect(ui.escapeHtml(null)).toBe("");
    expect(ui.escapeHtml(undefined)).toBe("");
  });
});

describe("filterItems", () => {
  test("empty or blank query returns the first items", () => {
    expect(ui.filterItems(items, "")).toEqual(items);
    expect(ui.filterItems(items, "   ")).toEqual(items);
    expect(ui.filterItems(items, undefined, 2)).toEqual(items.slice(0, 2));
  });
  test("matches case-insensitively anywhere in the label", () => {
    expect(ui.filterItems(items, "LAKSH")).toEqual([items[2]]);
    expect(ui.filterItems(items, " log ")).toEqual([items[1]]);
    expect(ui.filterItems(items, "#10")).toHaveLength(2);
    expect(ui.filterItems(items, "zzz")).toEqual([]);
  });
  test("caps results at the limit (12 by default)", () => {
    const many = Array.from({ length: 20 }, (_, i) => ({ label: `Cow ${i}`, href: "/", kind: "cow" }));
    expect(ui.filterItems(many, "")).toHaveLength(12);
    expect(ui.filterItems(many, "cow", 5)).toHaveLength(5);
    expect(ui.filterItems(many, "cow 1")).toHaveLength(11);   // 1, 10-19
  });
});

describe("selection", () => {
  test("clampSelection keeps the highlight inside the list", () => {
    expect(ui.clampSelection(0, 0)).toBe(0);
    expect(ui.clampSelection(5, 0)).toBe(0);
    expect(ui.clampSelection(-3, 4)).toBe(0);
    expect(ui.clampSelection(2, 4)).toBe(2);
    expect(ui.clampSelection(3, 4)).toBe(3);
    expect(ui.clampSelection(9, 4)).toBe(3);
  });
  test("arrow keys move within bounds, other keys do nothing", () => {
    expect(ui.moveSelection(0, "ArrowDown", 3)).toBe(1);
    expect(ui.moveSelection(2, "ArrowDown", 3)).toBe(2);
    expect(ui.moveSelection(2, "ArrowUp", 3)).toBe(1);
    expect(ui.moveSelection(0, "ArrowUp", 3)).toBe(0);
    expect(ui.moveSelection(1, "Enter", 3)).toBe(1);
    expect(ui.moveSelection(0, "ArrowDown", 0)).toBe(0);
  });
});

describe("renderItems", () => {
  test("renders each item and marks only the selected one", () => {
    const html = ui.renderItems(items.slice(0, 2), 1);
    expect(html).toBe(
      '<div class="palette__item" data-href="/"><span>Dashboard</span><span class="kind">page</span></div>' +
      '<div class="palette__item sel" data-href="/milk"><span>Milk Log</span><span class="kind">page</span></div>');
    expect(html.match(/ sel"/g)).toHaveLength(1);
  });
  test("an empty list says so", () => {
    expect(ui.renderItems([], 0)).toBe('<div class="palette__empty">No matches</div>');
  });
  test("a cow named like markup renders as text, not HTML (XSS)", () => {
    const evil = [{ label: '<img src=x onerror="alert(1)">', href: '/x" onclick="y', kind: "<b>cow</b>" }];
    const html = ui.renderItems(evil, 0);
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<b>");
    expect(html).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
    expect(html).toContain('data-href="/x&quot; onclick=&quot;y"');
    expect(html).toMatch(/<span class="kind">&lt;b&gt;cow&lt;\/b&gt;<\/span>/);
  });
});

describe("safeHref", () => {
  test("keeps same-site paths", () => {
    expect(ui.safeHref("/cows#cow-1")).toBe("/cows#cow-1");
    expect(ui.safeHref("/")).toBe("/");
  });
  test("refuses scripts, other hosts and junk", () => {
    expect(ui.safeHref("javascript:alert(1)")).toBe("/");
    expect(ui.safeHref("//evil.example/x")).toBe("/");
    expect(ui.safeHref("https://evil.example")).toBe("/");
    expect(ui.safeHref("")).toBe("/");
    expect(ui.safeHref(undefined)).toBe("/");
  });
});
