"""Barnboard — a small dairy farm's daily command center.

FastAPI + Jinja2 + HTMX on the AiNa golden starter shell. Server-rendered,
no build step, SQLite in one file. The three rules of this codebase:
  1. Logging milk must be one tap + one number (the notebook test).
  2. Withholding alerts are computed from dates at read time, never cached.
  3. Everything the farmer enters is exportable as CSV.

Run locally:  uvicorn app.main:app --reload --port 8000
Demo data:    BARNBOARD_SEED=1 uvicorn app.main:app   (seeds only an empty DB)
"""
from __future__ import annotations

import csv
import io
import json
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, i18n

APP_NAME = os.environ.get("APP_NAME", "Barnboard")
APP_TAGLINE = os.environ.get("APP_TAGLINE", "Your dairy farm's daily command center.")
CURRENCY = os.environ.get("CURRENCY", "₹")  # ₹ — override for other markets

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def inr_format(n: float, decimals: int = 0) -> str:
    """Indian digit grouping: 1234567.5 -> 12,34,568 (lakh/crore style).
    Used for all money display; raw numbers stay unformatted in CSV exports."""
    neg = n < 0
    n = abs(float(n))
    whole = int(round(n, decimals))
    frac = ""
    if decimals:
        whole = int(n)
        frac = f"{n - whole:.{decimals}f}"[1:]
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if neg else "") + s + frac


templates.env.filters["inr"] = inr_format


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    if os.environ.get("BARNBOARD_SEED") == "1":
        with db.get_db() as con:
            if con.execute("SELECT COUNT(*) AS n FROM cows").fetchone()["n"] == 0:
                db.seed_demo(con, date.today())
            # For a hosted demo: create a ready-to-use owner login so visitors
            # don't hit the first-run setup page. Set DEMO_LOGIN="user:pass".
            demo = os.environ.get("DEMO_LOGIN", "")
            if demo and ":" in demo and not db.has_users(con):
                u, p = demo.split(":", 1)
                uid = db.create_user(con, u.strip(), p, role="owner", approved=True)
                db.set_security(con, uid, "What is your village name?", "demo")


def _ensure_seed() -> None:
    """Serverless-safe: the startup event may not fire (or the /tmp DB may have
    been recycled) between cold starts, so make the first request self-heal."""
    try:
        db.init_db()
        with db.get_db() as con:
            if os.environ.get("BARNBOARD_SEED") == "1" and \
                    con.execute("SELECT COUNT(*) AS n FROM cows").fetchone()["n"] == 0:
                db.seed_demo(con, date.today())
                demo = os.environ.get("DEMO_LOGIN", "")
                if demo and ":" in demo and not db.has_users(con):
                    u, p = demo.split(":", 1)
                    uid = db.create_user(con, u.strip(), p, role="owner", approved=True)
                    db.set_security(con, uid, "What is your village name?", "demo")
    except Exception:
        pass


def _t_for(request: Request):
    return i18n.make_t(i18n.get_lang(request))


def _toast(html: str, message: str, status_code: int = 200) -> HTMLResponse:
    """HTMX fragment + toast. X-Toast MUST stay latin-1 safe — always use this."""
    safe = (message or "").encode("ascii", "replace").decode("ascii")
    return HTMLResponse(html, status_code=status_code, headers={"X-Toast": safe})


# ── Auth middleware ────────────────────────────────────────────────────────
# Everything requires a login except: the login/setup pages themselves,
# static assets, /healthz (uptime probes), and the secret-token calendar
# feed (calendar apps cannot log in; the token IS the credential).

SESSION_COOKIE = "bb_session"
_PUBLIC_PATHS = {"/login", "/setup", "/signup", "/healthz", "/forgot", "/forgot/reset"}

# Secure cookies when served over TLS (set SECURE_COOKIES=1 behind HTTPS/a TLS proxy).
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "0") == "1"

# ── Login rate-limiting (in-memory sliding window, per client IP) ────────────
# Brute-force guard: a handful of failed auth attempts per IP per minute, then
# 429. In-memory is fine for a single-worker single-farm deploy; a multi-worker
# or multi-node setup would move this to SQLite/Redis.
import time as _time
from collections import defaultdict, deque

_RL_MAX = int(os.environ.get("LOGIN_RATE_MAX", "5"))      # attempts...
_RL_WINDOW = int(os.environ.get("LOGIN_RATE_WINDOW", "60"))  # ...per this many seconds
_rl_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _rate_limited(request: Request, bucket: str) -> bool:
    """True if this IP has exceeded the limit for `bucket`. Records the hit."""
    key = f"{bucket}:{_client_ip(request)}"
    now = _time.monotonic()
    dq = _rl_hits[key]
    while dq and now - dq[0] > _RL_WINDOW:
        dq.popleft()
    if len(dq) >= _RL_MAX:
        return True
    dq.append(now)
    return False


def _set_session_cookie(resp, token: str) -> None:
    resp.set_cookie(SESSION_COOKIE, token, max_age=db.SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=SECURE_COOKIES)


_seeded_once = False


