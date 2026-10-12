"""Security boundaries and persistent browser-game integration."""
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from chaos_blackjack.web.server import Application

TOKEN = "1234567890123456"


def test_browser_cloud_saves_are_opaque_isolated_and_versioned(app):
    alice, bob = Client(app), Client(app)
    alice.register("alice"); bob.register("bobby")
    assert alice.request("/api/browser-save")[1]["snapshot"] == ""
    snapshot = "DROP TABLE account; -- opaque data must never execute"
    assert alice.request("/api/browser-save", {"snapshot": snapshot, "revision": 0}, csrf=False)[0] == 403
    status, reply, _ = alice.request("/api/browser-save", {"snapshot": snapshot, "revision": 0})
    assert status == 200 and reply["revision"] == 1
    assert alice.request("/api/browser-save")[1]["snapshot"] == snapshot
    assert bob.request("/api/browser-save")[1]["snapshot"] == ""
    assert alice.request("/api/browser-save", {"snapshot": "stale", "revision": 0})[0] == 409
    assert alice.request("/api/browser-save", {"snapshot": "bad", "revision": True})[0] == 409
    assert alice.request("/api/browser-save", {"snapshot": {}, "revision": 1})[0] == 400
    assert alice.request("/api/browser-save", {"snapshot": "x" * 2_000_001, "revision": 1})[0] == 400
    assert alice.request("/api/me")[0] == 200
    alice.app = Application(app.db_path, invitation=TOKEN)
    assert alice.request("/api/browser-save")[1]["revision"] == 1


def test_wasm_assets_require_session_and_confine_paths(app, tmp_path, monkeypatch):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "index.html").write_text("<html>game</html>")
    monkeypatch.setenv("BLACKJACK_BROWSER_BUILD", str(root))
    c = Client(app)
    assert c.request("/play/")[0] == 401
    c.register()
    assert c.request("/play/../../accounts.db")[0] == 404
    env = {"PATH_INFO": "/play/", "REQUEST_METHOD": "GET", "HTTP_COOKIE": c.cookie}
    headers = {}
    def start(status, values):
        headers.update(dict(values))
        assert status.startswith("200")
    assert b"game" in b"".join(app(env, start))
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    c.request("/api/logout", {})
    assert c.request("/play/")[0] == 401


def test_game_cache_revalidates_changes_and_disabled_sessions(app, tmp_path, monkeypatch):
    root = tmp_path / "bundle"
    root.mkdir()
    asset = root / "main.wasm"
    asset.write_bytes(b"wasm-one")
    (root / "index.html").write_text("<html>game</html>")
    monkeypatch.setenv("BLACKJACK_BROWSER_BUILD", str(root))
    c = Client(app)
    c.register()

    def get(path, etag="", method="GET"):
        response = {}
        def start(status, headers):
            response.update(status=int(status.split()[0]), headers=dict(headers))
        body = b"".join(app({"PATH_INFO": path, "REQUEST_METHOD": method,
                              "HTTP_COOKIE": c.cookie, "HTTP_IF_NONE_MATCH": etag}, start))
        return response["status"], body, response["headers"]

    status, body, headers = get("/play/main.wasm")
    assert status == 200 and body == b"wasm-one"
    assert headers["Content-Type"] == "application/wasm"
    assert headers["Cache-Control"] == "private, no-cache"
    tag = headers["ETag"]
    status, body, headers = get("/play/main.wasm", tag)
    assert status == 304 and body == b"" and "Content-Length" not in headers
    assert get("/play/main.wasm", '"other", ' + tag[2:])[0] == 304
    assert get("/play/", "*")[2]["Cache-Control"] == "no-store"
    asset.write_bytes(b"changed-wasm-content")
    status, body, headers = get("/play/main.wasm", tag)
    assert status == 200 and body == b"changed-wasm-content" and headers["ETag"] != tag
    assert get("/play/main.wasm", method="HEAD")[1] == b""
    c.request("/api/logout", {})
    assert get("/play/main.wasm", headers["ETag"])[0] == 401


class Client:
    def __init__(self, app):
        self.app, self.cookie, self.csrf = app, "", ""

    def request(self, path, data=None, *, csrf=True, origin=None):
        body = json.dumps(data).encode() if data is not None else b""
        env = {"PATH_INFO": path, "REQUEST_METHOD": "POST" if data is not None else "GET",
               "wsgi.input": io.BytesIO(body), "wsgi.url_scheme": "https", "HTTP_HOST": "example.test",
               "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": "application/json",
               "HTTP_COOKIE": self.cookie, "REMOTE_ADDR": "127.0.0.1"}
        if csrf:
            env["HTTP_X_CSRF_TOKEN"] = self.csrf
        if origin:
            env["HTTP_ORIGIN"] = origin
        response = {}
        def start(status, headers):
            response.update(status=int(status.split()[0]), headers=dict(headers))
        content = b"".join(self.app(env, start))
        result = json.loads(content)
        if "Set-Cookie" in response["headers"]:
            self.cookie = response["headers"]["Set-Cookie"].split(";")[0]
        self.csrf = result.get("csrf", self.csrf)
        return response["status"], result, response["headers"]

    def register(self, username="player", token=TOKEN):
        return self.request("/api/register", {"username": username, "password": "secure-password", "token": token})


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKJACK_ADMIN_PASSWORD", "admin-test-password")
    return Application(tmp_path / "accounts.db", invitation=TOKEN, secure=True)


