# Demo-gate policy (G0.4 — gap #12)

**Decision (2026-09-08):** the access PIN (4276) is deliberately **published**
in the public documentation. The PIN gate is therefore *informational*, not
access control: it signals "you are entering a live app", keeps drive-by
crawlers out of the app's URL space, and gives the demo a front door — it does
not restrict who may enter. This is the right posture for a self-serve public
demo whose data is entirely synthetic and self-resetting.

**What the gate still protects:** nothing sensitive. The hosted twin's
database is an ephemeral, self-reseeding synthetic herd; the local lanes are
LAN-only. No real farm data sits behind any published PIN.

**Rotation procedure — when a real client engagement needs a private demo:**
1. Pick a new PIN. Local lane: change `BETADOC_PIN` in
   `betadoc-data/ecosystem.config.js`, `pm2 restart betadoc-dataplatform`.
   Hosted twin: set `BETADOC_PIN` in the Vercel project env, redeploy.
2. Remove the PIN line from `betadoc-data/site/documentation.html`
   (restore "shared with you separately") and redeploy/republish.
3. Share the new PIN with the client out-of-band.
4. Note the rotation in this file with the date.

**Revisit trigger:** the moment any non-synthetic data reaches a gated lane,
this policy is void — rotate immediately and unpublish.

## Update 2026-09-09 — request-based access

The PIN is no longer published. Visitors request access at `/demo/request`
with their email; every request is appended to `.demo-requests.jsonl` (the
lead log, gitignored). Delivery: by email when SMTP_* env is configured
(owner gets a copy via OWNER_EMAIL), otherwise revealed on screen after the
email is captured. PIN rotated 4276 → 8437 as part of this change.

## Update 2026-09-09 (later) — interim PIN on the gate

Until an email channel is configured (Resend key or SMTP), the gate page
itself displays the access PIN so visitors are never locked out; the request
form still captures leads. The moment RESEND_API_KEY / SMTP_* env exists and
the process restarts, the PIN disappears from the gate automatically
(override with BETADOC_SHOW_PIN=1/0).