@app.middleware("http")
async def require_login(request: Request, call_next):
    global _seeded_once
    if not _seeded_once:
        _ensure_seed()
        _seeded_once = True
    path = request.url.path
    if (path in _PUBLIC_PATHS or path.startswith("/static/")
            or path.startswith("/calendar/") or path.startswith("/lang/")
            or path.startswith("/reset/")):
        return await call_next(request)
    if path.startswith("/api/v1/"):
        # Machine consumers: a session cookie OR the feed secret token
        # (?token=... / Authorization: Bearer ...) — same credential as the
        # calendar feed. APIs answer 401 JSON, never a login redirect.
        tok = request.query_params.get("token") or \
            request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        with db.get_db() as con:
            user = db.session_user(con, request.cookies.get(SESSION_COOKIE))
            expected = db.feed_token(con)
        if user or (tok and expected and secrets.compare_digest(tok, expected)):
            return await call_next(request)
        return Response(json.dumps({"error": "unauthorized"}), status_code=401,
                        media_type="application/json")
    with db.get_db() as con:
        user = db.session_user(con, request.cookies.get(SESSION_COOKIE))
    if not user:
        if request.headers.get("HX-Request"):
            return Response(status_code=401, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", status_code=303)
    request.state.user = user
    return await call_next(request)


# Inline SVG icons (stroke=currentColor) — no external asset deps.
_ICONS = {
    "grid": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></svg>',
    "cow": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M4 9c-1.5 0-2.5-1.2-2.5-3M20 9c1.5 0 2.5-1.2 2.5-3"/><path d="M6 8c0-2 2.5-4 6-4s6 2 6 4c0 1.5-.5 2.5-1 3.5.7 1 1 2.2 1 3.5 0 3.3-2.7 6-6 6s-6-2.7-6-6c0-1.3.3-2.5 1-3.5-.5-1-1-2-1-3.5Z"/><circle cx="9.5" cy="9" r=".8" fill="currentColor"/><circle cx="14.5" cy="9" r=".8" fill="currentColor"/><path d="M9.5 16.5h.01M14.5 16.5h.01"/></svg>',
    "drop": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 2.7 6.6 9.8a6.75 6.75 0 1 0 10.8 0L12 2.7Z"/></svg>',
    "health": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6V3Z"/></svg>',
    "heart": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 20.5C7 16.6 3 13.3 3 9.3 3 6.9 4.9 5 7.3 5c1.7 0 3.2.9 4.1 2.3l.6 1 .6-1C13.5 5.9 15 5 16.7 5 19.1 5 21 6.9 21 9.3c0 4-4 7.3-9 11.2Z"/></svg>',
    "coins": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><ellipse cx="12" cy="5.5" rx="8" ry="2.8"/><path d="M4 5.5v6c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8v-6"/><path d="M4 11.5v6c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8v-6"/></svg>',
    "map": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M9 3 4 5v16l5-2 6 2 5-2V3l-5 2-6-2Z"/><line x1="9" y1="3" x2="9" y2="19"/><line x1="15" y1="5" x2="15" y2="21"/></svg>',
    "team": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.2 3.4-5 6.5-5s5.7 1.8 6.5 5"/><circle cx="17.5" cy="9.5" r="2.5"/><path d="M16.5 15.2c2.6.3 4.4 1.8 5 4.3"/></svg>',
}

NAV = [
    {"key": "dashboard", "label": "Dashboard", "href": "/", "icon": _ICONS["grid"]},
    {"key": "milk", "label": "Milk Log", "href": "/milk", "icon": _ICONS["drop"]},
    {"key": "cows", "label": "Herd", "href": "/cows", "icon": _ICONS["cow"]},
    {"key": "health", "label": "Health", "href": "/treatments", "icon": _ICONS["health"]},
    {"key": "breeding", "label": "Breeding", "href": "/breeding", "icon": _ICONS["heart"]},
    {"key": "sales", "label": "Milk Sales", "href": "/sales", "icon": _ICONS["coins"]},
    {"key": "team", "label": "Team", "href": "/team", "icon": _ICONS["team"], "owner_only": True},
    {"key": "roadmap", "label": "Roadmap", "href": "/roadmap", "icon": _ICONS["map"]},
]

ROADMAP = [
    {"title": "Herd register + fast AM/PM milk logging", "state": "done", "note": "Shipped in v1.0"},
    {"title": "Withholding alerts, breeding countdowns, iCal feed", "state": "done", "note": "Shipped in v1.0"},
    {"title": "Milk sales, CSV export, dark mode, command palette", "state": "done", "note": "Shipped in v1.0"},
    {"title": "Login + sessions (first-run setup, secret-token calendar feed)", "state": "done", "note": "Shipped in v1.1"},
    {"title": "Per-person accounts (self-signup from the login page)", "state": "done", "note": "Shipped in v1.2"},
    {"title": "Owner/helper roles + signup approval (Team page)", "state": "done", "note": "Shipped in v1.3"},
    {"title": "Password change + Telugu language (సులభమైన తెలుగు)", "state": "done", "note": "Shipped in v1.4"},
    {"title": "Forgot-password reset (owner-issued link + CLI recovery)", "state": "done", "note": "Shipped in v1.5"},
    {"title": "Self-service reset via a recovery question (no owner needed)", "state": "done", "note": "Shipped in v1.6"},
    {"title": "CSV import of existing records", "state": "planned", "note": "V2"},
    {"title": "Printable monthly report", "state": "planned", "note": "V2"},
]


def ctx(request: Request, active: str, **extra):
    with db.get_db() as con:
        cows = con.execute(
            "SELECT id, tag, name FROM cows WHERE status != 'sold' ORDER BY tag").fetchall()
        feed_token = db.feed_token(con)
    palette = [{"label": f"{n['label']}", "href": n["href"], "kind": "page"} for n in NAV]
    palette += [{"label": f"#{c['tag']} {c['name']}".strip(), "href": f"/cows#cow-{c['id']}",
                 "kind": "cow"} for c in cows]
    user = getattr(request.state, "user", None)
    is_owner = bool(user and user["role"] == "owner")
    nav = [n for n in NAV if is_owner or not n.get("owner_only")]
    lang = i18n.get_lang(request)
    return {
        "request": request, "app_name": APP_NAME, "app_tagline": APP_TAGLINE,
        "nav": nav, "active": active, "palette_json": json.dumps(palette),
        "today": db.iso(date.today()), "user": user, "currency": CURRENCY,
        "feed_url": f"/calendar/{feed_token}.ics",
        "lang": lang, "t": i18n.make_t(lang), **extra,
    }


# ── Auth routes ────────────────────────────────────────────────────────────

def _auth_ctx(request: Request, **extra):
    lang = i18n.get_lang(request)
    return {"request": request, "app_name": APP_NAME, "app_tagline": APP_TAGLINE,
            "lang": lang, "t": i18n.make_t(lang), **extra}


@app.get("/lang/{code}")
def set_lang(code: str, next: str = "/"):
    if code not in i18n.LANGS:
        code = "en"
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    resp = RedirectResponse(next, status_code=303)
    resp.set_cookie("bb_lang", code, max_age=365 * 86400, samesite="lax")
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, pending: int = 0, reset: int = 0):
    with db.get_db() as con:
        if not db.has_users(con):
            return RedirectResponse("/setup", status_code=303)
    info = None
    if pending:
        info = "Account created. The farm owner has to approve it before you can sign in."
    elif reset:
        info = "Password reset. Sign in with your new password."
    return templates.TemplateResponse(request, "pages/login.html", _auth_ctx(request, info=info))


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if _rate_limited(request, "login"):
        return templates.TemplateResponse(
            request, "pages/login.html",
            _auth_ctx(request, error="Too many attempts. Wait a minute and try again."),
            status_code=429)
    with db.get_db() as con:
        user = db.authenticate(con, username.strip(), password)
        if not user:
            return templates.TemplateResponse(
                request, "pages/login.html",
                _auth_ctx(request, error="Wrong username or password."), status_code=401)
        if not user["approved"]:
            return templates.TemplateResponse(
                request, "pages/login.html",
                _auth_ctx(request, error="Your account is waiting for the owner's approval."),
                status_code=403)
        token = db.create_session(con, user["id"])
    resp = RedirectResponse("/", status_code=303)
    _set_session_cookie(resp, token)
    return resp


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    with db.get_db() as con:
        if db.has_users(con):
            return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "pages/setup.html",
                                      _auth_ctx(request, questions=db.SECURITY_QUESTIONS))


def _validate_credentials(username: str, password: str, password2: str,
                          question: str, answer: str) -> str | None:
    if len(username) < 2:
        return "Username must be at least 2 characters."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password != password2:
        return "Passwords do not match."
    if not question.strip():
        return "Please choose a recovery question."
    if len(answer.strip()) < 2:
        return "Please answer your recovery question."
    return None


