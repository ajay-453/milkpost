"""Auth and team tests (TestForge-fix arc F5.1): first-run setup, signup ->
pending -> owner approval, roles and the last-owner rule, removal, password
recovery by question (with lockout) and by one-time link, logout. Same
throwaway-DB pattern as test_barnboard.py.

Run:  cd app && .venv/bin/python -m pytest -q
"""
import itertools
import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "test.db"))

from app import db, main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_ips = (f"198.51.100.{i}" for i in itertools.count(1))   # fresh IP per login: no rate-limit bleed
Q = "What is your village name?"
MEMBERS = ("founder", "ravi", "sita", "gopal", "lakshmi", "anil", "meena")


def _login(username, password):
    c = TestClient(main.app)
    r = c.post("/login", data={"username": username, "password": password},
               headers={"x-forwarded-for": next(_ips)}, follow_redirects=False)
    return c, r


def _uid(username):
    with db.get_db() as con:
        row = con.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return row["id"] if row else None


@pytest.fixture(scope="module")
def boss():
    db.init_db()
    with db.get_db() as con:   # start clean so the module can run twice in one process
        marks = ",".join("?" * len(MEMBERS))
        for table in ("sessions", "password_resets"):
            con.execute(f"DELETE FROM {table} WHERE user_id IN "
                        f"(SELECT id FROM users WHERE username IN ({marks}))", MEMBERS)
        con.execute(f"DELETE FROM users WHERE username IN ({marks})", MEMBERS)
        con.execute("UPDATE users SET role = 'owner' WHERE username = 'boss'")
        if not _uid("boss"):
            uid = db.create_user(con, "boss", "bosspass123", role="owner", approved=True)
            db.set_security(con, uid, Q, "kondapur")
    c, r = _login("boss", "bosspass123")
    assert r.status_code == 303
    return c


def _signup(username, password="helperpass1"):
    return TestClient(main.app).post("/signup", data={
        "username": username, "password": password, "password2": password,
        "question": Q, "answer": "nellore"}, follow_redirects=False)


# ── first run ───────────────────────────────────────────────────────────────

def test_setup_is_one_shot(boss, monkeypatch):
    anon = TestClient(main.app)
    assert anon.get("/setup", follow_redirects=False).headers["location"] == "/login"
    assert anon.post("/setup", data={"username": "x", "password": "p" * 8, "password2": "p" * 8},
                     follow_redirects=False).headers["location"] == "/login"
    monkeypatch.setattr(db, "has_users", lambda con: False)   # pretend first run
    assert anon.get("/login", follow_redirects=False).headers["location"] == "/setup"
    assert anon.get("/signup", follow_redirects=False).headers["location"] == "/setup"
    assert anon.get("/setup").status_code == 200
    bad = anon.post("/setup", data={"username": "founder", "password": "short", "password2": "short",
                                    "question": Q, "answer": "x"})
    assert bad.status_code == 422 and "at least 8" in bad.text
    ok = anon.post("/setup", data={"username": "founder", "password": "founderpass1",
                                   "password2": "founderpass1", "question": Q, "answer": "guntur"},
                   follow_redirects=False)
    assert ok.status_code == 303 and "bb_session" in ok.headers.get("set-cookie", "")
    with db.get_db() as con:
        u = con.execute("SELECT role, approved FROM users WHERE username='founder'").fetchone()
    assert (u["role"], u["approved"]) == ("owner", 1)


@pytest.mark.parametrize("form,msg", [
    ({"username": "a"}, "at least 2"),
    ({"password2": "different1"}, "do not match"),
    ({"question": " "}, "recovery question"),
    ({"answer": "z"}, "answer your recovery"),
])
def test_signup_validation(form, msg):
    data = {"username": "newbie", "password": "helperpass1", "password2": "helperpass1",
            "question": Q, "answer": "nellore", **form}
    r = TestClient(main.app).post("/signup", data=data)
    assert r.status_code == 422 and msg in r.text


# ── signup -> approval -> roles -> removal ──────────────────────────────────

def test_signup_waits_for_owner_approval(boss):
    assert TestClient(main.app).get("/signup").status_code == 200
    r = _signup("ravi")
    assert r.status_code == 303 and r.headers["location"] == "/login?pending=1"
    assert _signup("ravi").status_code == 422                       # taken
    assert "approve" in TestClient(main.app).get("/login", params={"pending": 1}).text
    _, denied = _login("ravi", "helperpass1")
    assert denied.status_code == 403
    uid = _uid("ravi")
    ok = boss.post(f"/team/{uid}/approve")
    assert ok.status_code == 200 and "approved" in ok.headers["x-toast"]
    assert boss.post("/team/999999/approve").status_code == 404
    helper, r = _login("ravi", "helperpass1")
    assert r.status_code == 303
    # helpers are not owners: team pages and actions are closed to them
    assert helper.get("/team", follow_redirects=False).headers["location"] == "/"
    for action in ("approve", "reset", "remove"):
        assert helper.post(f"/team/{uid}/{action}").status_code == 403
    assert helper.post(f"/team/{uid}/role", data={"role": "owner"}).status_code == 403


