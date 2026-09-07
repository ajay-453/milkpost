# Barnboard Data Platform — Architecture

The diagram below is the live map of the data arc. Each component box has a
stable id (`comp-<key>`) that matches a `component` key in the task database.
The cockpit recolours the boxes from task state at request time:

- **grey** — untouched (no leaves done)
- **amber** — in progress (some leaves done or partial, some still open)
- **green** — done and verified (all leaves done)

The `fill` values below are only defaults for viewing this file directly; the
cockpit overrides them. Component keys are lowercase letters only, so the SVG ids
match the task table exactly (digits/hyphens would break the match).

<svg id="arch-svg" viewBox="0 0 720 520" width="100%" xmlns="http://www.w3.org/2000/svg"
     font-family="Inter, system-ui, sans-serif">
  <style>
    .box { stroke:#5b6472; stroke-width:1.5; rx:8; }
    .lbl { fill:#0b0d10; font-size:13px; font-weight:600; }
    .sub { fill:#3a4048; font-size:10.5px; }
    .grp { fill:none; stroke:#9aa3af; stroke-dasharray:4 4; stroke-width:1.2; }
    .grplbl { fill:#6b7280; font-size:11px; font-weight:700; letter-spacing:.04em; }
    .arrow { stroke:#5b6472; stroke-width:1.4; fill:none; marker-end:url(#arr); }
  </style>
  <defs>
    <marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
      <path d="M0,0 L8,4 L0,8 z" fill="#5b6472"/>
    </marker>
  </defs>

  <!-- external free data -->
  <rect id="comp-research" class="box" x="30" y="20" width="200" height="46" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="45" y="39">Free-data research</text>
  <text class="sub" x="45" y="55">inventory · licenses · use-cases</text>

  <rect id="comp-datasets" class="box" x="250" y="20" width="200" height="46" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="265" y="39">Reference datasets</text>
  <text class="sub" x="265" y="55">fetchers · checksums · benchmarks</text>

  <!-- barnboard operational data -->
  <rect id="comp-app" class="box" x="490" y="20" width="200" height="46" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="505" y="39">Barnboard app (live)</text>
  <text class="sub" x="505" y="55">cows · milk · breeding · sales</text>

  <!-- data-team medallion pipeline -->
  <rect class="grp" x="20" y="96" width="680" height="120" rx="10"/>
  <text class="grplbl" x="34" y="114">DATA-TEAM PIPELINE (spine)</text>
  <rect id="comp-pipeline" class="box" x="40" y="126" width="300" height="70" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="55" y="150">Medallion pipeline</text>
  <text class="sub" x="55" y="166">architect → engineer: bronze → silver → gold</text>
  <text class="sub" x="55" y="181">catalog · lineage · governance envelope</text>

  <rect id="comp-semantic" class="box" x="370" y="126" width="310" height="70" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="385" y="150">Governed semantic layer</text>
  <text class="sub" x="385" y="166">designer: metric DSL · conformance guard</text>
  <text class="sub" x="385" y="181">analyst: questions → reports + receipts</text>

  <!-- models -->
  <rect class="grp" x="20" y="236" width="680" height="100" rx="10"/>
  <text class="grplbl" x="34" y="254">MODELS (scientist branch)</text>
  <rect id="comp-models" class="box" x="40" y="264" width="640" height="58" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="55" y="286">Trained models — versioned params on gold</text>
  <text class="sub" x="55" y="303">7-day yield forecast · anomaly scoring · revenue projection · eval report</text>

  <!-- serving / contracts -->
  <rect class="grp" x="20" y="356" width="680" height="90" rx="10"/>
  <text class="grplbl" x="34" y="374">SERVING &amp; CONTRACTS (ml branch)</text>
  <rect id="comp-serving" class="box" x="40" y="382" width="310" height="52" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="55" y="403">Inference serving</text>
  <text class="sub" x="55" y="419">predict API · dashboard forecast panel</text>

  <rect id="comp-contracts" class="box" x="370" y="382" width="310" height="52" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="385" y="403">Open data contracts</text>
  <text class="sub" x="385" y="419">JSON API · CSV round-trip · versioned schema</text>

  <!-- ops plane -->
  <rect id="comp-ops" class="box" x="40" y="466" width="640" height="42" rx="8" fill="#e5e7eb"/>
  <text class="lbl" x="55" y="484">Ops plane (sre) — PM2 bare-metal · Docker image · pytest · GitHub</text>
  <text class="sub" x="55" y="499">same stack runs on laptop, VPS, container host — stdlib + 4 pinned deps</text>

  <!-- arrows -->
  <path class="arrow" d="M130 66 L130 96"/>
  <path class="arrow" d="M350 66 L350 96"/>
  <path class="arrow" d="M590 66 L590 96"/>
  <path class="arrow" d="M340 161 L370 161"/>
  <path class="arrow" d="M360 216 L360 236"/>
  <path class="arrow" d="M195 336 L195 356"/>
  <path class="arrow" d="M525 336 L525 356"/>
  <path class="arrow" d="M360 446 L360 466"/>
</svg>

## Reading the map

Raw sources enter from the top: the live barnboard application database (the
farm's own records) and the reference datasets acquired from the free-data
research. The data-team pipeline lands them as typed bronze, cleans to silver,
models to gold, and the governed semantic layer answers management questions
with receipts. The scientist branch trains versioned models on gold; the ml
branch serves them back into the app and exposes open data contracts so any
other system can consume the same data. The ops plane keeps the identical
stack running on every platform.