@app.post("/setup", response_class=HTMLResponse)
def setup_submit(request: Request, username: str = Form(...), password: str = Form(...),
                 password2: str = Form(...), question: str = Form(""), answer: str = Form("")):
    with db.get_db() as con:
        if db.has_users(con):  # setup is one-shot; never a second-account backdoor
            return RedirectResponse("/login", status_code=303)
        username = username.strip()
        error = _validate_credentials(username, password, password2, question, answer)
        if error:
            return templates.TemplateResponse(
                request, "pages/setup.html",
                _auth_ctx(request, error=error, questions=db.SECURITY_QUESTIONS), status_code=422)
        user_id = db.create_user(con, username, password, role="owner", approved=True)
        db.set_security(con, user_id, question, answer)
        token = db.create_session(con, user_id)
    resp = RedirectResponse("/", status_code=303)
    _set_session_cookie(resp, token)
    return resp


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    with db.get_db() as con:
        if not db.has_users(con):  # first run: the setup page does the welcoming
            return RedirectResponse("/setup", status_code=303)
    return templates.TemplateResponse(request, "pages/signup.html",
                                      _auth_ctx(request, questions=db.SECURITY_QUESTIONS))


@app.post("/signup", response_class=HTMLResponse)
def signup_submit(request: Request, username: str = Form(...), password: str = Form(...),
                  password2: str = Form(...), question: str = Form(""), answer: str = Form("")):
    username = username.strip()
    error = _validate_credentials(username, password, password2, question, answer)
    with db.get_db() as con:
        if not error and con.execute(
                "SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            error = "That username is taken."
        if error:
            return templates.TemplateResponse(
                request, "pages/signup.html",
                _auth_ctx(request, error=error, questions=db.SECURITY_QUESTIONS), status_code=422)
        user_id = db.create_user(con, username, password, role="helper", approved=False)
        db.set_security(con, user_id, question, answer)
    # No session yet — the account sits pending until an owner approves it.
    return RedirectResponse("/login?pending=1", status_code=303)


# ── Self-service password recovery (security question) ─────────────────────

@app.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return templates.TemplateResponse(request, "pages/forgot.html",
                                      _auth_ctx(request, step="username"))


@app.post("/forgot", response_class=HTMLResponse)
def forgot_lookup(request: Request, username: str = Form(...)):
    with db.get_db() as con:
        row = db.get_recovery(con, username)
        if not row:
            # No question set (or unknown user): can't self-serve — point to owner.
            return templates.TemplateResponse(
                request, "pages/forgot.html",
                _auth_ctx(request, step="username", username=username, no_question=True),
                status_code=404)
        if db.reset_locked_minutes(row) > 0:
            return templates.TemplateResponse(
                request, "pages/forgot.html",
                _auth_ctx(request, step="username", locked=db.reset_locked_minutes(row)),
                status_code=429)
        question = row["security_question"]
    return templates.TemplateResponse(
        request, "pages/forgot.html",
        _auth_ctx(request, step="answer", username=username.strip(), question=question))


@app.post("/forgot/reset", response_class=HTMLResponse)
def forgot_reset(request: Request, username: str = Form(...), answer: str = Form(...),
                 password: str = Form(...), password2: str = Form(...)):
    with db.get_db() as con:
        row = db.get_recovery(con, username)
        if not row:
            return RedirectResponse("/forgot", status_code=303)
        question = row["security_question"]
        error = None
        if len(password) < 8:
            error = "New password must be at least 8 characters."
        elif password != password2:
            error = "New passwords do not match."
        if error:
            return templates.TemplateResponse(
                request, "pages/forgot.html",
                _auth_ctx(request, step="answer", username=username.strip(),
                          question=question, error=error), status_code=422)
        ok, reason = db.try_security_reset(con, username, answer, password)
        if reason == "locked":
            locked_row = db.get_recovery(con, username)
            mins = db.reset_locked_minutes(locked_row) if locked_row else db._RESET_LOCK_MIN
    if ok:
        return RedirectResponse("/login?reset=1", status_code=303)
    if reason == "locked":
        return templates.TemplateResponse(
            request, "pages/forgot.html",
            _auth_ctx(request, step="username", locked=mins), status_code=429)
    return templates.TemplateResponse(
        request, "pages/forgot.html",
        _auth_ctx(request, step="answer", username=username.strip(), question=question,
                  error="That answer is not correct. Try again."), status_code=422)


@app.post("/logout")
def logout(request: Request):
    with db.get_db() as con:
        db.delete_session(con, request.cookies.get(SESSION_COOKIE))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ── Password reset via one-time link (no login required) ───────────────────

@app.get("/reset/{token}", response_class=HTMLResponse)
def reset_page(request: Request, token: str):
    with db.get_db() as con:
        user = db.reset_user(con, token)
    if not user:
        return templates.TemplateResponse(
            request, "pages/reset.html",
            _auth_ctx(request, token=token, invalid=True), status_code=404)
    return templates.TemplateResponse(
        request, "pages/reset.html",
        _auth_ctx(request, token=token, invalid=False, username=user["username"]))


@app.post("/reset/{token}", response_class=HTMLResponse)
def reset_submit(request: Request, token: str, password: str = Form(...),
                 password2: str = Form(...)):
    with db.get_db() as con:
        user = db.reset_user(con, token)
        if not user:
            return templates.TemplateResponse(
                request, "pages/reset.html",
                _auth_ctx(request, token=token, invalid=True), status_code=404)
        error = None
        if len(password) < 8:
            error = "New password must be at least 8 characters."
        elif password != password2:
            error = "New passwords do not match."
        if error:
            return templates.TemplateResponse(
                request, "pages/reset.html",
                _auth_ctx(request, token=token, invalid=False, username=user["username"],
                          error=error), status_code=422)
        db.consume_reset(con, token, password)
    return RedirectResponse("/login?reset=1", status_code=303)


# ── My account (password change + language) ────────────────────────────────

@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request, changed: int = 0, saved_q: int = 0):
    info = None
    if changed:
        info = "Password changed. Other devices were signed out."
    elif saved_q:
        info = "Recovery question saved."
    with db.get_db() as con:
        u = con.execute("SELECT security_question FROM users WHERE id = ?",
                        (request.state.user["id"],)).fetchone()
    return templates.TemplateResponse(request, "pages/account.html", ctx(
        request, "account", info=info, error=None, q_error=None,
        current_question=u["security_question"] if u else None,
        questions=db.SECURITY_QUESTIONS))


@app.post("/account/password", response_class=HTMLResponse)
def change_password(request: Request, current: str = Form(...), new: str = Form(...),
                    new2: str = Form(...)):
    user = request.state.user
    error = None
    if not db.verify_password(current, user["password_hash"]):
        error = "Current password is wrong."
    elif len(new) < 8:
        error = "New password must be at least 8 characters."
    elif new != new2:
        error = "New passwords do not match."
    if error:
        return templates.TemplateResponse(
            request, "pages/account.html",
            ctx(request, "account", info=None, error=error), status_code=422)
    token = request.cookies.get(SESSION_COOKIE)
    with db.get_db() as con:
        con.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                    (db.hash_password(new), user["id"]))
        # Sign out every other device; the session that made the change survives.
        con.execute("DELETE FROM sessions WHERE user_id = ? AND token != ?",
                    (user["id"], token or ""))
    return RedirectResponse("/account?changed=1", status_code=303)


