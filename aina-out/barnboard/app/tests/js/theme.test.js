// Theme helpers (static/js/ui.js): explicit choice beats the OS preference,
// the toggle flips, and the button shows the way back.
import { describe, expect, test } from "vitest";

import * as ui from "../../static/js/ui.js";

describe("effectiveTheme", () => {
  test("a stored choice wins over the OS preference", () => {
    expect(ui.effectiveTheme("dark", false)).toBe("dark");
    expect(ui.effectiveTheme("light", true)).toBe("light");
  });
  test("without a valid choice, follow the OS", () => {
    expect(ui.effectiveTheme(null, true)).toBe("dark");
    expect(ui.effectiveTheme(null, false)).toBe("light");
    expect(ui.effectiveTheme("purple", true)).toBe("dark");
    expect(ui.effectiveTheme("", false)).toBe("light");
  });
});

describe("toggle and icon", () => {
  test("nextTheme flips, defaulting to dark", () => {
    expect(ui.nextTheme("dark")).toBe("light");
    expect(ui.nextTheme("light")).toBe("dark");
    expect(ui.nextTheme(undefined)).toBe("dark");
  });
  test("the button shows the theme you'd switch to", () => {
    expect(ui.themeIcon("dark")).toBe("☀️");
    expect(ui.themeIcon("light")).toBe("🌙");
    expect(ui.themeIcon(ui.nextTheme("dark"))).not.toBe(ui.themeIcon("dark"));
  });
});

describe("module shape", () => {
  test("exposes exactly the helpers app.js uses", () => {
    expect(Object.keys(ui).sort()).toEqual([
      "clampSelection", "effectiveTheme", "escapeHtml", "filterItems", "moveSelection",
      "nextTheme", "renderItems", "safeHref", "themeIcon",
    ]);
    expect(ui).toHaveProperty("escapeHtml");
  });
});
