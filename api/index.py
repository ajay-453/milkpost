"""Vercel entrypoint for barnboard-app-v2 — betadoc at the front, the real app
behind the /demo PIN gate. Mirrors betadoc/betadoc_server.py's routing as a
pure ASGI wrapper; the application code is untouched.

  /                    betadoc site (or the app dashboard once PIN'd — that is
                       where the app's post-login redirect lands)
  /documentation.html  betadoc documentation page
  /demo                PIN gate -> signed cookie;  /demo/exit drops it
  everything else      the Barnboard app, only with a valid PIN cookie

The SQLite DB lives in /tmp (ephemeral): a self-reseeding synthetic demo, not a
stateful host. DEMO_LOGIN provisions a ready-to-use account on cold start.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "aina-out", "barnboard", "app")
SITE = os.path.join(ROOT, "betadoc-data", "site")
sys.path.insert(0, APP_DIR)

# Twin knobs — set BEFORE importing the app (db.py reads DB_PATH at import).
os.environ.setdefault("DB_PATH", "/tmp/barnboard.db")
os.environ.setdefault("BARNBOARD_SEED", "1")
os.environ.setdefault("DEMO_LOGIN", "demo:farm12345")
# On Vercel, models are trained at cold start on the instance's own seeded
# herd (G2.3) so forecast dates are fresh; locally the repo artifacts serve.
os.environ.setdefault("BARNBOARD_MODELS",
                      "/tmp/models" if os.environ.get("VERCEL")
                      else os.path.join(ROOT, "models"))
# Sessions must survive across lambda instances: each instance has its own
# /tmp database, so DB-backed sessions bounce users back to /login whenever a
# click lands on a different instance. Stateless signed-cookie sessions fix
# that — the signing key comes from the SESSION_SECRET env var (set in the
# Vercel project); the derived fallback only covers local rehearsal.
os.environ.setdefault("STATELESS_SESSIONS", "1")
if os.environ.get("VERCEL"):
    # HTTPS is guaranteed on Vercel: mark the app session cookie Secure (G0.2)
    os.environ.setdefault("SECURE_COOKIES", "1")
os.environ.setdefault("SESSION_SECRET", hashlib.sha256(
    f"bb-v2-session-fallback:{os.environ.get('BETADOC_PIN', '4276')}".encode()).hexdigest())

from app.main import app as barnboard  # noqa: E402
from app.main import _ensure_seed  # noqa: E402

_models_ready = False


def _ensure_models() -> None:
    """G2.3: train on this instance's seeded herd once per cold start, so the
    served forecast starts tomorrow instead of at a stale bundled date. The
    trainer is stdlib and ~100ms at demo scale; failure just hides the panel."""
    global _models_ready
    if _models_ready:
        return
    _models_ready = True
    if not os.environ.get("VERCEL"):
        return
    try:
        latest = os.path.join(os.environ["BARNBOARD_MODELS"], "yield_forecast", "LATEST")
        if not os.path.exists(latest):
            _ensure_seed()                      # DB must exist before training
            sys.path.insert(0, os.path.join(ROOT, "tools"))
            import train_models as _tm
            cows = _tm.load_series_from_app(os.environ["DB_PATH"])
            if cows:
                _tm.run_training(cows, os.environ["BARNBOARD_MODELS"], "v1")
    except Exception:
        pass

PIN = os.environ.get("BETADOC_PIN", "8437")   # rotated 2026-09-09 (request-based access)
# Demo-access requests (mirrors betadoc_server.py): email in, PIN out — by
# SMTP when configured, on screen otherwise. On Vercel the lead log goes to
# stdout (visible in function logs) plus ephemeral /tmp.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "Barnboard <onboarding@resend.dev>")


def _resend_send(to_addr: str, subject: str, text: str) -> bool:
    """Send via the Resend HTTP API (no SDK — one urllib call). Note: until a
    sending domain is verified in Resend, the free tier delivers only to the
    account owner's own address — requester delivery then falls back to the
    on-screen reveal while owner notifications still work."""
    if not RESEND_API_KEY:
        return False
    import json as _json
    try:
        req = urllib.request.Request(
            "https://api.resend.com/emails", method="POST",
            data=_json.dumps({"from": RESEND_FROM, "to": [to_addr],
                              "subject": subject, "text": text}).encode(),
            headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _pin_email_text(creds) -> str:
    creds_txt = ""
    if creds:
        creds_txt = (f"Your personal demo login:\n"
                     f"  username: {creds['username']}\n"
                     f"  password: {creds['password']}\n\n"
                     "It works until you sign out twice - after that,\n"
                     "just request access again.\n\n")
    return ("Thanks for your interest in Barnboard!\n\n"
            f"Your demo access PIN: {PIN}\n\n" + creds_txt +
            "Enter the PIN at the /demo page, then sign in. Everything in\n"
            "the demo is synthetic data - explore freely.\n")


def _deliver_pin(email: str, creds) -> str:
    """Preferred: Resend -> SMTP -> on-screen. Owner always gets a lead
    notification when any email channel exists. Returns the delivery mode."""
    text = _pin_email_text(creds)
    delivered = "screen"
    if _resend_send(email, "Your Barnboard demo access PIN", text):
        delivered = "resend"
    elif _send_pin_email(email, creds):
        delivered = "smtp"
    if OWNER_EMAIL:
        _resend_send(OWNER_EMAIL, "Barnboard demo request",
                     f"New demo access request from: {email}\n"
                     f"Delivered via: {delivered}\n"
                     + (f"Issued login: {creds['username']}\n" if creds else ""))
    return delivered



def _log_request(email: str, delivered: str) -> None:
    import json as _json
    from datetime import datetime, timezone
    line = _json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "email": email, "delivered": delivered})
    print(f"DEMO-REQUEST {line}", flush=True)          # durable in Vercel logs
    try:
        with open("/tmp/demo-requests.jsonl", "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _send_pin_email(to_addr: str, creds: dict | None = None) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        return False
    import smtplib
    from email.message import EmailMessage
    try:
        msg = EmailMessage()
        msg["Subject"] = "Your Barnboard demo access PIN"
        msg["From"] = SMTP_FROM
        msg["To"] = to_addr
        if OWNER_EMAIL:
            msg["Bcc"] = OWNER_EMAIL
        creds_txt = ""
        if creds:
            creds_txt = (f"Your personal demo login:\n"
                         f"  username: {creds['username']}\n"
                         f"  password: {creds['password']}\n\n"
                         "It works until you sign out twice - after that,\n"
                         "just request access again.\n\n")
        msg.set_content(
            "Thanks for your interest in Barnboard!\n\n"
            f"Your demo access PIN: {PIN}\n\n" + creds_txt +
            "Enter the PIN at the /demo page, then sign in. Everything in\n"
            "the demo is synthetic data - explore freely.\n")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception:
        return False
# The PIN is the credential; the cookie secret only has to be stable across
# cold starts, so deriving it from the PIN is fine for a demo gate.
SECRET = os.environ.get("BETADOC_SECRET",
                        hashlib.sha256(f"bb-v2:{PIN}".encode()).hexdigest())
COOKIE = "bdd_demo"
TTL = 14 * 86400

GATE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Barnboard — demo access</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ctext x='1' y='13' font-size='13'%3E%F0%9F%93%88%3C/text%3E%3C/svg%3E">
<style>:root{{--bg:#f8f7f4;--fg:#1c1917;--mut:#6b6560;--card:#fff;--bd:#e7e5e4;--acc:#15803d}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f110f;--fg:#f5f5f4;--mut:#a8a29e;--card:#191c19;--bd:#2b2f2b;--acc:#2fb463}}}}
*{{box-sizing:border-box;margin:0}}body{{background:var(--bg);color:var(--fg);
font:16px/1.6 Inter,system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;padding:24px}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:34px;max-width:380px;width:100%;text-align:center}}
h1{{font-size:22px;margin:8px 0 4px}}p{{color:var(--mut);font-size:14px;margin-bottom:20px}}
input{{width:100%;padding:12px;font-size:22px;text-align:center;letter-spacing:.5em;border:1px solid var(--bd);
border-radius:10px;background:var(--bg);color:var(--fg)}}
button{{width:100%;margin-top:14px;padding:12px;font-size:15px;font-weight:600;border:0;border-radius:10px;
background:var(--acc);color:#fff;cursor:pointer}}.err{{color:#dc2626;font-size:14px;margin-top:10px}}
a{{color:var(--acc)}}.back{{margin-top:18px;font-size:13px}}</style></head><body>
<form class="card" method="post" action="/demo">
<div style="font-size:34px">&#128200;</div><h1>Data Platform live demo</h1>
<p>Enter the access PIN you were given to open the live application.</p>
<input name="pin" inputmode="numeric" autocomplete="one-time-code" maxlength="8" autofocus placeholder="&#183;&#183;&#183;&#183;">
<button type="submit">Open the demo</button>{err}
<div class="back">No PIN yet? <a href="/demo/request"><strong>Request access</strong></a></div>
<div class="back"><a href="/">&larr; back to the overview</a></div>
</form></body></html>"""