@app.post("/account/security", response_class=HTMLResponse)
def set_security_question(request: Request, question: str = Form(...), answer: str = Form(...)):
    user = request.state.user
    with db.get_db() as con:
        if not question.strip() or len(answer.strip()) < 2:
            u = con.execute("SELECT security_question FROM users WHERE id = ?",
                            (user["id"],)).fetchone()
            return templates.TemplateResponse(request, "pages/account.html", ctx(
                request, "account", info=None, error=None,
                q_error="Choose a question and give an answer (2+ characters).",
                current_question=u["security_question"] if u else None,
                questions=db.SECURITY_QUESTIONS), status_code=422)
        db.set_security(con, user["id"], question, answer)
    return RedirectResponse("/account?saved_q=1", status_code=303)


# ── Team management (owner only) ───────────────────────────────────────────

def _owner_or_none(request: Request):
    user = getattr(request.state, "user", None)
    return user if user and user["role"] == "owner" else None


def _team_row_html(request: Request, con, user_id: int, me_id: int) -> str:
    u = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return templates.get_template("partials/team_row.html").render(
        {"request": request, "u": u, "me_id": me_id,
         "owner_count": db.owner_count(con), "t": _t_for(request)})


@app.get("/team", response_class=HTMLResponse)
def team_page(request: Request):
    me = _owner_or_none(request)
    if not me:
        return RedirectResponse("/", status_code=303)
    with db.get_db() as con:
        users = con.execute(
            "SELECT * FROM users ORDER BY approved, CASE role WHEN 'owner' THEN 0 ELSE 1 END, "
            "username").fetchall()
        n_owners = db.owner_count(con)
    pending = [u for u in users if not u["approved"]]
    return templates.TemplateResponse(request, "pages/team.html", ctx(
        request, "team", users=users, me_id=me["id"], owner_count=n_owners,
        pending_n=len(pending)))


@app.post("/team/{user_id}/approve", response_class=HTMLResponse)
def team_approve(request: Request, user_id: int):
    me = _owner_or_none(request)
    if not me:
        return _toast("", "Owners only", 403)
    with db.get_db() as con:
        u = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not u:
            return _toast("", "User not found", 404)
        con.execute("UPDATE users SET approved = 1 WHERE id = ?", (user_id,))
        html = _team_row_html(request, con, user_id, me["id"])
    return _toast(html, f"{u['username']} approved - they can sign in now")


@app.post("/team/{user_id}/role", response_class=HTMLResponse)
def team_role(request: Request, user_id: int, role: str = Form(...)):
    me = _owner_or_none(request)
    if not me:
        return _toast("", "Owners only", 403)
    if role not in ("owner", "helper"):
        return _toast("", "Unknown role", 422)
    with db.get_db() as con:
        u = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not u:
            return _toast("", "User not found", 404)
        if (u["role"] == "owner" and role == "helper"
                and u["approved"] and db.owner_count(con) <= 1):
            return _toast("", "The farm needs at least one owner", 422)
        con.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        html = _team_row_html(request, con, user_id, me["id"])
    return _toast(html, f"{u['username']} is now a {role}")


@app.post("/team/{user_id}/reset", response_class=HTMLResponse)
def team_reset(request: Request, user_id: int):
    """Owner generates a one-time reset link to hand the member in person.
    Swaps a copyable link panel into the page; the toast just confirms."""
    me = _owner_or_none(request)
    if not me:
        return _toast("", "Owners only", 403)
    with db.get_db() as con:
        u = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not u:
            return _toast("", "User not found", 404)
        token = db.create_reset(con, user_id)
    link = str(request.base_url).rstrip("/") + f"/reset/{token}"
    html = templates.get_template("partials/reset_link.html").render(
        {"request": request, "u": u, "link": link, "hours": db.RESET_HOURS,
         "t": _t_for(request)})
    return _toast(html, f"Reset link created for {u['username']}")


@app.post("/team/{user_id}/remove", response_class=HTMLResponse)
def team_remove(request: Request, user_id: int):
    me = _owner_or_none(request)
    if not me:
        return _toast("", "Owners only", 403)
    if user_id == me["id"]:
        return _toast("", "You cannot remove yourself", 422)
    with db.get_db() as con:
        u = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not u:
            return _toast("", "User not found", 404)
        if u["role"] == "owner" and u["approved"] and db.owner_count(con) <= 1:
            return _toast("", "The farm needs at least one owner", 422)
        con.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        con.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return _toast("", f"{u['username']} removed")


def _svg_trend(days: list[dict], width: int = 640, height: int = 140) -> str:
    """Server-rendered bar chart of daily litres — no JS chart lib."""
    if not days:
        return ""
    mx = max((d["total"] for d in days), default=0) or 1
    n = len(days)
    gap, pad_top, pad_bot = 6, 18, 18
    bw = (width - gap * (n - 1)) / n
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
             f'role="img" aria-label="Daily milk production, last {n} days" '
             f'preserveAspectRatio="none">']
    for i, d in enumerate(days):
        h = (d["total"] / mx) * (height - pad_top - pad_bot)
        x, y = i * (bw + gap), height - pad_bot - h
        cls = "var(--accent)" if i == n - 1 else "var(--accent-soft-bar, var(--border-strong))"
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(h, 1):.1f}" rx="3" '
            f'fill="{cls}"><title>{d["date"]}: {d["total"]} L</title></rect>')
    parts.append(
        f'<text x="0" y="12" font-size="11" fill="var(--text-faint)">{mx:.0f} L peak</text>')
    parts.append(
        f'<text x="{width}" y="{height - 4}" text-anchor="end" font-size="11" '
        f'fill="var(--text-faint)">today</text>')
    parts.append("</svg>")
    return "".join(parts)


# ── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    today = date.today()
    with db.get_db() as con:
        herd_n = con.execute("SELECT COUNT(*) n FROM cows WHERE status != 'sold'").fetchone()["n"]
        milking_n = con.execute("SELECT COUNT(*) n FROM cows WHERE status = 'milking'").fetchone()["n"]
        days = db.daily_totals(con, today, 14)
        today_total = days[-1]["total"]
        yday_total = days[-2]["total"] if len(days) > 1 else 0
        withholds = db.active_withholdings(con, today)
        calvings = db.upcoming_calvings(con, today, 30)
        drops = db.yield_drop_alerts(con, today)
        month_start = today.replace(day=1)
        rev = con.execute(
            "SELECT COALESCE(SUM(litres * price_per_litre), 0) v FROM sales WHERE collected_on >= ?",
            (db.iso(month_start),)).fetchone()["v"]
    delta = today_total - yday_total
    t = i18n.make_t(i18n.get_lang(request))
    stats = [
        {"label": "Milk today", "value": f"{today_total:.1f} L",
         "delta": f"{delta:+.1f} L {t('vs yesterday')}", "dir": "up" if delta >= 0 else "down"},
        {"label": "Milking cows", "value": str(milking_n),
         "delta": f"{t('of')} {herd_n} {t('in herd')}", "dir": "up"},
        {"label": "Withholding", "value": str(len(withholds)),
         "delta": t("DO NOT TANK") if withholds else t("all clear"),
         "dir": "down" if withholds else "up"},
        {"label": "Revenue this month", "value": f"{CURRENCY}{inr_format(rev)}",
         "delta": t("from collections"), "dir": "up"},
    ]
    empty_herd = herd_n == 0
    forecast = _herd_forecast()
    return templates.TemplateResponse(request, "pages/dashboard.html", ctx(
        request, "dashboard", stats=stats, withholds=withholds, calvings=calvings,
        drops=drops, trend_svg=_svg_trend(days), empty_herd=empty_herd,
        forecast=forecast,
        forecast_svg=_svg_forecast(forecast["days"]) if forecast else ""))


