# Barnboard — Dev Notes

*Stage 4 of the AiNa App Factory pipeline · engine: local Claude*

## Architecture

One FastAPI service, server-rendered with Jinja2, interactive via HTMX fragment
swaps. SQLite through stdlib `sqlite3` — no ORM, keeping `requirements.txt`
identical to the golden starter (fastapi, uvicorn, jinja2, python-multipart).
The AiNa golden-starter shell (sidebar/topbar/design system/toasts) was
**extended, not replaced**: `app.css` and `htmx.min.js` are untouched;
domain styles live in an additive `barnboard.css`.

```
app/main.py          routes, SVG chart builder, ICS generator, toast glue
app/db.py            schema, business logic (withholding, yield-drop, calvings), demo seed
templates/pages/     dashboard · milk · cows · treatments · breeding · sales · roadmap
templates/partials/  one HTMX row partial per entity
static/css/barnboard.css   theme-toggle tokens, DO-NOT-TANK banner, palette
static/js/app.js     command palette (Ctrl+K) + dark-mode toggle
```

## How to run

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
BARNBOARD_SEED=1 uvicorn app.main:app --reload --port 8000
```

(Or Docker — see `app/README.md`. On machines without pip, `uv venv` + `uv pip
install -r requirements.txt` works identically.)

## Non-obvious decisions

- **Withholding is computed, never stored.** `clear_date = treated_on +
  withhold_days` is derived at read time in `db.active_withholdings()`; there is
  no boolean to go stale. The flag surfaces in three places: dashboard banner,
  dashboard alert list, and the milk-log row for the affected cow.
- **Yield-drop compares complete days only** (up to yesterday). Today's total is
  partial until the PM milking is logged; comparing it against full-day averages
  false-alarmed on every cow each morning. Caught and fixed during verification.
- **Milk logging is per-row upsert** (`ON CONFLICT ... DO UPDATE`), so re-logging
  corrects rather than duplicates, and each save returns the row plus
  out-of-band swaps for the session total and logged-count — the page never
  reloads during milking.
- **The ICS feed is hand-rolled** (~30 lines, CRLF line endings, all-day
  `VALUE=DATE` events, stable UIDs). `file` identifies it as a valid iCalendar;
  no dependency needed.
- **SVG trend chart is server-rendered** in Python — fills `var(--accent)` /
  design-system tokens so it themes correctly in light and dark with zero JS.
- **Toasts ride the `X-Toast` header** via the starter's `_toast()` helper; all
  messages are ASCII-safe (the helper also enforces it). Error paths return 422
  with a toast and no swap — HTMX leaves the row untouched, the user sees why.
- **Command palette data is inlined** as JSON in a `<script type="application/json">`
  per page render (pages + live cow list) — no fetch, works offline-ish.

## Verification performed (live, not assumed)

- Booted under uvicorn; all 11 routes return 200 (seeded and empty DB).
- Milk save → `X-Toast: #101: 14.2 L saved` + OOB `session-total` update. Bad
  litres → 422 toast. Duplicate cow tag → 422 toast.
- Treatment with 4-day withhold → DO-NOT-TANK banner on dashboard, red-flagged
  milk row, `Milk OK again` event in `/calendar.ics`.
- Marking a breeding *calved* with tag 990 → calf #990 appears in the herd.
- `/calendar.ics` validates (`file` → "iCalendar calendar file"); 3 event types.
- CSV exports return headed, well-formed rows (431 milk-log lines on seed).
- Empty DB → onboarding card; **Load demo herd** button seeds and HX-redirects.
- Yield-drop: exactly one alert (Clover, the seeded decliner) after the fix.
- Server log clean — zero errors/tracebacks across the whole session.

## v1.1 addendum — auth + India localization

- **Login added** (stdlib only, zero new dependencies): PBKDF2-SHA256 password
  hashing (200k iterations, per-user salt), opaque session tokens stored in
  SQLite (30-day expiry, revocable), HttpOnly/SameSite=Lax cookie. A one-shot
  `/setup` page creates the farm account on first run; HTTP middleware guards
  every route except `/login`, `/setup`, `/healthz`, static assets, and the
  calendar feed. HTMX requests get `401 + HX-Redirect` so fragments bounce to
  login cleanly.
- **Calendar feed moved to a secret-token URL** (`/calendar/<token>.ics`,
  token minted at first boot into the `settings` table, compared with
  `secrets.compare_digest`) because calendar apps cannot log in; the old
  `/calendar.ics` is login-protected and redirects there.
- **India localization:** money in ₹ with lakh/crore digit grouping (custom
  `inr` Jinja filter; `CURRENCY` env overrides the symbol), seed herd renamed
  to Indian names with desi breeds (Gir, Sahiwal, Red Sindhi, Murrah buffalo,
  HF/Jersey cross), breed picker updated, dairy-society collection wording,
  realistic ₹38–44/L procurement prices. CSV exports keep raw numbers.
