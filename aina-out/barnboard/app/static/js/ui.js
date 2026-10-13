/* Barnboard UI helpers: pure functions behind the theme toggle and the command
   palette. No DOM access: an ES module imported by app.js in the browser and
   directly by the JS tests. */

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/* Labels are cow names and tags typed by users: never trust them as HTML. */
export function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
    return ESCAPES[c];
  });
}

/* Explicit choice wins; otherwise follow the OS preference. */
export function effectiveTheme(stored, prefersDark) {
  if (stored === "dark" || stored === "light") return stored;
  return prefersDark ? "dark" : "light";
}

export function nextTheme(current) {
  return current === "dark" ? "light" : "dark";
}

export function themeIcon(theme) {
  return theme === "dark" ? "☀️" : "🌙";
}

/* Case-insensitive substring match on the label, first `limit` hits. An empty
   query matches everything (indexOf("") is 0). */
export function filterItems(items, query, limit) {
  var max = limit || 12;
  var q = String(query || "").trim().toLowerCase();
  return items.filter(function (it) {
    return String(it.label).toLowerCase().indexOf(q) !== -1;
  }).slice(0, max);
}

/* Keep the highlighted row inside the list. */
export function clampSelection(sel, count) {
  if (count <= 0) return 0;
  return Math.min(Math.max(0, sel), count - 1);
}

/* Arrow keys move the highlight; anything else leaves it alone. */
export function moveSelection(sel, key, count) {
  if (key === "ArrowDown") return clampSelection(sel + 1, count);
  if (key === "ArrowUp") return clampSelection(sel - 1, count);
  return sel;
}

export function renderItems(items, sel) {
  if (!items.length) return '<div class="palette__empty">No matches</div>';
  return items.map(function (it, i) {
    return '<div class="palette__item' + (i === sel ? " sel" : "") +
      '" data-href="' + escapeHtml(it.href) + '"><span>' + escapeHtml(it.label) +
      '</span><span class="kind">' + escapeHtml(it.kind) + "</span></div>";
  }).join("");
}

/* Palette links are same-site paths; refuse anything else (javascript:, //host). */
export function safeHref(href) {
  var h = String(href);   // undefined/null become "undefined"/"null": not paths
  return h.charAt(0) === "/" && h.charAt(1) !== "/" ? h : "/";
}