@app.post("/demo-seed", response_class=HTMLResponse)
def demo_seed():
    with db.get_db() as con:
        if con.execute("SELECT COUNT(*) n FROM cows").fetchone()["n"] == 0:
            db.seed_demo(con, date.today())
    return HTMLResponse("", headers={"HX-Redirect": "/"})


# ── Herd ───────────────────────────────────────────────────────────────────

def _cow_row_html(request: Request, con, cow_id: int) -> str:
    cow = con.execute("SELECT * FROM cows WHERE id = ?", (cow_id,)).fetchone()
    return templates.get_template("partials/cow_row.html").render(
        {"request": request, "cow": cow, "statuses": db.COW_STATUSES,
         "today": db.iso(date.today()), "t": _t_for(request)})


@app.get("/cows", response_class=HTMLResponse)
def cows_page(request: Request):
    with db.get_db() as con:
        cows = con.execute(
            "SELECT * FROM cows ORDER BY CASE status WHEN 'milking' THEN 0 WHEN 'dry' THEN 1 "
            "WHEN 'heifer' THEN 2 WHEN 'calf' THEN 3 ELSE 4 END, tag").fetchall()
    return templates.TemplateResponse(request, "pages/cows.html", ctx(
        request, "cows", cows=cows, statuses=db.COW_STATUSES))


@app.post("/cows", response_class=HTMLResponse)
def create_cow(request: Request, tag: str = Form(...), name: str = Form(""),
               breed: str = Form(""), dob: str = Form(""), status: str = Form("milking")):
    tag = tag.strip()
    if not tag:
        return _toast("", "Tag is required", 422)
    if status not in db.COW_STATUSES:
        status = "milking"
    with db.get_db() as con:
        dup = con.execute("SELECT id FROM cows WHERE tag = ?", (tag,)).fetchone()
        if dup:
            return _toast("", f"Tag #{tag} already exists", 422)
        cur = con.execute(
            "INSERT INTO cows (tag, name, breed, dob, status) VALUES (?,?,?,?,?)",
            (tag, name.strip(), breed.strip(), dob or None, status))
        html = _cow_row_html(request, con, cur.lastrowid)
    return _toast(html, f"Added #{tag} {name.strip()}".strip())


@app.post("/cows/{cow_id}/status", response_class=HTMLResponse)
def update_cow_status(request: Request, cow_id: int, status: str = Form(...)):
    if status not in db.COW_STATUSES:
        return _toast("", "Unknown status", 422)
    with db.get_db() as con:
        cow = con.execute("SELECT * FROM cows WHERE id = ?", (cow_id,)).fetchone()
        if not cow:
            return _toast("", "Cow not found", 404)
        con.execute("UPDATE cows SET status = ? WHERE id = ?", (status, cow_id))
        html = _cow_row_html(request, con, cow_id)
    return _toast(html, f"#{cow['tag']} is now {status}")


# ── Milk logging (the product) ─────────────────────────────────────────────

def _milk_page_data(con, log_date: date, session: str):
    cows = con.execute("SELECT * FROM cows WHERE status = 'milking' ORDER BY tag").fetchall()
    logs = db.session_logs(con, log_date, session)
    prev_session = "AM" if session == "PM" else "PM"
    prev_date = log_date if session == "PM" else log_date - timedelta(days=1)
    prev_logs = db.session_logs(con, prev_date, prev_session)
    withheld = db.withheld_cow_ids(con, date.today())
    total = round(sum(logs.values()), 1)
    return cows, logs, prev_logs, withheld, total


@app.get("/milk", response_class=HTMLResponse)
def milk_page(request: Request, d: str | None = None, session: str | None = None):
    log_date = db.parse_date(d, date.today())
    if session not in ("AM", "PM"):
        session = "AM" if datetime.now().hour < 12 else "PM"
    with db.get_db() as con:
        cows, logs, prev_logs, withheld, total = _milk_page_data(con, log_date, session)
        logged_n = len([c for c in cows if c["id"] in logs])
    return templates.TemplateResponse(request, "pages/milk.html", ctx(
        request, "milk", cows=cows, logs=logs, prev_logs=prev_logs, withheld=withheld,
        log_date=db.iso(log_date), session=session, total=total, logged_n=logged_n))


@app.post("/milk/log", response_class=HTMLResponse)
def log_milk(request: Request, cow_id: int = Form(...), log_date: str = Form(...),
             session: str = Form(...), litres: str = Form(...)):
    if session not in ("AM", "PM"):
        return _toast("", "Session must be AM or PM", 422)
    day = db.parse_date(log_date)
    if not day:
        return _toast("", "Bad date", 422)
    try:
        val = float(litres)
    except ValueError:
        return _toast("", "Litres must be a number", 422)
    if not (0 <= val <= 80):
        return _toast("", "Litres must be between 0 and 80", 422)
    with db.get_db() as con:
        cow = con.execute("SELECT * FROM cows WHERE id = ?", (cow_id,)).fetchone()
        if not cow:
            return _toast("", "Cow not found", 404)
        con.execute(
            "INSERT INTO milk_logs (cow_id, log_date, session, litres) VALUES (?,?,?,?) "
            "ON CONFLICT (cow_id, log_date, session) DO UPDATE SET litres = excluded.litres",
            (cow_id, db.iso(day), session, val))
        logs = db.session_logs(con, day, session)
        withheld = db.withheld_cow_ids(con, date.today())
        total = round(sum(logs.values()), 1)
        row = templates.get_template("partials/milk_row.html").render(
            {"request": request, "cow": cow, "logs": logs, "prev_logs": {},
             "withheld": withheld, "log_date": db.iso(day), "session": session,
             "t": _t_for(request)})
    oob = (f'<span id="session-total" hx-swap-oob="true">{total:.1f} L</span>'
           f'<span id="logged-count" hx-swap-oob="true">{len(logs)}</span>')
    return _toast(row + oob, f"#{cow['tag']}: {val:g} L saved")


# ── Health / treatments ────────────────────────────────────────────────────