- **Verified live:** 13-step curl battery (redirects, weak-password 422,
  second-setup lockout, HTMX 401, wrong-password 401, tokened feed 200 +
  wrong token 404, logout) plus a Selenium-driven Chrome session through
  setup → login → dashboard → sales → dark-mode toggle → logout.

## v1.2–v1.3 addendum — signup, roles, approval

- **v1.2:** self-signup from the login page (per-person accounts).
- **v1.3:** owner/helper roles with approval-gated signup. New signups are
  created `pending` and cannot sign in (login returns 403 with a clear
  message; `session_user` also requires `approved=1`, so stale cookies die
  with the flag). Owners get a **Team** page (owner-only route + nav entry)
  to approve/reject pending accounts, promote/demote, and remove members —
  removal deletes the user's sessions immediately.
- **Safety rails:** you cannot remove yourself; the last approved owner can
  be neither removed nor demoted (enforced server-side, buttons also disabled
  in the UI). Setup remains one-shot and creates the owner.
- **Careful migration:** `role`/`approved` columns are added via additive
  `ALTER TABLE` with `approved` defaulting to **1** for pre-existing rows
  (no lockouts on upgrade); the earliest account becomes owner. Verified
  against the live DB: all pre-upgrade accounts kept working.

## v1.4 addendum — password change + Telugu

- **Password change** (`/account`): verifies the current password, enforces
  8-char minimum + match, re-hashes with PBKDF2, and deletes every *other*
  session for the user (the changing device stays signed in). Verified: wrong
  current → 422, short → 422, mismatch → 422, success signs out the second
  device and invalidates the old password.
- **Telugu (te) alongside English (en):** a tiny stdlib i18n layer
  (`app/i18n.py`) — a dict keyed by the English string, exposed to templates as
  `t()`, with English fallback so a missing key can never break a page. A
  `/lang/<code>` route sets a year-long `bb_lang` cookie; a top-bar toggle and
  login/account switchers flip it. HTMX fragment endpoints thread `t` into
  their render contexts so swapped rows come back translated too.
- **Deliberately English:** toast pop-ups (the `X-Toast` HTTP header is
  latin-1 only — Telugu characters there would 500 the response), plus
  farmer-entered data (names, drugs, notes) and CSV exports.

## v1.5 addendum — forgot-password reset

- **No-email design fitting the farm's trust model:** an owner issues a
  one-time reset link from the Team page (**Reset password** → a copyable
  `/reset/<token>` link, shown in an OOB panel) and hands it over in person.
  Tokens live in a `password_resets` table, expire in 24 h, are single-use,
  and creating a new one drops any earlier token for that user.
- **The reset page is public** (`/reset/<token>`, added to the middleware
  allowlist) since a locked-out user can't be logged in. Completing a reset
  burns the token and deletes all that user's sessions.
- **Sole-owner lockout** — the one case the in-app flow can't cover — is
  handled by `reset_password.py`, a CLI run on the server (access to the DB
  box is the credential): prints a reset link, or `--set` to type a new
  password directly.
- **Verified:** link generation, public reset page, short/mismatch 422,
  successful reset invalidates the old password, token single-use (reuse
  404), bad token 404, helper blocked from issuing resets (403), CLI script
  produces a working link.

## v1.6 addendum — self-service password reset

- **User-owned recovery, no owner or email needed.** Each account sets a
  **security question** (from a farmer-friendly list — village, first cow,
  mother's name, festival, school) at signup/setup, and can change it on the
  My account page. `/forgot` is a public two-step flow: username → the user's
  own question → answer + new password.
- **Answer handling:** hashed with the same PBKDF2 as passwords, normalized
  (lowercased, whitespace-collapsed) so capitalisation/trailing spaces don't
  lock a farmer out. A correct answer sets the password and deletes all the
  user's sessions.
- **Brute-force guard:** 5 wrong answers lock *self-reset* for 15 min
  (`reset_fails`/`reset_lock` columns); normal login and owner-issued resets
  are unaffected, so a locked user is never fully stranded.
- **Migration is additive** (nullable columns) — accounts created before v1.6
  simply have no question yet; `/forgot` tells them to set one or ask the
  owner, and the owner link / CLI from v1.5 remain as the fallback.
- **Verified:** signup captures the question; self-reset with the right answer
  works and case/space-insensitively; wrong answer 422; short/mismatch 422;
  old password invalidated; 5-strike lockout engages while login still works;
  no-question accounts routed to the owner fallback.

## What's stubbed / deferred (honest list)

- No HTTPS/rate-limiting/password-reset — LAN/VPN posture still applies.
  Password reset currently means an owner removing and re-approving the
  account (or editing the DB).
- `@app.on_event("startup")` is deprecated in favor of lifespan handlers; works
  fine on FastAPI 0.115, swap when convenient.
- Monthly summary on the sales page updates on reload, not via OOB swap (noted
  in the UI).
- No automated pytest suite in V1 — verification was live-endpoint testing;
  a suite is the natural companion to the V2 auth work.
- Palette cow-jump links to the herd page anchor; a per-cow detail page is V2.
