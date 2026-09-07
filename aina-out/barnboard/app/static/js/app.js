/* Barnboard client glue: theme toggle + command palette. No dependencies. */
(function () {
  "use strict";

  /* ── Theme ─────────────────────────────────────────────────────────── */
  var root = document.documentElement;
  var stored = null;
  try { stored = localStorage.getItem("bb-theme"); } catch (e) { /* private mode */ }
  if (stored === "dark" || stored === "light") root.setAttribute("data-theme", stored);

  function effectiveTheme() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function paintThemeBtn() {
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = effectiveTheme() === "dark" ? "☀️" : "🌙";
  }

  window.bbToggleTheme = function () {
    var next = effectiveTheme() === "dark" ? "light" : "dark";
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

  function filtered() {
    var q = (input().value || "").trim().toLowerCase();
    if (!q) return items.slice(0, 12);
    return items.filter(function (it) {
      return it.label.toLowerCase().indexOf(q) !== -1;
    }).slice(0, 12);
  }

  function render() {
    var f = filtered();
    if (sel >= f.length) sel = Math.max(0, f.length - 1);
    var html = f.map(function (it, i) {
      return '<div class="palette__item' + (i === sel ? " sel" : "") +
        '" data-href="' + it.href + '"><span>' + it.label +
        '</span><span class="kind">' + it.kind + "</span></div>";
    }).join("");
    list().innerHTML = html || '<div class="palette__empty">No matches</div>';
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
    window.location.href = f[sel].href;
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
    else if (e.key === "ArrowDown") { e.preventDefault(); sel += 1; render(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); render(); }
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
        if (item) { closePalette(); window.location.href = item.dataset.href; }
      });
      input().addEventListener("input", function () { sel = 0; render(); });
    }
  });
})();
