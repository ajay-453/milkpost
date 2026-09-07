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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "aina-out", "barnboard", "app")
SITE = os.path.join(ROOT, "betadoc-data", "site")
sys.path.insert(0, APP_DIR)

# Twin knobs — set BEFORE importing the app (db.py reads DB_PATH at import).
os.environ.setdefault("DB_PATH", "/tmp/barnboard.db")
os.environ.setdefault("BARNBOARD_SEED", "1")
os.environ.setdefault("DEMO_LOGIN", "demo:farm12345")
os.environ.setdefault("BARNBOARD_MODELS", os.path.join(ROOT, "models"))
# Sessions must survive across lambda instances: each instance has its own
# /tmp database, so DB-backed sessions bounce users back to /login whenever a
# click lands on a different instance. Stateless signed-cookie sessions fix
# that — the signing key comes from the SESSION_SECRET env var (set in the
# Vercel project); the derived fallback only covers local rehearsal.
os.environ.setdefault("STATELESS_SESSIONS", "1")
os.environ.setdefault("SESSION_SECRET", hashlib.sha256(
    f"bb-v2-session-fallback:{os.environ.get('BETADOC_PIN', '4276')}".encode()).hexdigest())

from app.main import app as barnboard  # noqa: E402

PIN = os.environ.get("BETADOC_PIN", "4276")
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
<div class="back"><a href="/">&larr; back to the overview</a></div>
</form></body></html>"""


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


async def app(scope, receive, send):
    if scope["type"] != "http":
        return await barnboard(scope, receive, send)
    path = scope["path"]
    has_pin = _valid(_cookie(scope))

    if path == "/" and not has_pin:
        return await _site_file(send, "index.html")
    if path == "/index.html":
        return await _site_file(send, "index.html")
    if path == "/documentation.html":
        return await _site_file(send, "documentation.html")

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
    if path == "/demo/exit":
        cookie = f"{COOKIE}=; Path=/; Max-Age=0"
        return await _redirect(send, "/", [(b"set-cookie", cookie.encode())])

    if not has_pin:
        return await _redirect(send, "/demo")
    return await barnboard(scope, receive, send)
