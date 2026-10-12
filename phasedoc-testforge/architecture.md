# MilkPost TestForge-fix (F) arc — Architecture

The map follows a fix from the hub to the scan that checks it. Code fixes land
in the hub app (left), the mirror cut decides what the scanned repo contains
(middle), and testforge.run re-scans the mirror (right). Box ids (`comp-<key>`)
match the `component` keys in the task database; the cockpit recolours them
from task state (grey = untouched, amber = in progress, green = done and verified).

<svg id="arch-svg" viewBox="0 0 720 430" width="100%" xmlns="http://www.w3.org/2000/svg"
     font-family="Inter, system-ui, sans-serif">
  <style>
    .box { stroke:#5b6472; stroke-width:1.5; }
    .lbl { fill:#0b0d10; font-size:13px; font-weight:600; }
    .sub { fill:#3a4048; font-size:10.5px; }
    .grp { fill:none; stroke:#9aa3af; stroke-dasharray:4 4; stroke-width:1.2; }
    .grplbl { fill:#6b7280; font-size:11px; font-weight:700; letter-spacing:.04em; }
    .arrow { stroke:#6b7280; stroke-width:1.4; fill:none; marker-end:url(#arr); }
  </style>
  <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#6b7280"/></marker></defs>

  <rect class="grp" x="20" y="20" width="250" height="390" rx="10"/>
  <text class="grplbl" x="34" y="38">HUB APP (aina-out/barnboard/app)</text>

  <rect id="comp-deps" class="box" x="36" y="52" width="218" height="84" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="50" y="74">Dependencies (F0.1, F0.2, F1.4)</text>
  <text class="sub" x="50" y="92">jinja2 3.1.6 · python-multipart 0.0.32</text>
  <text class="sub" x="50" y="107">pip-audit clean · vercel --prod</text>
  <text class="sub" x="50" y="122">requirements.lock with hashes</text>

  <rect id="comp-sql" class="box" x="36" y="150" width="218" height="70" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="50" y="172">SQL hardening (F0.3, F0.4)</text>
  <text class="sub" x="50" y="190">literal query per whitelisted table</text>
  <text class="sub" x="50" y="205">pragma_table_info(?) · backup.py</text>

  <rect id="comp-runtime" class="box" x="36" y="234" width="218" height="70" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="50" y="256">Runtime (F2.1–F2.3)</text>
  <text class="sub" x="50" y="274">gzip · Cache-Control on /api/v1</text>
  <text class="sub" x="50" y="289">response schemas, 5 JSON routes</text>

  <rect id="comp-ops" class="box" x="36" y="318" width="218" height="76" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="50" y="340">Error tracking (F2.4)</text>
  <text class="sub" x="50" y="358">user decision: Sentry or declined</text>
  <text class="sub" x="50" y="373">rate limit already decided (G3.3)</text>

  <rect class="grp" x="290" y="20" width="200" height="390" rx="10"/>
  <text class="grplbl" x="304" y="38">MIRROR CUT</text>

  <rect id="comp-ci" class="box" x="304" y="52" width="172" height="100" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="318" y="74">CI (F1.2, F1.3)</text>
  <text class="sub" x="318" y="92">milkpost.yml workflow</text>
  <text class="sub" x="318" y="107">pytest + baseline gate</text>
  <text class="sub" x="318" y="122">pytest --cov TOTAL line</text>
  <text class="sub" x="318" y="137">path-filtered</text>

  <rect id="comp-mirror" class="box" x="304" y="170" width="172" height="120" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="318" y="192">Mirror (F1.1, F1.5, F1.6)</text>
  <text class="sub" x="318" y="210">MILKPOST_PATHS grows:</text>
  <text class="sub" x="318" y="225">README (path-rename)</text>
  <text class="sub" x="318" y="240">milkpost.yml · this arc</text>
  <text class="sub" x="318" y="258">git-filter-repo cut,</text>
  <text class="sub" x="318" y="273">run by the user</text>

  <rect class="grp" x="510" y="20" width="190" height="390" rx="10"/>
  <text class="grplbl" x="524" y="38">PROOF</text>

  <rect id="comp-verify" class="box" x="524" y="170" width="162" height="120" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="538" y="192">Re-scan (F3.1, F3.2)</text>
  <text class="sub" x="538" y="210">testforge.run on</text>
  <text class="sub" x="538" y="225">ajay-453/milkpost</text>
  <text class="sub" x="538" y="243">0 SQLi · 0 advisories</text>
  <text class="sub" x="538" y="258">README + CI detected</text>
  <text class="sub" x="538" y="273">scans/compare.md</text>

  <path class="arrow" d="M254 94 H280 V230 H302"/>
  <path class="arrow" d="M254 185 H280"/>
  <path class="arrow" d="M254 269 H280"/>
  <path class="arrow" d="M390 152 V168"/>
  <path class="arrow" d="M476 230 H522"/>
</svg>