@app.get("/treatments", response_class=HTMLResponse)
def treatments_page(request: Request):
    today = date.today()
    with db.get_db() as con:
        rows = con.execute(
            """SELECT t.*, c.tag, c.name FROM treatments t JOIN cows c ON c.id = t.cow_id
               ORDER BY t.treated_on DESC LIMIT 200""").fetchall()
        cows = con.execute(
            "SELECT id, tag, name FROM cows WHERE status != 'sold' ORDER BY tag").fetchall()
    treatments = []
    for r in rows:
        clear = db.withhold_clear_date(r["treated_on"], r["withhold_days"])
        treatments.append({**dict(r), "clear_date": db.iso(clear), "active": clear > today})
    return templates.TemplateResponse(request, "pages/treatments.html", ctx(
        request, "health", treatments=treatments, cows=cows))


@app.post("/treatments", response_class=HTMLResponse)
def create_treatment(request: Request, cow_id: int = Form(...), drug: str = Form(...),
                     treated_on: str = Form(...), withhold_days: int = Form(0),
                     notes: str = Form("")):
    day = db.parse_date(treated_on)
    if not day or not drug.strip():
        return _toast("", "Drug and a valid date are required", 422)
    withhold_days = max(0, min(120, int(withhold_days)))
    today = date.today()
    with db.get_db() as con:
        cow = con.execute("SELECT * FROM cows WHERE id = ?", (cow_id,)).fetchone()
        if not cow:
            return _toast("", "Cow not found", 404)
        cur = con.execute(
            "INSERT INTO treatments (cow_id, drug, treated_on, withhold_days, notes) VALUES (?,?,?,?,?)",
            (cow_id, drug.strip(), db.iso(day), withhold_days, notes.strip()))
        r = con.execute(
            "SELECT t.*, c.tag, c.name FROM treatments t JOIN cows c ON c.id = t.cow_id WHERE t.id = ?",
            (cur.lastrowid,)).fetchone()
    clear = db.withhold_clear_date(r["treated_on"], r["withhold_days"])
    t = {**dict(r), "clear_date": db.iso(clear), "active": clear > today}
    html = templates.get_template("partials/treatment_row.html").render(
        {"request": request, "tr": t, "t": _t_for(request)})
    msg = (f"#{cow['tag']} treated - milk withheld until {t['clear_date']}"
           if t["active"] else f"Treatment recorded for #{cow['tag']}")
    return _toast(html, msg)


# ── Breeding ───────────────────────────────────────────────────────────────

@app.get("/breeding", response_class=HTMLResponse)
def breeding_page(request: Request):
    today = date.today()
    with db.get_db() as con:
        rows = con.execute(
            """SELECT b.*, c.tag, c.name FROM breedings b JOIN cows c ON c.id = b.cow_id
               ORDER BY CASE b.outcome WHEN 'calved' THEN 1 ELSE 0 END, b.due_date LIMIT 200"""
        ).fetchall()
        cows = con.execute(
            "SELECT id, tag, name FROM cows WHERE status IN ('milking','dry','heifer') ORDER BY tag"
        ).fetchall()
    breedings = [{**dict(r),
                  "days_left": (date.fromisoformat(r["due_date"]) - today).days}
                 for r in rows]
    default_due = db.iso(today + timedelta(days=db.GESTATION_DAYS))
    return templates.TemplateResponse(request, "pages/breeding.html", ctx(
        request, "breeding", breedings=breedings, cows=cows, default_due=default_due,
        gestation=db.GESTATION_DAYS))


@app.post("/breeding", response_class=HTMLResponse)
def create_breeding(request: Request, cow_id: int = Form(...), inseminated_on: str = Form(...),
                    due_date: str = Form(""), notes: str = Form("")):
    day = db.parse_date(inseminated_on)
    if not day:
        return _toast("", "A valid insemination date is required", 422)
    due = db.parse_date(due_date) or (day + timedelta(days=db.GESTATION_DAYS))
    with db.get_db() as con:
        cow = con.execute("SELECT * FROM cows WHERE id = ?", (cow_id,)).fetchone()
        if not cow:
            return _toast("", "Cow not found", 404)
        cur = con.execute(
            "INSERT INTO breedings (cow_id, inseminated_on, due_date, notes) VALUES (?,?,?,?)",
            (cow_id, db.iso(day), db.iso(due), notes.strip()))
        r = con.execute(
            "SELECT b.*, c.tag, c.name FROM breedings b JOIN cows c ON c.id = b.cow_id WHERE b.id = ?",
            (cur.lastrowid,)).fetchone()
    b = {**dict(r), "days_left": (due - date.today()).days}
    html = templates.get_template("partials/breeding_row.html").render(
        {"request": request, "b": b, "t": _t_for(request)})
    return _toast(html, f"#{cow['tag']} bred - due {db.iso(due)}")


@app.post("/breeding/{breeding_id}/outcome", response_class=HTMLResponse)
def breeding_outcome(request: Request, breeding_id: int, outcome: str = Form(...),
                     calf_tag: str = Form("")):
    if outcome not in ("open", "confirmed", "calved", "lost"):
        return _toast("", "Unknown outcome", 422)
    today = date.today()
    with db.get_db() as con:
        r = con.execute(
            "SELECT b.*, c.tag, c.name FROM breedings b JOIN cows c ON c.id = b.cow_id WHERE b.id = ?",
            (breeding_id,)).fetchone()
        if not r:
            return _toast("", "Record not found", 404)
        calf_id = None
        msg = f"#{r['tag']}: {outcome}"
        if outcome == "calved":
            tag = calf_tag.strip() or f"{r['tag']}-C{breeding_id}"
            existing = con.execute("SELECT id FROM cows WHERE tag = ?", (tag,)).fetchone()
            if existing:
                return _toast("", f"Calf tag #{tag} already exists", 422)
            calf_id = con.execute(
                "INSERT INTO cows (tag, name, breed, dob, status, notes) VALUES (?,?,?,?,?,?)",
                (tag, "", "", db.iso(today), "calf", f"Calf of #{r['tag']}")).lastrowid
            msg = f"#{r['tag']} calved - calf #{tag} added to herd"
        con.execute("UPDATE breedings SET outcome = ?, calf_cow_id = COALESCE(?, calf_cow_id) "
                    "WHERE id = ?", (outcome, calf_id, breeding_id))
        r2 = con.execute(
            "SELECT b.*, c.tag, c.name FROM breedings b JOIN cows c ON c.id = b.cow_id WHERE b.id = ?",
            (breeding_id,)).fetchone()
    b = {**dict(r2), "days_left": (date.fromisoformat(r2["due_date"]) - today).days}
    html = templates.get_template("partials/breeding_row.html").render(
        {"request": request, "b": b, "t": _t_for(request)})
    return _toast(html, msg)


# ── Milk sales ─────────────────────────────────────────────────────────────

