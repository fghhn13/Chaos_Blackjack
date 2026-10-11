"""Small WSGI application. All game state and credentials stay on the server."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import mimetypes
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from http.cookies import SimpleCookie
from pathlib import Path

from chaos_blackjack.agent import AgentSession

LOG = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
SESSION_AGE = 7 * 86400
USERNAME = re.compile(r"[A-Za-z0-9_]{3,32}\Z")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return f"scrypt${salt}${key.hex()}"


def check_password(password: str, stored: str) -> bool:
    _, salt, expected = stored.split("$")
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return hmac.compare_digest(actual.hex(), expected)


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class Application:
    def __init__(self, db_path: str | Path | None = None, *, invitation: str | None = None,
                 secure: bool | None = None):
        self.db_path = Path(db_path or os.environ.get("BLACKJACK_WEB_DB", "data/web.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.secure = secure if secure is not None else os.environ.get("BLACKJACK_SECURE_COOKIE", "1") == "1"
        invitation = invitation or os.environ.get("BLACKJACK_REGISTRATION_TOKEN", "")
        if not re.fullmatch(r"[0-9]{16}", invitation):
            raise RuntimeError("BLACKJACK_REGISTRATION_TOKEN must contain 16 digits")
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS session (
                    token TEXT PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES account(id),
                    csrf TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS game (
                    account_id INTEGER PRIMARY KEY REFERENCES account(id),
                    state TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES account(id),
                    result TEXT NOT NULL, bankroll INTEGER NOT NULL, rounds INTEGER NOT NULL,
                    chaos INTEGER NOT NULL, created INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempt (key TEXT PRIMARY KEY, count INTEGER NOT NULL,
                    until INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS browser_save (
                    account_id INTEGER PRIMARY KEY REFERENCES account(id),
                    snapshot TEXT NOT NULL, revision INTEGER NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO setting VALUES ('invitation', ?)", (digest(invitation),))
            # A bootstrap administrator is explicit; registrants never acquire admin rights.
            admin_password = os.environ.get("BLACKJACK_ADMIN_PASSWORD")
            if admin_password:
                self.validate_password(admin_password)
                db.execute("INSERT OR IGNORE INTO account(username,password,admin,created) VALUES (?,?,1,?)",
                           (os.environ.get("BLACKJACK_ADMIN_USER", "admin"), hash_password(admin_password), int(time.time())))
        self.dummy_password = hash_password(secrets.token_urlsafe(24))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def validate_password(password):
        if not isinstance(password, str) or not 10 <= len(password) <= 128:
            raise APIError(400, "Password must be 10–128 characters.")

    @staticmethod
    def account_dict(user):
        return {"id": user["id"], "username": user["username"], "admin": bool(user["admin"])}

    def cookie(self, token: str, age: int = SESSION_AGE) -> str:
        return f"blackjack_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}" + ("; Secure" if self.secure else "")

    def authenticate(self, db, env):
        cookie = SimpleCookie()
        try:
            cookie.load(env.get("HTTP_COOKIE", ""))
            token = cookie["blackjack_session"].value
        except (KeyError, ValueError):
            raise APIError(401, "Please sign in.")
        user = db.execute("""SELECT a.*, s.csrf, s.token AS session_token FROM session s
            JOIN account a ON a.id=s.account_id WHERE s.token=? AND s.expires>? AND a.enabled=1""",
                          (digest(token), int(time.time()))).fetchone()
        if not user:
            raise APIError(401, "Session expired. Please sign in.")
        return user

    def create_session(self, db, user):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute("DELETE FROM session WHERE expires<?", (int(time.time()),))
        db.execute("INSERT INTO session VALUES (?,?,?,?)",
                   (digest(token), user["id"], csrf, int(time.time()) + SESSION_AGE))
        return {"ok": True, "user": self.account_dict(user), "csrf": csrf}, [("Set-Cookie", self.cookie(token))]

    def auth_limit(self, env, data):
        # Commit limits independently so rejected authentication still counts.
        now = int(time.time())
        address = env.get("REMOTE_ADDR", "unknown")
        if os.environ.get("BLACKJACK_TRUST_PROXY") == "1" and address in ("127.0.0.1", "::1"):
            forwarded = env.get("HTTP_X_REAL_IP", "")
            try:
                address = str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
        keys = ["ip:" + address]
        if isinstance(data.get("username"), str):
            keys.append("user:" + data["username"].casefold())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM attempt WHERE until<?", (now,))
            for key in keys:
                row = db.execute("SELECT count FROM attempt WHERE key=?", (key,)).fetchone()
                if row and row["count"] >= 30:
                    raise APIError(429, "Too many sign-in attempts. Try again in 10 minutes.")
            for key in keys:
                db.execute("INSERT INTO attempt VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1",
                           (key, now + 600))

    def dispatch(self, env, data):
        path, method = env["PATH_INFO"], env["REQUEST_METHOD"]
        if path == "/healthz" and method == "GET":
            with self.connect() as db:
                db.execute("SELECT 1").fetchone()
            return {"ok": True, "revision": os.environ.get("BLACKJACK_REVISION", "local")}, []
        if path in ("/api/login", "/api/register") and method == "POST":
            self.auth_limit(env, data)
            username, password = data.get("username", ""), data.get("password", "")
            if not isinstance(username, str) or not USERNAME.fullmatch(username):
                raise APIError(400, "Username must be 3–32 letters, digits or underscores.")
            username = username.lower()
            self.validate_password(password)
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                user = db.execute("SELECT * FROM account WHERE username=?", (username,)).fetchone()
                if path == "/api/register":
                    token = data.get("token", "")
                    expected = db.execute("SELECT value FROM setting WHERE key='invitation'").fetchone()[0]
                    if not isinstance(token, str) or not hmac.compare_digest(digest(token), expected):
                        raise APIError(403, "Invalid invitation token.")
                    if user:
                        raise APIError(409, "Username already exists.")
                    db.execute("INSERT INTO account(username,password,created) VALUES (?,?,?)",
                               (username, hash_password(password), int(time.time())))
                    user = db.execute("SELECT * FROM account WHERE username=?", (username,)).fetchone()
                elif not check_password(password, user["password"] if user else self.dummy_password) or not user or not user["enabled"]:
                    raise APIError(401, "Invalid username or password.")
                return self.create_session(db, user)
        with self.connect() as db:
            if method == "POST":
                db.execute("BEGIN IMMEDIATE")
            user = self.authenticate(db, env)
            if method == "POST" and not hmac.compare_digest(env.get("HTTP_X_CSRF_TOKEN", ""), user["csrf"]):
                raise APIError(403, "Invalid security token. Reload the page.")
            uid = user["id"]
            if path == "/api/browser-save":
                row = db.execute("SELECT snapshot,revision FROM browser_save WHERE account_id=?", (uid,)).fetchone()
                revision = row["revision"] if row else 0
                if method == "GET":
                    return {"ok": True, "snapshot": row["snapshot"] if row else "", "revision": revision}, []
                if method == "POST":
                    snapshot = data.get("snapshot")
                    if not isinstance(snapshot, str) or len(snapshot.encode()) > 2_000_000:
                        raise APIError(400, "Save exceeds the 2 MB limit.")
                    if type(data.get("revision")) is not int or data["revision"] != revision:
                        raise APIError(409, "Save changed in another tab. Reload to use the latest save.")
                    # Opaque client data: never execute SQL or deserialize it on the server.
                    revision += 1
                    db.execute("INSERT INTO browser_save VALUES (?,?,?) ON CONFLICT(account_id) DO UPDATE SET snapshot=excluded.snapshot,revision=excluded.revision",
                               (uid, snapshot, revision))
                    return {"ok": True, "revision": revision}, []
            if path == "/api/me" and method == "GET":
                return {"ok": True, "user": self.account_dict(user), "csrf": user["csrf"]}, []
            if path == "/api/logout" and method == "POST":
                db.execute("DELETE FROM session WHERE token=?", (user["session_token"],))
                return {"ok": True}, [("Set-Cookie", self.cookie("", 0))]
            if path == "/api/password" and method == "POST":
                self.validate_password(data.get("password"))
                old = data.get("current_password", "")
                if not isinstance(old, str) or len(old) > 128 or not check_password(old, user["password"]):
                    raise APIError(403, "Current password is incorrect.")
                db.execute("UPDATE account SET password=? WHERE id=?", (hash_password(data["password"]), uid))
                db.execute("DELETE FROM session WHERE account_id=?", (uid,))
                return {"ok": True}, [("Set-Cookie", self.cookie("", 0))]
            if path == "/api/history" and method == "GET":
                rows = db.execute("SELECT result,bankroll,rounds,chaos,created FROM history WHERE account_id=? ORDER BY id DESC LIMIT 20", (uid,))
                return {"ok": True, "history": [dict(r) for r in rows]}, []
            if path.startswith("/api/admin/"):
                if not user["admin"]:
                    raise APIError(403, "Administrator access required.")
                if path == "/api/admin/accounts" and method == "GET":
                    rows = db.execute("SELECT id,username,admin,enabled,created FROM account ORDER BY id")
                    return {"ok": True, "accounts": [dict(r) for r in rows]}, []
                if path == "/api/admin/account" and method == "POST":
                    target, enabled = data.get("id"), data.get("enabled")
                    if type(target) is not int or type(enabled) is not bool:
                        raise APIError(400, "An account id and enabled flag are required.")
                    if target == uid:
                        raise APIError(400, "You cannot disable your own account.")
                    changed = db.execute("UPDATE account SET enabled=? WHERE id=? AND admin=0", (int(enabled), target))
                    if not changed.rowcount:
                        raise APIError(404, "Account not found or is an administrator.")
                    if not enabled:
                        db.execute("DELETE FROM session WHERE account_id=?", (target,))
                    return {"ok": True}, []
                if path == "/api/admin/invitation" and method == "POST":
                    token = "".join(secrets.choice("0123456789") for _ in range(16))
                    db.execute("UPDATE setting SET value=? WHERE key='invitation'", (digest(token),))
                    return {"ok": True, "token": token}, []
            if path == "/api/game" and method == "GET":
                row = db.execute("SELECT * FROM game WHERE account_id=?", (uid,)).fetchone()
                if not row:
                    return {"ok": True, "obs": None, "revision": 0, "events": []}, []
                return {**AgentSession.from_state(json.loads(row["state"])).execute({"cmd": "observe"}), "revision": row["revision"]}, []
            if path in ("/api/game/new", "/api/game/command") and method == "POST":
                row = db.execute("SELECT * FROM game WHERE account_id=?", (uid,)).fetchone()
                revision = row["revision"] if row else 0
                if type(data.get("revision")) is not int or data["revision"] != revision:
                    raise APIError(409, "The table changed in another tab. Refresh and try again.")
                if path.endswith("/new"):
                    if type(data.get("chaos", False)) is not bool:
                        raise APIError(400, "Invalid game mode.")
                    game = AgentSession.new(chaos=data.get("chaos", False), use_llm=False)
                    reply = game.execute({"cmd": "observe"})
                else:
                    if not row:
                        raise APIError(409, "Start a run first.")
                    game = AgentSession.from_state(json.loads(row["state"]))
                    command = data.get("command")
                    if not isinstance(command, dict) or command.get("cmd") not in ("bet", "buy", "act"):
                        raise APIError(400, "Invalid game command.")
                    reply = game.execute(command)
                    if not reply["ok"]:
                        return {**reply, "revision": revision}, []
                    if reply["obs"]["phase"] == "run_over":
                        obs = reply["obs"]
                        db.execute("INSERT INTO history(account_id,result,bankroll,rounds,chaos,created) VALUES (?,?,?,?,?,?)",
                                   (uid, obs["run_end"]["kind"], obs["bankroll"], obs["round"], int(obs["chaos"]["enabled"]), int(time.time())))
                revision += 1
                db.execute("INSERT INTO game VALUES (?,?,?) ON CONFLICT(account_id) DO UPDATE SET state=excluded.state,revision=excluded.revision",
                           (uid, json.dumps(game.to_state()), revision))
                return {**reply, "revision": revision}, []
        raise APIError(404, "Endpoint not found.")

    def __call__(self, env, start_response):
        headers = [("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
                   ("Referrer-Policy", "same-origin"), ("Cache-Control", "no-store"),
                   ("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]
        status = 200
        try:
            path = env.get("PATH_INFO", "/")
            method = env.get("REQUEST_METHOD", "GET")
            head_only = method == "HEAD"
            if head_only:
                env = {**env, "REQUEST_METHOD": "GET"}
                method = "GET"
            if method not in ("GET", "POST"):
                raise APIError(405, "Method not allowed.")
            if path.startswith("/play/") and method == "GET":
                with self.connect() as db:
                    self.authenticate(db, env)
                root = Path(os.environ.get("BLACKJACK_BROWSER_BUILD", "build/pygame/build/web")).resolve()
                target = (root / (path[6:] or "index.html")).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    raise APIError(404, "Game asset not found.")
                body = target.read_bytes()
                mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if target.suffix == ".wasm":
                    mime = "application/wasm"
                headers.append(("Content-Type", mime))
                # Pygbag's generated loader needs inline scripts and WASM compilation.
                # This policy is restricted to the authenticated game frame.
                headers = [(k, v) for k, v in headers if k not in ("Content-Security-Policy", "X-Frame-Options")]
                headers += [("X-Frame-Options", "SAMEORIGIN"), ("Content-Security-Policy",
                             "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; media-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")]
            elif path in ("/", "/static/app.js", "/static/style.css") and method == "GET":
                name, mime = {"/": ("index.html", "text/html"), "/static/app.js": ("app.js", "text/javascript"),
                              "/static/style.css": ("style.css", "text/css")}[path]
                body = (STATIC / name).read_bytes()
                headers.append(("Content-Type", mime + "; charset=utf-8"))
            else:
                data = {}
                if method == "POST":
                    origin = env.get("HTTP_ORIGIN")
                    scheme = env.get("HTTP_X_FORWARDED_PROTO", env.get("wsgi.url_scheme", "http"))
                    if origin and origin != f"{scheme}://{env.get('HTTP_HOST', '')}":
                        raise APIError(403, "Cross-origin requests are not allowed.")
                    if env.get("CONTENT_TYPE", "").split(";")[0] != "application/json":
                        raise APIError(415, "JSON requests are required.")
                    try:
                        size = int(env.get("CONTENT_LENGTH") or 0)
                        limit = 2_100_000 if path == "/api/browser-save" else 8192
                        if not 0 < size <= limit:
                            raise APIError(413, "Request is too large or empty.")
                        data = json.loads(env["wsgi.input"].read(size))
                        if not isinstance(data, dict):
                            raise ValueError()
                    except (ValueError, UnicodeError):
                        raise APIError(400, "Invalid JSON request.")
                result, extra = self.dispatch(env, data)
                headers.extend(extra)
                headers.append(("Content-Type", "application/json; charset=utf-8"))
                body = json.dumps(result, ensure_ascii=False).encode()
        except APIError as exc:
            status = exc.status
            headers.append(("Content-Type", "application/json; charset=utf-8"))
            body = json.dumps({"ok": False, "error": {"message": exc.message}}).encode()
        except Exception:
            LOG.exception("Web request failed")
            status = 500
            headers.append(("Content-Type", "application/json; charset=utf-8"))
            body = b'{"ok":false,"error":{"message":"Server error. Please try again."}}'
        from http import HTTPStatus
        headers.append(("Content-Length", str(len(body))))
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [] if head_only else [body]


def create_app():
    return Application()
