# Barnboard 🐄

**Your dairy farm's daily command center.** Herd register, twice-daily milk
logging, treatment tracking with milk-withholding alerts, calving countdowns,
milk sales — one screen, phone-first, self-hosted.

Built with FastAPI + Jinja2 + HTMX on SQLite. Server-rendered, no build step,
no external services. Your data is one `.db` file you own.

## Quickstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
BARNBOARD_SEED=1 uvicorn app.main:app --reload --port 8000   # demo herd
# or plain:  uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 — on an empty database the dashboard offers a
one-click **Load demo herd** too.

### Docker

```bash
docker build -t barnboard .
docker run -p 8000:8000 -v barnboard-data:/app/data -e DB_PATH=/app/data/barnboard.db barnboard
```

## The features that matter

- **Milk log** (`/milk`) — AM/PM per-cow logging, one tap + one number per cow,
  no page reloads. Cows under an active withholding are flagged **DO NOT TANK**.
- **Withholding alerts** — record a treatment with its withholding days (from the
  drug label / your vet); Barnboard computes the clear-date and shouts about it
  everywhere that matters until it passes.
- **Reminder feed** (`/calendar.ics`) — subscribe once in your phone's calendar
  app; withholding clear-dates, expected calvings and planned dry-offs appear
  as calendar events. No notification infrastructure, no app to install.
- **Yield-drop detection** — a cow producing >20% below her own 7-day average is
  flagged on the dashboard (the earliest cheap sign of mastitis or lameness).
- **Breeding** — inseminations auto-compute a due date (+283 d); marking a record
  *calved* creates the calf in the herd in one step.
- **CSV export** — `/export/{cows,milk_logs,treatments,breedings,sales}.csv`.
- **Ctrl+K** command palette (pages + cows) · **dark mode** toggle · works on a
  phone in the barn.
- **Made for Indian dairies** — revenue in ₹ with lakh/crore digit grouping,
  desi breeds (Gir, Sahiwal, Red Sindhi, Murrah…) in the breed picker, dairy-
  society collection workflow. Litres throughout. Set `CURRENCY` to change
  the symbol for other markets.

## 🌐 Language & account

Barnboard speaks **English and simple Telugu (సులభమైన తెలుగు)**. Switch with the
language button in the top bar (or on the login page); the choice is remembered
per device for a year. Data you type (cow names, notes) and toast pop-ups stay
as entered. Each user has a **My account** page (click your name in the sidebar)
to change their password — changing it signs out every other device.

## 🔐 Login

Barnboard is login-protected with **owner/helper roles**. On first run a
**setup page** creates the owner account. After that, anyone on the farm can
sign up via **Create an account** on the sign-in page — new accounts wait as
*pending* until an owner approves them on the **Team** page (owners can also
promote, demote, or remove members; the farm always keeps at least one owner).
Helpers can do everything operational; only owners manage the team. Sessions
last 30 days per device. Passwords are PBKDF2-hashed; sessions are revocable
server-side (delete rows from the `sessions` table). The calendar feed uses a
**secret-token URL** (see the 📅 link in the sidebar) so phone calendar apps
can subscribe without logging in — treat that URL like a password.

**Forgot a password?** There's no email, so recovery is self-service via a
**security question** each user picks when they sign up (village name, first
cow's name, etc.). On the login page, **Forgot your password?** → enter your
username → answer your question → set a new password. Answers are hashed and
match case-/space-insensitively; five wrong answers lock self-reset for 15
minutes (normal login still works). Set or change your question any time on
**My account**.

Two fallbacks remain for accounts with no question set (e.g. ones created
before this feature): an owner can issue a one-time reset link from the
**Team** page, and for a locked-out sole owner there's a server-side script:

```bash
cd app && python3 reset_password.py <username> --base-url https://your-barnboard-url
# prints a one-time reset link; or use --set to type a new password directly
```

Still run Barnboard on your LAN or behind a VPN (e.g. Tailscale) rather than
the open internet: there is no HTTPS or rate limiting yet.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `APP_NAME` | `Barnboard` | Name in the UI |
| `PORT` | `8000` | Docker listen port |
| `DB_PATH` | `./barnboard.db` | SQLite file location |
| `CURRENCY` | `₹` | Currency symbol for money display |
| `BARNBOARD_SEED` | unset | `1` = seed a demo herd into an empty DB at boot |

## Layout

```
app/main.py      routes + business glue
app/db.py        schema, queries, withholding/yield/calving logic, demo seed
templates/       Jinja2 pages + HTMX partials
static/          design system CSS + vendored htmx + palette/theme JS
```

Backup = copy the `.db` file. That's it.

---

*Generated by the AiNa App Factory pipeline. Docs (braindoc → SOW → PRD →
ops runbook) ship alongside this codebase in `../docs/`.*