@app.get("/sales", response_class=HTMLResponse)
def sales_page(request: Request):
    today = date.today()
    with db.get_db() as con:
        rows = con.execute("SELECT * FROM sales ORDER BY collected_on DESC LIMIT 100").fetchall()
        months = con.execute(
            """SELECT substr(collected_on, 1, 7) ym, SUM(litres) litres,
                      SUM(litres * price_per_litre) revenue
               FROM sales GROUP BY ym ORDER BY ym DESC LIMIT 6""").fetchall()
    return templates.TemplateResponse(request, "pages/sales.html", ctx(
        request, "sales", sales=rows, months=months, today=db.iso(today)))


@app.post("/sales", response_class=HTMLResponse)
def create_sale(request: Request, collected_on: str = Form(...), litres: str = Form(...),
                price_per_litre: str = Form(...), notes: str = Form("")):
    day = db.parse_date(collected_on)
    try:
        li, price = float(litres), float(price_per_litre)
    except ValueError:
        return _toast("", "Litres and price must be numbers", 422)
    if not day or li <= 0 or price <= 0:
        return _toast("", "Valid date, litres and price are required", 422)
    with db.get_db() as con:
        cur = con.execute(
            "INSERT INTO sales (collected_on, litres, price_per_litre, notes) VALUES (?,?,?,?)",
            (db.iso(day), li, price, notes.strip()))
        s = con.execute("SELECT * FROM sales WHERE id = ?", (cur.lastrowid,)).fetchone()
    html = templates.get_template("partials/sale_row.html").render(
        {"request": request, "s": s, "currency": CURRENCY, "t": _t_for(request)})
    return _toast(html, f"Collection saved - Rs {inr_format(li * price, 2)}")


# ── CSV export ─────────────────────────────────────────────────────────────

@app.get("/export/{table}.csv")
def export_csv(table: str):
    if table not in db.EXPORT_TABLES:
        return PlainTextResponse("unknown table", status_code=404)
    with db.get_db() as con:
        rows = con.execute(f"SELECT * FROM {table}").fetchall()  # table from whitelist
    buf = io.StringIO()
    writer = csv.writer(buf)
    if rows:
        writer.writerow(rows[0].keys())
        writer.writerows([list(r) for r in rows])
    else:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({table})").fetchall()]
        writer.writerow(cols)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{table}.csv"'})


# ── Open data contracts: versioned read-only JSON API ──────────────────────
# The machine-readable siblings of the CSV export: same whitelist, same data,
# plus a schema endpoint any consumer can program against. Auth is handled in
# the middleware (session or feed token).

DATA_SCHEMA_VERSION = "1.0"


def _json(payload: dict, status: int = 200) -> Response:
    return Response(json.dumps(payload, indent=2, default=str), status_code=status,
                    media_type="application/json")


@app.get("/api/v1/schema")
def api_schema():
    tables = {}
    with db.get_db() as con:
        for t in db.EXPORT_TABLES:
            tables[t] = [
                {"name": c[1], "type": c[2], "notnull": bool(c[3]), "pk": bool(c[5])}
                for c in con.execute(f"PRAGMA table_info({t})").fetchall()]  # t from whitelist
    return _json({"schema_version": DATA_SCHEMA_VERSION, "tables": tables})


@app.get("/api/v1/{table}.json")
def api_table(table: str):
    if table not in db.EXPORT_TABLES:
        return _json({"error": "unknown table"}, 404)
    with db.get_db() as con:
        rows = [dict(r) for r in con.execute(f"SELECT * FROM {table}").fetchall()]
    return _json({"schema_version": DATA_SCHEMA_VERSION, "table": table,
                  "row_count": len(rows), "rows": rows})


# ── Governed metrics API (G2.2) ─────────────────────────────────────────────
# The semantic layer's versioned metric definitions, served with receipts:
# every value ships its definition, owner, lineage, and the exact SQL. Values
# are recomputed from the gold layer per request — the governance guard's
# never-sum-a-ratio rule is honored because the golden expression recomputes
# ratios from components at whatever grain is asked.

import sqlite3 as _sqlite3

RUN_DIR = os.environ.get(
    "BARNBOARD_RUNDIR",
    str(Path(__file__).resolve().parents[4] / "data-team-out" / "barnboard"))


def _metric_defs() -> dict[str, dict]:
    defs: dict[str, dict] = {}
    try:
        for f in sorted((Path(RUN_DIR) / "semantic" / "metrics").glob("*.json")):
            m = json.loads(f.read_text())
            if m.get("metric"):
                defs[m["metric"]] = m
    except OSError:
        pass
    return defs


def _golden_sql(m: dict, by: str | None) -> str | None:
    agg, meas = m.get("aggregation"), m.get("measure")
    if agg == "sum":
        expr = f'sum("{meas}")'
    elif agg == "count":
        expr = f'count("{meas}")' if meas else "count(*)"
    elif agg in ("min", "max", "avg"):
        expr = f'{agg}("{meas}")'
    elif agg == "ratio":
        expr = f'sum("{m.get("numerator")}")*1.0/nullif(sum("{m.get("denominator")}"),0)'
    elif agg == "derived":
        expr = m.get("expression", "")
    else:
        return None
    table = (m.get("rollups") or {}).get("daily", "").removeprefix("gold.")
    if not (table and expr):
        return None
    if by:
        return (f'SELECT "{by}", {expr} AS "{m["metric"]}" FROM "{table}" '
                f'GROUP BY "{by}" ORDER BY 2 DESC')
    return f'SELECT {expr} AS "{m["metric"]}" FROM "{table}"'


@app.get("/api/v1/metrics")
def api_metrics():
    defs = _metric_defs()
    return _json({"schema_version": DATA_SCHEMA_VERSION, "count": len(defs), "metrics": [
        {"metric": k, "label": v.get("label", ""), "version": v.get("version", ""),
         "aggregation": v.get("aggregation", ""), "owner": v.get("owner", ""),
         "unit": v.get("unit", ""), "dimensions": v.get("dimensions", [])}
        for k, v in sorted(defs.items())]})


@app.get("/api/v1/metrics/{metric_id}")
def api_metric(metric_id: str, by: str = ""):
    m = _metric_defs().get(metric_id)
    if not m:
        return _json({"error": "unknown metric"}, 404)
    dim = by or None
    if dim and dim not in (m.get("dimensions") or []):
        return _json({"error": "dimension not declared for this metric"}, 422)
    sql = _golden_sql(m, dim)
    if not sql:
        return _json({"error": "metric not computable"}, 422)
    gold = Path(RUN_DIR) / "gold" / "gold.db"
    if not gold.exists():
        return _json({"error": "gold layer unavailable"}, 503)
    con = _sqlite3.connect(f"file:{gold}?mode=ro", uri=True)
    try:
        rows = con.execute(sql).fetchall()
    finally:
        con.close()
    rnd = int(m.get("round", 2))
    if dim:
        value = [[r[0], round(r[1], rnd) if r[1] is not None else None] for r in rows]
    else:
        v = rows[0][0] if rows else None
        value = round(v, rnd) if v is not None else None
    return _json({"schema_version": DATA_SCHEMA_VERSION, "metric": metric_id,
                  "value": value, "by": dim, "unit": m.get("unit", ""),
                  "receipt": {"version": m.get("version"), "owner": m.get("owner"),
                              "aggregation": m.get("aggregation"),
                              "definition": m.get("description", ""),
                              "lineage": m.get("lineage", []), "sql": sql}})


