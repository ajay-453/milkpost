"""MilkPost data layer — stdlib sqlite3, no ORM.

One SQLite file holds the whole farm. Schema is created at boot with
CREATE TABLE IF NOT EXISTS (additive migrations are enough for V1).
Withholding clear-dates are ALWAYS computed at read time from
treated_on + withhold_days — never stored — so they can't go stale.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import random
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "barnboard.db"))

GESTATION_DAYS = 283          # bovine average; user can override the due date
DRY_OFF_BEFORE_DUE = 60       # planned dry-off = due_date - 60 days
YIELD_DROP_THRESHOLD = 0.20   # alert when a day's total falls >20% below 7-day avg

SCHEMA = """
CREATE TABLE IF NOT EXISTS cows (
  id INTEGER PRIMARY KEY,
  tag TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL DEFAULT '',
  breed TEXT NOT NULL DEFAULT '',
  dob TEXT,
  status TEXT NOT NULL DEFAULT 'milking',
  notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS milk_logs (
  id INTEGER PRIMARY KEY,
  cow_id INTEGER NOT NULL REFERENCES cows(id),
  log_date TEXT NOT NULL,
  session TEXT NOT NULL CHECK (session IN ('AM','PM')),
  litres REAL NOT NULL,
  UNIQUE (cow_id, log_date, session)
);
CREATE TABLE IF NOT EXISTS treatments (
  id INTEGER PRIMARY KEY,
  cow_id INTEGER NOT NULL REFERENCES cows(id),
  drug TEXT NOT NULL,
  treated_on TEXT NOT NULL,
  withhold_days INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS breedings (
  id INTEGER PRIMARY KEY,
  cow_id INTEGER NOT NULL REFERENCES cows(id),
  inseminated_on TEXT NOT NULL,
  due_date TEXT NOT NULL,
  outcome TEXT NOT NULL DEFAULT 'open',
  calf_cow_id INTEGER REFERENCES cows(id),
  notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sales (
  id INTEGER PRIMARY KEY,
  collected_on TEXT NOT NULL,
  litres REAL NOT NULL,
  price_per_litre REAL NOT NULL,
  notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_milk_date ON milk_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_milk_cow_date ON milk_logs(cow_id, log_date);
CREATE INDEX IF NOT EXISTS idx_treat_date ON treatments(treated_on);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'helper',
  approved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);
"""

COW_STATUSES = ["calf", "heifer", "milking", "dry", "sold"]
EXPORT_TABLES = ["cows", "milk_logs", "treatments", "breedings", "sales"]


def get_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    with get_db() as con:
        con.executescript(SCHEMA)
        if not get_setting(con, "feed_token"):
            set_setting(con, "feed_token", secrets.token_urlsafe(16))
        _migrate_users(con)


def _migrate_users(con: sqlite3.Connection) -> None:
    """Additive migrations for the users table — each guarded on column presence
    so upgrades never lock anyone out.
    v1.3: role/approved (earliest account becomes owner, existing rows approved).
    v1.6: security_question/answer + reset lockout counters for self-service
          password recovery (nullable — existing users set theirs when ready)."""
    cols = {c["name"] for c in con.execute("PRAGMA table_info(users)").fetchall()}
    if "role" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'helper'")
        con.execute("ALTER TABLE users ADD COLUMN approved INTEGER NOT NULL DEFAULT 1")
        con.execute("UPDATE users SET role = 'owner' WHERE id = (SELECT MIN(id) FROM users)")
    if "security_question" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN security_question TEXT")
        con.execute("ALTER TABLE users ADD COLUMN security_answer_hash TEXT")
        con.execute("ALTER TABLE users ADD COLUMN reset_fails INTEGER NOT NULL DEFAULT 0")
        con.execute("ALTER TABLE users ADD COLUMN reset_lock TEXT")
    if "is_temp" not in cols:
        # v1.7: request-based demo guests — temporary credentials that self-
        # destruct after logouts_left logouts (the visitor re-requests access).
        con.execute("ALTER TABLE users ADD COLUMN is_temp INTEGER NOT NULL DEFAULT 0")
        con.execute("ALTER TABLE users ADD COLUMN logouts_left INTEGER")


# ── Settings ───────────────────────────────────────────────────────────────

def get_setting(con: sqlite3.Connection, key: str) -> str | None:
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def feed_token(con: sqlite3.Connection) -> str:
    """The calendar/API secret. A FEED_TOKEN env var overrides the per-install
    settings value so serverless instances (each with a private /tmp database
    and therefore a different random token) all agree on one stable token."""
    return os.environ.get("FEED_TOKEN") or get_setting(con, "feed_token") or ""


def set_setting(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))


# ── Auth (stdlib only: PBKDF2 passwords, opaque session tokens in SQLite) ──

SESSION_DAYS = 30  # farm phone convenience; sessions are revocable server-side
_PBKDF2_ITERS = 200_000

# Stateless mode (STATELESS_SESSIONS=1): the session cookie is a self-contained
# HMAC-signed token instead of a row in the sessions table. Needed on hosts with
# no shared/persistent disk (e.g. serverless), where a DB-backed session would
# not survive across instances or cold starts. Self-hosted default is 0 (unchanged).
STATELESS = os.environ.get("STATELESS_SESSIONS") == "1"
_SESSION_SECRET = os.environ.get("SESSION_SECRET", "")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _PBKDF2_ITERS)
    return secrets.compare_digest(dk.hex(), dk_hex)


def has_users(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"] > 0


def create_user(con: sqlite3.Connection, username: str, password: str,
                role: str = "helper", approved: bool = False) -> int:
    cur = con.execute(
        "INSERT INTO users (username, password_hash, created_at, role, approved) "
        "VALUES (?,?,?,?,?)",
        (username, hash_password(password), datetime.now().isoformat(timespec="seconds"),
         role, 1 if approved else 0))
    return cur.lastrowid


_TEMP_WORDS = ("milk", "calf", "barn", "gir", "moo", "hay", "churn", "ghee")


def create_temp_user(con: sqlite3.Connection, logouts: int = 2) -> tuple[str, str]:
    """A disposable demo login (helper role). Dies after `logouts` logouts —
    the visitor requests access again. Returns (username, password)."""
    while True:
        username = "guest-" + secrets.token_hex(2)
        if not con.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            break
    password = (f"{secrets.choice(_TEMP_WORDS)}-{secrets.randbelow(9000) + 1000}"
                f"-{secrets.choice(_TEMP_WORDS)}")
    con.execute(
        "INSERT INTO users (username, password_hash, created_at, role, approved, "
        "is_temp, logouts_left) VALUES (?,?,?,?,1,1,?)",
        (username, hash_password(password),
         datetime.now().isoformat(timespec="seconds"), "helper", logouts))
    return username, password


def burn_temp_logout(con: sqlite3.Connection, user_row) -> None:
    """Called on logout: a temp guest loses one life; at zero the account and
    its sessions are deleted — the credentials simply stop existing."""
    if not user_row or not user_row["is_temp"]:
        return
    left = (user_row["logouts_left"] or 1) - 1
    if left <= 0:
        con.execute("DELETE FROM sessions WHERE user_id = ?", (user_row["id"],))
        con.execute("DELETE FROM users WHERE id = ?", (user_row["id"],))
    else:
        con.execute("UPDATE users SET logouts_left = ? WHERE id = ?", (left, user_row["id"]))


def authenticate(con: sqlite3.Connection, username: str, password: str) -> sqlite3.Row | None:
    user = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def _stateless_secret(con: sqlite3.Connection) -> str:
    # Prefer an explicit env secret (stable across serverless instances);
    # fall back to the per-install feed_token so it still works locally.
    return _SESSION_SECRET or (get_setting(con, "feed_token") or "barnboard-fallback")


def _make_stateless_token(con: sqlite3.Connection, user_id: int) -> str:
    import base64
    exp = int((datetime.now() + timedelta(days=SESSION_DAYS)).timestamp())
    msg = f"{user_id}.{exp}"
    sig = hmac.new(_stateless_secret(con).encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{msg}.{sig}".encode()).decode().rstrip("=")


def _read_stateless_token(con: sqlite3.Connection, token: str) -> int | None:
    import base64
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad).decode()
        uid, exp, sig = raw.split(".")
        good = hmac.new(_stateless_secret(con).encode(), f"{uid}.{exp}".encode(),
                        hashlib.sha256).hexdigest()[:32]
        if not secrets.compare_digest(sig, good):
            return None
        if int(exp) < int(datetime.now().timestamp()):
            return None
        return int(uid)
    except Exception:
        return None


def create_session(con: sqlite3.Connection, user_id: int) -> str:
    if STATELESS:
        return _make_stateless_token(con, user_id)
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    con.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)",
                (token, user_id, expires))
    con.execute("DELETE FROM sessions WHERE expires_at < ?",
                (datetime.now().isoformat(timespec="seconds"),))
    return token


def session_user(con: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    if STATELESS:
        uid = _read_stateless_token(con, token)
        if uid is None:
            return None
        return con.execute("SELECT * FROM users WHERE id = ? AND approved = 1", (uid,)).fetchone()
    return con.execute(
        """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token = ? AND s.expires_at >= ? AND u.approved = 1""",
        (token, datetime.now().isoformat(timespec="seconds"))).fetchone()


def owner_count(con: sqlite3.Connection) -> int:
    return con.execute(
        "SELECT COUNT(*) n FROM users WHERE role = 'owner' AND approved = 1").fetchone()["n"]


# ── Password reset (owner-initiated / CLI; no email needed) ────────────────

RESET_HOURS = 24


def create_reset(con: sqlite3.Connection, user_id: int) -> str:
    """One-time reset token. Any earlier unused token for the user is dropped,
    so only the most recent link works."""
    token = secrets.token_urlsafe(24)
    expires = (datetime.now() + timedelta(hours=RESET_HOURS)).isoformat(timespec="seconds")
    con.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
    con.execute("INSERT INTO password_resets (token, user_id, expires_at) VALUES (?,?,?)",
                (token, user_id, expires))
    return token


def reset_user(con: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    """The user a valid (unused, unexpired) reset token belongs to, else None."""
    if not token:
        return None
    return con.execute(
        """SELECT u.* FROM password_resets r JOIN users u ON u.id = r.user_id
           WHERE r.token = ? AND r.used = 0 AND r.expires_at >= ?""",
        (token, datetime.now().isoformat(timespec="seconds"))).fetchone()


def consume_reset(con: sqlite3.Connection, token: str, new_password: str) -> bool:
    """Set the new password and burn the token. Also kills all the user's
    sessions so a stolen cookie can't outlive the reset. Returns success."""
    row = reset_user(con, token)
    if not row:
        return False
    con.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(new_password), row["id"]))
    con.execute("UPDATE password_resets SET used = 1 WHERE token = ?", (token,))
    con.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
    return True


# ── Self-service recovery: a security question the user sets themselves ─────

SECURITY_QUESTIONS = [
    "What is your village name?",
    "What was your first cow's name?",
    "What is your mother's name?",
    "What is your favourite festival?",
    "What is the name of your school?",
]
_RESET_MAX_FAILS = 5        # wrong answers before a temporary lock
_RESET_LOCK_MIN = 15        # minutes locked after too many wrong answers


def _norm_answer(answer: str) -> str:
    """Answers compare case-insensitively and space-insensitively so a farmer
    isn't locked out by capitalisation — 'My Village ' == 'my village'."""
    return " ".join((answer or "").lower().split())


def set_security(con: sqlite3.Connection, user_id: int, question: str, answer: str) -> None:
    con.execute("UPDATE users SET security_question = ?, security_answer_hash = ?, "
                "reset_fails = 0, reset_lock = NULL WHERE id = ?",
                (question.strip(), hash_password(_norm_answer(answer)), user_id))


def get_recovery(con: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    """The user row if they exist AND have a security question set, else None."""
    row = con.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    if row and row["security_question"] and row["security_answer_hash"]:
        return row
    return None


def reset_locked_minutes(row: sqlite3.Row) -> int:
    """Minutes remaining on a self-reset lock (0 if not locked)."""
    if not row["reset_lock"]:
        return 0
    try:
        until = datetime.fromisoformat(row["reset_lock"])
    except ValueError:
        return 0
    delta = (until - datetime.now()).total_seconds()
    return max(0, int(delta // 60) + 1) if delta > 0 else 0


def try_security_reset(con: sqlite3.Connection, username: str, answer: str,
                       new_password: str) -> tuple[bool, str]:
    """Attempt a self-service reset. Returns (ok, reason). On too many wrong
    answers the account's self-reset locks for RESET_LOCK_MIN minutes (login and
    owner-issued reset still work)."""
    row = get_recovery(con, username)
    if not row:
        return False, "no_question"
    if reset_locked_minutes(row) > 0:
        return False, "locked"
    if not verify_password(_norm_answer(answer), row["security_answer_hash"]):
        fails = row["reset_fails"] + 1
        if fails >= _RESET_MAX_FAILS:
            lock_until = (datetime.now() + timedelta(minutes=_RESET_LOCK_MIN)).isoformat(timespec="seconds")
            con.execute("UPDATE users SET reset_fails = 0, reset_lock = ? WHERE id = ?",
                        (lock_until, row["id"]))
            return False, "locked"
        con.execute("UPDATE users SET reset_fails = ? WHERE id = ?", (fails, row["id"]))
        return False, "wrong_answer"
    # Correct answer: set password, clear counters, sign out every session.
    con.execute("UPDATE users SET password_hash = ?, reset_fails = 0, reset_lock = NULL "
                "WHERE id = ?", (hash_password(new_password), row["id"]))
    con.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
    return True, "ok"


def delete_session(con: sqlite3.Connection, token: str | None) -> None:
    if token:
        con.execute("DELETE FROM sessions WHERE token = ?", (token,))


def iso(d: date) -> str:
    return d.isoformat()


def parse_date(s: str | None, default: date | None = None) -> date | None:
    if not s:
        return default
    try:
        return date.fromisoformat(s)
    except ValueError:
        return default


# ── Withholding (the food-safety core) ─────────────────────────────────────

def withhold_clear_date(treated_on: str, withhold_days: int) -> date:
    """First date the cow's milk may go to the tank again."""
    return date.fromisoformat(treated_on) + timedelta(days=int(withhold_days))


def active_withholdings(con: sqlite3.Connection, today: date) -> list[dict]:
    rows = con.execute(
        """SELECT t.*, c.tag, c.name FROM treatments t
           JOIN cows c ON c.id = t.cow_id
           WHERE c.status != 'sold' ORDER BY t.treated_on DESC"""
    ).fetchall()
    out = []
    for r in rows:
        clear = withhold_clear_date(r["treated_on"], r["withhold_days"])
        if clear > today:
            out.append({**dict(r), "clear_date": iso(clear),
                        "days_left": (clear - today).days})
    return out


def withheld_cow_ids(con: sqlite3.Connection, today: date) -> set[int]:
    return {w["cow_id"] for w in active_withholdings(con, today)}


# ── Milk production ────────────────────────────────────────────────────────

def daily_totals(con: sqlite3.Connection, today: date, days: int = 14) -> list[dict]:
    start = today - timedelta(days=days - 1)
    rows = con.execute(
        "SELECT log_date, SUM(litres) AS total FROM milk_logs "
        "WHERE log_date >= ? GROUP BY log_date", (iso(start),)
    ).fetchall()
    by_date = {r["log_date"]: r["total"] for r in rows}
    return [{"date": iso(start + timedelta(days=i)),
             "total": round(by_date.get(iso(start + timedelta(days=i)), 0.0), 1)}
            for i in range(days)]


def session_logs(con: sqlite3.Connection, log_date: date, session: str) -> dict[int, float]:
    rows = con.execute(
        "SELECT cow_id, litres FROM milk_logs WHERE log_date = ? AND session = ?",
        (iso(log_date), session)).fetchall()
    return {r["cow_id"]: r["litres"] for r in rows}


def yield_drop_alerts(con: sqlite3.Connection, today: date) -> list[dict]:
    """Cows whose most recent daily total sits >20% below their own 7-day average.

    The earliest cheap signal of mastitis/lameness. Needs >=4 prior days of
    data so a brand-new herd doesn't generate noise. Only COMPLETE days are
    compared (up to yesterday) — today's total is partial until the PM
    milking is logged and would false-alarm every morning.
    """
    alerts = []
    cows = con.execute("SELECT id, tag, name FROM cows WHERE status = 'milking'").fetchall()
    last_full = today - timedelta(days=1)
    start = last_full - timedelta(days=7)
    for c in cows:
        rows = con.execute(
            "SELECT log_date, SUM(litres) AS total FROM milk_logs "
            "WHERE cow_id = ? AND log_date >= ? AND log_date <= ? "
            "GROUP BY log_date ORDER BY log_date",
            (c["id"], iso(start), iso(last_full))).fetchall()
        if len(rows) < 5:
            continue
        latest = rows[-1]
        prior = [r["total"] for r in rows[:-1]]
        avg = sum(prior) / len(prior)
        if avg > 0 and latest["total"] < avg * (1 - YIELD_DROP_THRESHOLD):
            alerts.append({"cow_id": c["id"], "tag": c["tag"], "name": c["name"],
                           "latest": round(latest["total"], 1), "avg": round(avg, 1),
                           "pct": round(100 * (1 - latest["total"] / avg))})
    return alerts


# ── Breeding ───────────────────────────────────────────────────────────────

def upcoming_calvings(con: sqlite3.Connection, today: date, within_days: int = 30) -> list[dict]:
    rows = con.execute(
        """SELECT b.*, c.tag, c.name FROM breedings b
           JOIN cows c ON c.id = b.cow_id
           WHERE b.outcome IN ('open','confirmed') ORDER BY b.due_date"""
    ).fetchall()
    out = []
    for r in rows:
        due = date.fromisoformat(r["due_date"])
        days = (due - today).days
        if -7 <= days <= within_days:  # include a week overdue
            out.append({**dict(r), "days_left": days})
    return out


HEAT_CYCLE_DAYS = 21
HEAT_WINDOW = 1          # ± days around the expected return
HEAT_DIP = 0.92          # day total <= 92% of her own recent mean = dip
HEAT_LOOKBACK = 3        # only surface heats detected in the last few days


def heat_watch(con: sqlite3.Connection, today: date) -> list[dict]:
    """Rules-based estrus (heat) return detection (G4.3).

    Literature-validated shape, no ML: a cow whose latest insemination FAILED
    returns to heat on a ~21-day cycle, and the heat day shows a one-day milk
    dip. Flag only when BOTH agree — a projected cycle day (±1) AND a dip
    (<=92% of her own prior mean) — so stable cows can never false-positive.
    """
    alerts = []
    rows = con.execute(
        """SELECT b.cow_id, c.tag, c.name, MAX(b.inseminated_on) AS anchor
           FROM breedings b JOIN cows c ON c.id = b.cow_id
           WHERE c.status = 'milking'
             AND b.outcome = 'failed'
             AND NOT EXISTS (SELECT 1 FROM breedings b2 WHERE b2.cow_id = b.cow_id
                             AND b2.inseminated_on > b.inseminated_on
                             AND b2.outcome IN ('open','confirmed'))
           GROUP BY b.cow_id""").fetchall()
    for r in rows:
        anchor = date.fromisoformat(r["anchor"])
        daily = con.execute(
            "SELECT log_date, SUM(litres) AS total, COUNT(*) AS n FROM milk_logs "
            "WHERE cow_id = ? GROUP BY log_date ORDER BY log_date", (r["cow_id"],)).fetchall()
        totals = {d["log_date"]: d["total"] for d in daily if d["n"] >= 2}
        for back in range(HEAT_LOOKBACK):
            day = today - timedelta(days=back)
            cycles = (day - anchor).days
            if cycles <= 0 or cycles % HEAT_CYCLE_DAYS > HEAT_WINDOW \
                    and cycles % HEAT_CYCLE_DAYS < HEAT_CYCLE_DAYS - HEAT_WINDOW:
                continue
            d_iso = iso(day)
            if d_iso not in totals:
                continue
            prior = [t for d, t in totals.items() if d < d_iso][-5:]
            if len(prior) < 4:
                continue
            mean = sum(prior) / len(prior)
            if mean > 0 and totals[d_iso] <= mean * HEAT_DIP:
                alerts.append({"cow_id": r["cow_id"], "tag": r["tag"], "name": r["name"],
                               "heat_day": d_iso, "cycle": round(cycles / HEAT_CYCLE_DAYS),
                               "dip_pct": round(100 * (1 - totals[d_iso] / mean)),
                               "next_expected": iso(day + timedelta(days=HEAT_CYCLE_DAYS))})
                break
    return alerts


# ── Demo seed ──────────────────────────────────────────────────────────────

_SEED_COWS = [
    ("101", "Gauri", "HF cross", "milking", 13.5), ("102", "Lakshmi", "Gir", "milking", 12.0),
    ("103", "Ganga", "Sahiwal", "milking", 9.5), ("104", "Radha", "HF cross", "milking", 14.0),
    ("105", "Kamala", "Jersey cross", "milking", 11.0), ("106", "Meera", "HF cross", "milking", 13.0),
    ("107", "Tulsi", "Red Sindhi", "milking", 9.0), ("108", "Nandini", "Murrah buffalo", "milking", 12.5),
    ("109", "Parvati", "HF cross", "milking", 13.8), ("110", "Shyama", "Gir", "milking", 10.2),
    ("111", "Savitri", "Sahiwal", "dry", 0.0), ("112", "Sundari", "Gir", "heifer", 0.0),
]


def seed_demo(con: sqlite3.Connection, today: date) -> None:
    """Populate a realistic 12-cow herd with 3 weeks of history. Only call on an
    empty herd. Deterministic (seeded RNG) so demos are reproducible."""
    rng = random.Random(42)
    ids: dict[str, int] = {}
    for tag, name, breed, status, _base in _SEED_COWS:
        dob = today - timedelta(days=rng.randint(700, 2600))
        cur = con.execute(
            "INSERT INTO cows (tag, name, breed, dob, status) VALUES (?,?,?,?,?)",
            (tag, name, breed, iso(dob), status))
        ids[tag] = cur.lastrowid
    for day_off in range(21, -1, -1):
        d = today - timedelta(days=day_off)
        for tag, name, _breed, status, base in _SEED_COWS:
            if status != "milking":
                continue
            for sess in ("AM", "PM"):
                if day_off == 0 and sess == "PM":
                    continue  # tonight's milking hasn't happened yet
                litres = base * rng.uniform(0.9, 1.1)
                if tag == "102" and day_off <= 2:   # Clover: declining → yield-drop alert
                    litres *= 0.65
                con.execute(
                    "INSERT INTO milk_logs (cow_id, log_date, session, litres) VALUES (?,?,?,?)",
                    (ids[tag], iso(d), sess, round(litres, 1)))
    con.execute(  # active withholding: treated 2 days ago, 5-day withhold → 3 days left
        "INSERT INTO treatments (cow_id, drug, treated_on, withhold_days, notes) VALUES (?,?,?,?,?)",
        (ids["104"], "Penicillin (mastitis, LF quarter)", iso(today - timedelta(days=2)), 5,
         "Vet visit — recheck in a week"))
    con.execute(
        "INSERT INTO treatments (cow_id, drug, treated_on, withhold_days, notes) VALUES (?,?,?,?,?)",
        (ids["107"], "Hoof trim + topical", iso(today - timedelta(days=30)), 0, "No withhold"))
    con.execute(  # confirmed pregnancy due in 12 days → dashboard countdown + ICS event
        "INSERT INTO breedings (cow_id, inseminated_on, due_date, outcome) VALUES (?,?,?,?)",
        (ids["111"], iso(today - timedelta(days=GESTATION_DAYS - 12)),
         iso(today + timedelta(days=12)), "confirmed"))
    con.execute(
        "INSERT INTO breedings (cow_id, inseminated_on, due_date, outcome) VALUES (?,?,?,?)",
        (ids["106"], iso(today - timedelta(days=40)),
         iso(today + timedelta(days=GESTATION_DAYS - 40)), "open"))
    for day_off in range(20, 0, -2):  # tanker every 2 days
        d = today - timedelta(days=day_off)
        total = con.execute(
            "SELECT SUM(litres) AS t FROM milk_logs WHERE log_date IN (?,?)",
            (iso(d - timedelta(days=1)), iso(d))).fetchone()["t"] or 0
        con.execute(
            "INSERT INTO sales (collected_on, litres, price_per_litre, notes) VALUES (?,?,?,?)",
            (iso(d), round(total * 0.98, 1), round(rng.uniform(38.0, 44.0), 2),
             "Village dairy society"))