def test_roles_keep_at_least_one_owner(boss):
    _signup("sita")
    uid = _uid("sita")
    boss.post(f"/team/{uid}/approve")
    assert boss.post(f"/team/{uid}/role", data={"role": "king"}).status_code == 422
    assert boss.post("/team/999999/role", data={"role": "owner"}).status_code == 404
    up = boss.post(f"/team/{uid}/role", data={"role": "owner"})
    assert up.status_code == 200 and "now a owner" in up.headers["x-toast"]
    assert boss.post(f"/team/{uid}/role", data={"role": "helper"}).status_code == 200
    with db.get_db() as con:   # make boss the only approved owner, then try to demote
        con.execute("UPDATE users SET role='helper' WHERE role='owner' AND username != 'boss'")
    last = boss.post(f"/team/{_uid('boss')}/role", data={"role": "helper"})
    assert last.status_code == 422 and "at least one owner" in last.headers["x-toast"]
    assert boss.post(f"/team/{_uid('boss')}/remove").status_code == 422   # not yourself


def test_remove_member_ends_their_sessions(boss):
    _signup("gopal")
    uid = _uid("gopal")
    boss.post(f"/team/{uid}/approve")
    member, _ = _login("gopal", "helperpass1")
    assert member.get("/", follow_redirects=False).status_code == 200
    r = boss.post(f"/team/{uid}/remove")
    assert r.status_code == 200 and "removed" in r.headers["x-toast"]
    assert _uid("gopal") is None
    assert member.get("/", follow_redirects=False).status_code in (302, 303)
    assert boss.post("/team/999999/remove").status_code == 404
    assert boss.post("/team/999999/reset").status_code == 404


def test_remove_member_with_open_reset_link(boss):
    # regression: an unused reset link used to block removal (FK -> 500)
    _signup("gopal")
    uid = _uid("gopal")
    assert boss.post(f"/team/{uid}/reset").status_code == 200
    r = boss.post(f"/team/{uid}/remove")
    assert r.status_code == 200 and _uid("gopal") is None


# ── recovery: question, lockout, one-time link ──────────────────────────────

def test_forgot_by_question_and_lockout(boss):
    anon = TestClient(main.app)
    assert anon.get("/forgot").status_code == 200
    assert anon.post("/forgot", data={"username": "nobody"}).status_code == 404
    _signup("lakshmi")
    step = anon.post("/forgot", data={"username": "lakshmi"})
    assert step.status_code == 200 and Q in step.text
    form = {"username": "lakshmi", "answer": "nellore", "password": "brandnew12", "password2": "brandnew12"}
    assert anon.post("/forgot/reset", data={**form, "password": "short", "password2": "short"}).status_code == 422
    assert anon.post("/forgot/reset", data={**form, "password2": "mismatch12"}).status_code == 422
    assert anon.post("/forgot/reset", data={**form, "username": "nobody"},
                     follow_redirects=False).headers["location"] == "/forgot"
    ok = anon.post("/forgot/reset", data=form, follow_redirects=False)
    assert ok.headers["location"] == "/login?reset=1"
    with db.get_db() as con:
        assert db.authenticate(con, "lakshmi", "brandnew12") is not None
    wrong = {**form, "answer": "wrong"}
    codes = [anon.post("/forgot/reset", data=wrong).status_code for _ in range(db._RESET_MAX_FAILS)]
    assert codes[:-1] == [422] * (db._RESET_MAX_FAILS - 1) and codes[-1] == 429
    assert anon.post("/forgot", data={"username": "lakshmi"}).status_code == 429
    assert anon.post("/forgot/reset", data=form).status_code == 429   # right answer, still locked


def test_owner_reset_link_is_one_time(boss):
    _signup("anil")
    uid = _uid("anil")
    r = boss.post(f"/team/{uid}/reset")
    assert r.status_code == 200 and "/reset/" in r.text
    token = r.text.split("/reset/")[1].split('"')[0].split("<")[0].strip()
    anon = TestClient(main.app)
    page = anon.get(f"/reset/{token}")
    assert page.status_code == 200 and "anil" in page.text
    assert anon.post(f"/reset/{token}", data={"password": "short", "password2": "short"}).status_code == 422
    assert anon.post(f"/reset/{token}", data={"password": "newpass123", "password2": "other1234"}).status_code == 422
    ok = anon.post(f"/reset/{token}", data={"password": "newpass123", "password2": "newpass123"},
                   follow_redirects=False)
    assert ok.headers["location"] == "/login?reset=1"
    assert anon.get(f"/reset/{token}").status_code == 404           # used up
    assert anon.post(f"/reset/{token}", data={"password": "x" * 8, "password2": "x" * 8}).status_code == 404
    assert "new password" in anon.get("/login", params={"reset": 1}).text.lower()


# ── sessions ────────────────────────────────────────────────────────────────

def test_password_change_and_logout(boss):
    _signup("meena")
    boss.post(f"/team/{_uid('meena')}/approve")
    c, _ = _login("meena", "helperpass1")
    other, _ = _login("meena", "helperpass1")
    mism = c.post("/account/password", data={"current": "helperpass1", "new": "x" * 8, "new2": "y" * 8})
    assert mism.status_code == 422
    ok = c.post("/account/password", data={"current": "helperpass1", "new": "changed123",
                                           "new2": "changed123"}, follow_redirects=False)
    assert ok.headers["location"] == "/account?changed=1"
    assert c.get("/account", params={"changed": 1}).status_code == 200
    assert other.get("/", follow_redirects=False).status_code in (302, 303)   # other device signed out
    out = c.post("/logout", follow_redirects=False)
    assert out.headers["location"] == "/login"
    assert c.get("/", follow_redirects=False).status_code in (302, 303)
