# Barnboard Gap-Closure (G) arc — Architecture

The map below shows the gap surfaces, arranged by the priority quadrants from
[gap-analysis.md](gap-analysis.md). Box ids (`comp-<key>`) match `component`
keys in the task database; the cockpit recolours them from task state (grey =
untouched, amber = in progress, green = done and verified).

<svg id="arch-svg" viewBox="0 0 720 470" width="100%" xmlns="http://www.w3.org/2000/svg"
     font-family="Inter, system-ui, sans-serif">
  <style>
    .box { stroke:#5b6472; stroke-width:1.5; rx:8; }
    .lbl { fill:#0b0d10; font-size:13px; font-weight:600; }
    .sub { fill:#3a4048; font-size:10.5px; }
    .grp { fill:none; stroke:#9aa3af; stroke-dasharray:4 4; stroke-width:1.2; }
    .grplbl { fill:#6b7280; font-size:11px; font-weight:700; letter-spacing:.04em; }
  </style>

  <rect class="grp" x="20" y="20" width="680" height="120" rx="10"/>
  <text class="grplbl" x="34" y="38">Q1 — HIGH IMPACT · LOW COMPLEXITY (G0 + G1)</text>

  <rect id="comp-contracts" class="box" x="40" y="50" width="200" height="70" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="55" y="74">Open contracts</text>
  <text class="sub" x="55" y="90">stable serverless API token</text>
  <text class="sub" x="55" y="104">metrics API (G2.2)</text>

  <rect id="comp-security" class="box" x="260" y="50" width="200" height="70" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="275" y="74">Security hygiene</text>
  <text class="sub" x="275" y="90">Secure cookies · gate policy</text>
  <text class="sub" x="275" y="104">serverless trade-offs recorded</text>

  <rect id="comp-app" class="box" x="480" y="50" width="200" height="70" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="495" y="74">Product polish</text>
  <text class="sub" x="495" y="90">Telugu forecast strings</text>
  <text class="sub" x="495" y="104">"native to an Indian dairy"</text>

  <rect class="grp" x="20" y="160" width="680" height="100" rx="10"/>
  <text class="grplbl" x="34" y="178">CONTINUITY (G1)</text>
  <rect id="comp-continuity" class="box" x="40" y="188" width="640" height="58" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="55" y="210">Survive reboots, regressions, disks, drift</text>
  <text class="sub" x="55" y="227">pm2 startup + resurrect drill · nightly backups + restore rehearsal · CI (pytest + baseline gate) · registry check</text>

  <rect class="grp" x="20" y="280" width="680" height="100" rx="10"/>
  <text class="grplbl" x="34" y="298">Q2 — SCHEDULED (G2 + G3)</text>

  <rect id="comp-freshness" class="box" x="40" y="308" width="310" height="58" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="55" y="330">Freshness</text>
  <text class="sub" x="55" y="347">nightly pipeline+retrain · fresh twin forecasts</text>

  <rect id="comp-platform" class="box" x="370" y="308" width="310" height="58" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="385" y="330">Platform proof</text>
  <text class="sub" x="385" y="347">Docker verified · TLS on LAN lanes</text>

  <rect id="comp-backlog" class="box" x="40" y="400" width="640" height="52" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="55" y="421">Backlog (G4) — tracked, unscheduled</text>
  <text class="sub" x="55" y="438">price outlook · lactation priors · heat rules · demo videos · co-op design</text>
</svg>