def test_invitation_and_private_routes(app):
    c = Client(app)
    assert c.request("/api/game")[0] == 401
    assert c.register(token="wrong")[0] == 403
    status, data, headers = c.register()
    assert status == 200 and not data["user"]["admin"]
    assert all(flag in headers["Set-Cookie"] for flag in ("HttpOnly", "Secure", "SameSite=Lax"))
    assert c.request("/api/admin/accounts")[0] == 403
    assert c.request("/api/game/new", {"chaos": True, "revision": 0}, csrf=False)[0] == 403
    assert c.request("/api/game/new", {"chaos": True, "revision": 0}, origin="https://evil.test")[0] == 403


def test_game_persists_and_isolates_users(app):
    alice, bob = Client(app), Client(app)
    alice.register("alice"); bob.register("bobby")
    _, run, _ = alice.request("/api/game/new", {"chaos": True, "revision": 0})
    assert run["obs"]["bankroll"] == 100
    _, bet, _ = alice.request("/api/game/command", {"revision": run["revision"], "command": {"cmd": "bet", "amount": 10}})
    # Reconstruct the application to prove that saves survive a service restart.
    alice.app = Application(app.db_path, invitation=TOKEN)
    resumed = alice.request("/api/game")[1]
    assert resumed["obs"] == bet["obs"]
    assert bob.request("/api/game")[1]["obs"] is None
    assert "packed" not in json.dumps(bet) and "seed" not in bet
    assert alice.request("/api/game/command", {"revision": 1, "command": {"cmd": "bet", "amount": 10}})[0] == 409


def test_commands_are_serialized(app):
    c = Client(app); c.register()
    c.request("/api/game/new", {"chaos": False, "revision": 0})
    def bet(_):
        other = Client(app); other.cookie, other.csrf = c.cookie, c.csrf
        return other.request("/api/game/command", {"revision": 1, "command": {"cmd": "bet", "amount": 10}})[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(bet, range(2))) == [200, 409]


def test_password_logout_and_admin_disable(app):
    player, second, admin = Client(app), Client(app), Client(app)
    player.register()
    second.request("/api/login", {"username": "player", "password": "secure-password"})
    assert player.request("/api/password", {"current_password": "secure-password", "password": "changed-password"})[0] == 200
    assert second.request("/api/me")[0] == 401
    player.request("/api/login", {"username": "player", "password": "changed-password"})
    uid = player.request("/api/me")[1]["user"]["id"]
    admin.request("/api/login", {"username": "admin", "password": "admin-test-password"})
    assert admin.request("/api/admin/account", {"id": uid, "enabled": False})[0] == 200
    assert player.request("/api/me")[0] == 401
    assert player.request("/api/login", {"username": "player", "password": "changed-password"})[0] == 401
    assert admin.request("/api/admin/account", {"id": uid, "enabled": True})[0] == 200
    player.request("/api/login", {"username": "player", "password": "changed-password"})
    assert player.request("/api/logout", {})[0] == 200
    assert player.request("/api/me")[0] == 401


def test_invitation_rotation_and_auth_limit(app):
    admin = Client(app)
    admin.request("/api/login", {"username": "admin", "password": "admin-test-password"})
    token = admin.request("/api/admin/invitation", {})[1]["token"]
    assert len(token) == 16 and token.isdigit()
    c = Client(app)
    assert c.register("new_user")[0] == 403
    assert c.register("new_user", token)[0] == 200
    for _ in range(30):
        c.request("/api/login", {"username": "bad_user", "password": "wrong-password"})
    assert c.request("/api/login", {"username": "bad_user", "password": "wrong-password"})[0] == 429


def test_reject_arbitrary_runtime_options(app):
    c = Client(app); c.register()
    _, data, _ = c.request("/api/game/new", {"chaos": False, "revision": 0, "use_llm": True, "start_money": 9999})
    assert data["obs"]["bankroll"] == 100
    assert data["obs"]["chaos"]["enabled"] is False
    before = c.request("/api/game")[1]
    _, rejected, _ = c.request("/api/game/command", {"revision": 1, "command": {"cmd": "bet", "amount": 9999}})
    assert not rejected["ok"]
    assert c.request("/api/game")[1]["obs"] == before["obs"]