# ── Inference: yield forecasts from versioned model artifacts ──────────────
# Parameters live in models/yield_forecast/<version>/params.json (trained by
# tools/train_models.py); LATEST names the served version. Both are read per
# request, so bumping LATEST hot-reloads with zero code changes.

MODELS_DIR = os.environ.get(
    "BARNBOARD_MODELS", str(Path(__file__).resolve().parents[4] / "models"))


def _load_yield_model() -> dict | None:
    base = Path(MODELS_DIR) / "yield_forecast"
    try:
        version = (base / "LATEST").read_text().strip()
        return json.loads((base / version / "params.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _holt_path(level: float, trend: float, horizon: int, damp: float) -> list[float]:
    out, cum = [], 0.0
    for h in range(1, horizon + 1):
        cum += damp ** h
        out.append(max(0.0, level + cum * trend))
    return out


@app.get("/api/v1/predict/yield/{cow_id}")
def api_predict_yield(cow_id: int, days: int = 7):
    model = _load_yield_model()
    if not model:
        return _json({"error": "no model artifact"}, 503)
    cow = model["cows"].get(str(cow_id))
    if not cow:
        return _json({"error": "unknown cow"}, 404)
    horizon = max(1, min(days, 30))
    preds = _holt_path(cow["level"], cow["trend"], horizon, model.get("damp", 0.92))
    start = date.fromisoformat(cow["trained_through"])
    return _json({
        "schema_version": DATA_SCHEMA_VERSION,
        "model": model["model"], "model_version": model["version"],
        "cow_id": cow_id, "tag": cow["tag"], "breed": cow["breed"],
        "trained_through": cow["trained_through"],
        "forecast": [{"date": db.iso(start + timedelta(days=h)),
                      "litres": round(v, 1)}
                     for h, v in enumerate(preds, start=1)]})


def _herd_forecast(horizon: int = 7) -> dict | None:
    """Sum per-cow forecasts into a herd daily path for the dashboard panel."""
    model = _load_yield_model()
    if not model or not model["cows"]:
        return None
    damp = model.get("damp", 0.92)
    days_total = [0.0] * horizon
    latest = max(c["trained_through"] for c in model["cows"].values())
    for c in model["cows"].values():
        for i, v in enumerate(_holt_path(c["level"], c["trend"], horizon, damp)):
            days_total[i] += v
    start = date.fromisoformat(latest)
    return {"version": model["version"],
            "days": [{"date": db.iso(start + timedelta(days=i + 1)), "total": round(v, 1)}
                     for i, v in enumerate(days_total)]}


def _svg_forecast(days: list[dict], width: int = 640, height: int = 140) -> str:
    """Server-rendered forecast bars, same visual language as _svg_trend."""
    mx = max((d["total"] for d in days), default=0) or 1
    n = len(days)
    gap, pad_top, pad_bot = 6, 18, 18
    bw = (width - gap * (n - 1)) / n
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="7-day forecast" '
             f'preserveAspectRatio="none" style="width:100%;height:140px">']
    for i, d in enumerate(days):
        h = (d["total"] / mx) * (height - pad_top - pad_bot)
        x, y = i * (bw + gap), height - pad_bot - h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(h, 1):.1f}" rx="3" '
            f'fill="var(--accent-soft-bar, var(--border-strong))" opacity="0.75" '
            f'stroke="var(--accent)" stroke-dasharray="3 2">'
            f'<title>{d["date"]}: {d["total"]} L (forecast)</title></rect>')
    parts.append(
        f'<text x="0" y="12" font-size="11" fill="var(--text-faint)">{mx:.0f} L peak</text>')
    parts.append(
        f'<text x="{width}" y="{height - 4}" text-anchor="end" font-size="11" '
        f'fill="var(--text-faint)">+7d</text>')
    parts.append("</svg>")
    return "".join(parts)


# ── iCal reminder feed ─────────────────────────────────────────────────────

def _ics_event(uid: str, day: date, summary: str, description: str = "") -> str:
    dt = day.strftime("%Y%m%d")
    end = (day + timedelta(days=1)).strftime("%Y%m%d")
    lines = [
        "BEGIN:VEVENT", f"UID:{uid}@barnboard",
        f"DTSTAMP:{dt}T000000Z",
        f"DTSTART;VALUE=DATE:{dt}", f"DTEND;VALUE=DATE:{end}",
        f"SUMMARY:{summary}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{description}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


@app.get("/calendar.ics")
def calendar_feed_redirect():
    """Legacy/browser entry point (login-protected by middleware): bounce to
    the secret-token URL, which is what actually goes into a calendar app."""
    with db.get_db() as con:
        token = db.feed_token(con)
    return RedirectResponse(f"/calendar/{token}.ics", status_code=303)


@app.get("/calendar/{token}.ics")
def calendar_feed(token: str):
    """Subscribe once in any calendar app; farm deadlines appear on the phone.
    Zero notification infrastructure — the calendar app does the reminding.
    Public by secret token, because calendar apps cannot log in."""
    with db.get_db() as con:
        expected = db.feed_token(con)
    if not expected or not secrets.compare_digest(token, expected):
        return PlainTextResponse("not found", status_code=404)
    today = date.today()
    events = []
    with db.get_db() as con:
        for w in db.active_withholdings(con, today):
            events.append(_ics_event(
                f"withhold-{w['id']}", date.fromisoformat(w["clear_date"]),
                f"Milk OK again: #{w['tag']} {w['name']}".strip(),
                f"Withholding ends ({w['drug']}). Milk may go to the tank from this day."))
        for b in db.upcoming_calvings(con, today, within_days=400):
            due = date.fromisoformat(b["due_date"])
            events.append(_ics_event(
                f"calving-{b['id']}", due,
                f"Calving due: #{b['tag']} {b['name']}".strip(),
                f"Expected calving ({b['outcome']}). Bred {b['inseminated_on']}."))
            dry = due - timedelta(days=db.DRY_OFF_BEFORE_DUE)
            if dry >= today and b["outcome"] == "confirmed":
                events.append(_ics_event(
                    f"dryoff-{b['id']}", dry,
                    f"Dry off: #{b['tag']} {b['name']}".strip(),
                    f"Planned dry-off {db.DRY_OFF_BEFORE_DUE} days before {b['due_date']}."))
    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Barnboard//EN",
        "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{APP_NAME} reminders",
        *events, "END:VCALENDAR", ""])
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition": 'inline; filename="barnboard.ics"'})


# ── Roadmap + health ───────────────────────────────────────────────────────

@app.get("/roadmap", response_class=HTMLResponse)
def roadmap_page(request: Request):
    return templates.TemplateResponse(request, "pages/roadmap.html",
                                      ctx(request, "roadmap", roadmap=ROADMAP))


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"