REQUEST_PAGE = GATE_PAGE.split("<form", 1)[0] + """<form class="card" method="post" action="/demo/request">
<div style="font-size:34px">&#9993;&#65039;</div><h1>Request demo access</h1>
<p>Leave your email and we'll send you the access PIN for the live demo.</p>
<input name="email" type="email" required autofocus placeholder="you@example.com"
  style="letter-spacing:normal;font-size:16px;text-align:left">
<button type="submit">Send me the PIN</button>{err}
<div class="back"><a href="/demo">I already have a PIN</a></div>
</form></body></html>"""

GRANTED_PAGE = GATE_PAGE.split("<form", 1)[0] + """<div class="card">
<div style="font-size:34px">&#9989;</div><h1>{title}</h1>
<p>{message}</p>
<div class="back"><a href="/demo"><strong>Enter the demo &rarr;</strong></a></div>
</div></body></html>"""


def _token() -> str:
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), ts.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{ts}.{sig}"


def _valid(token: str) -> bool:
    ts, _, sig = token.partition(".")
    if not ts.isdigit() or int(time.time()) - int(ts) > TTL:
        return False
    want = hmac.new(SECRET.encode(), ts.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, want)


def _cookie(scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            for part in value.decode(errors="replace").split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE:
                    return v
    return ""


async def _send(send, status: int, body: bytes, ctype: str, extra=()):
    headers = [(b"content-type", ctype.encode()),
               (b"content-length", str(len(body)).encode()), *extra]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _redirect(send, location: str, extra=()):
    await send({"type": "http.response.start", "status": 303,
                "headers": [(b"location", location.encode()),
                            (b"content-length", b"0"), *extra]})
    await send({"type": "http.response.body", "body": b""})


async def _site_file(send, name: str):
    try:
        with open(os.path.join(SITE, name), "rb") as f:
            await _send(send, 200, f.read(), "text/html; charset=utf-8")
    except OSError:
        await _send(send, 404, b"not found", "text/plain")


_ASSET_MIME = {".webm": "video/webm", ".mp4": "video/mp4", ".svg": "image/svg+xml",
               ".png": "image/png", ".jpg": "image/jpeg"}


async def _site_asset(scope, send, name: str):
    """Site assets with byte-range support (G4.4) so the hero video streams
    (206) instead of downloading whole. `name` is basename-flattened upstream."""
    path = os.path.join(SITE, "assets", name)
    ext = os.path.splitext(name)[1]
    ctype = _ASSET_MIME.get(ext, "application/octet-stream")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return await _send(send, 404, b"not found", "text/plain")
    rng = ""
    for hname, hval in scope.get("headers", []):
        if hname == b"range":
            rng = hval.decode(errors="replace")
    if rng.startswith("bytes=") and ext in (".webm", ".mp4"):
        try:
            start_s, _, end_s = rng[6:].split(",")[0].partition("-")
            start = int(start_s) if start_s else 0
            end = min(int(end_s) if end_s else len(data) - 1, len(data) - 1)
            if 0 <= start <= end:
                chunk = data[start:end + 1]
                return await _send(send, 206, chunk, ctype, [
                    (b"content-range", f"bytes {start}-{end}/{len(data)}".encode()),
                    (b"accept-ranges", b"bytes")])
        except ValueError:
            pass
    extra = [(b"accept-ranges", b"bytes")] if ext in (".webm", ".mp4") else []
    await _send(send, 200, data, ctype, extra)


async def app(scope, receive, send):
    if scope["type"] != "http":
        return await barnboard(scope, receive, send)
    _ensure_models()
    path = scope["path"]
    has_pin = _valid(_cookie(scope))

    if path.startswith("/api/v1/") or path == "/healthz":
        # Machine consumers can't hold a PIN cookie. The app's own middleware
        # enforces session-or-feed-token auth and answers JSON 401 (G0.1).
        return await barnboard(scope, receive, send)

    if path == "/" and not has_pin:
        return await _site_file(send, "index.html")
    if path == "/index.html":
        return await _site_file(send, "index.html")
    if path == "/documentation.html":
        return await _site_file(send, "documentation.html")
    if path.startswith("/assets/"):
        return await _site_asset(scope, send, os.path.basename(path))

    if path == "/demo" and scope["method"] == "GET":
        if has_pin:
            return await _redirect(send, "/login")
        return await _send(send, 200, GATE_PAGE.format(err="").encode(),
                           "text/html; charset=utf-8")
    if path == "/demo" and scope["method"] == "POST":
        body = b""
        while True:
            msg = await receive()
            body += msg.get("body", b"")
            if not msg.get("more_body"):
                break
        pin = ""
        for pair in body.decode(errors="replace").split("&"):
            k, _, v = pair.partition("=")
            if k == "pin":
                pin = urllib.parse.unquote_plus(v).strip()
        if hmac.compare_digest(pin, PIN):
            secure = "; Secure" if os.environ.get("VERCEL") else ""
            cookie = (f"{COOKIE}={_token()}; Path=/; HttpOnly; SameSite=Lax; "
                      f"Max-Age={TTL}{secure}")
            return await _redirect(send, "/login", [(b"set-cookie", cookie.encode())])
        page = GATE_PAGE.format(err='<div class="err">Wrong PIN — try again.</div>')
        return await _send(send, 401, page.encode(), "text/html; charset=utf-8")
    if path == "/demo/request" and scope["method"] == "GET":
        return await _send(send, 200, REQUEST_PAGE.format(err="").encode(),
                           "text/html; charset=utf-8")
    if path == "/demo/request" and scope["method"] == "POST":
        import re as _re
        body = b""
        while True:
            msg = await receive()
            body += msg.get("body", b"")
            if not msg.get("more_body"):
                break
        email = ""
        for pair in body.decode(errors="replace").split("&"):
            k, _, v = pair.partition("=")
            if k == "email":
                email = urllib.parse.unquote_plus(v).strip()
        if not _re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email):
            page = REQUEST_PAGE.format(err='<div class="err">That doesn\'t look like an email address.</div>')
            return await _send(send, 422, page.encode(), "text/html; charset=utf-8")
        creds = None
        try:
            _ensure_seed()
            from app import db as _appdb
            with _appdb.get_db() as _con:
                _u, _pw = _appdb.create_temp_user(_con)
                creds = {"username": _u, "password": _pw}
        except Exception:
            pass
        mode = _deliver_pin(email, creds)
        if mode in ("resend", "smtp"):
            _log_request(email, mode)
            page = GRANTED_PAGE.format(title="Check your inbox",
                message=f"We've sent the access PIN and your personal demo login to <strong>{email}</strong>. It can take a minute to arrive.")
        else:
            _log_request(email, mode)
            cred_html = ""
            if creds:
                cred_html = (f"<br><br>Your personal demo login (valid until you sign out twice):<br>"
                             f"username <strong>{creds['username']}</strong> &middot; "
                             f"password <strong>{creds['password']}</strong>")
            page = GRANTED_PAGE.format(title="You're in",
                message=f"Thanks, <strong>{email}</strong>! Your access PIN is "
                        f"<strong style='font-size:22px;letter-spacing:.2em'>{PIN}</strong>" + cred_html)
        return await _send(send, 200, page.encode(), "text/html; charset=utf-8")
    if path == "/demo/exit":
        cookie = f"{COOKIE}=; Path=/; Max-Age=0"
        return await _redirect(send, "/", [(b"set-cookie", cookie.encode())])

    if not has_pin:
        return await _redirect(send, "/demo")
    return await barnboard(scope, receive, send)
