/* Barnboard client glue: theme toggle + command palette. The logic lives in
   ui.js (tested); this module only wires it to the DOM. */
import * as ui from "./ui.js";

(function () {

  /* ── Theme ─────────────────────────────────────────────────────────── */
  var root = document.documentElement;
  var stored = null;
  try { stored = localStorage.getItem("bb-theme"); } catch (e) { /* private mode */ }
  if (stored === "dark" || stored === "light") root.setAttribute("data-theme", stored);

  function effectiveTheme() {
    return ui.effectiveTheme(root.getAttribute("data-theme"),
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  function paintThemeBtn() {
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = ui.themeIcon(effectiveTheme());
  }

  window.bbToggleTheme = function () {
    var next = ui.nextTheme(effectiveTheme());
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("bb-theme", next); } catch (e) { /* ignore */ }
    paintThemeBtn();
  };

  /* ── Command palette (Ctrl/Cmd+K) ──────────────────────────────────── */
  var items = [];
  var sel = 0;

  function readData() {
    var el = document.getElementById("palette-data");
    if (!el) return;
    try { items = JSON.parse(el.textContent); } catch (e) { items = []; }
  }

  function overlay() { return document.getElementById("palette-overlay"); }
  function input() { return document.getElementById("palette-input"); }
  function list() { return document.getElementById("palette-list"); }

  function filtered() { return ui.filterItems(items, input().value); }

  function render() {
    var f = filtered();
    sel = ui.clampSelection(sel, f.length);
    list().innerHTML = ui.renderItems(f, sel);
  }

  window.bbOpenPalette = function () {
    overlay().classList.add("open");
    input().value = "";
    sel = 0;
    render();
    input().focus();
  };

  function closePalette() { overlay().classList.remove("open"); }

  function go() {
    var f = filtered();
    if (!f.length) return;
    closePalette();
    window.location.href = ui.safeHref(f[sel].href);
  }

  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      var o = overlay();
      if (o && o.classList.contains("open")) closePalette(); else window.bbOpenPalette();
      return;
    }
    var o = overlay();
    if (!o || !o.classList.contains("open")) return;
    if (e.key === "Escape") { closePalette(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); sel = ui.moveSelection(sel, e.key, filtered().length); render();
    }
    else if (e.key === "Enter") { e.preventDefault(); go(); }
  });

  document.addEventListener("DOMContentLoaded", function () {
    readData();
    paintThemeBtn();
    var o = overlay();
    if (o) {
      o.addEventListener("click", function (e) { if (e.target === o) closePalette(); });
      list().addEventListener("click", function (e) {
        var item = e.target.closest(".palette__item");
        if (item) { closePalette(); window.location.href = ui.safeHref(item.dataset.href); }
      });
      input().addEventListener("input", function () { sel = 0; render(); });
    }
  });
})();
