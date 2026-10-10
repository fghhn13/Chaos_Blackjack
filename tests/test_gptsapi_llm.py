"""GPTsAPI backend — offline tests with a fake transport (no network, no billing)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from chaos_blackjack.ai.gptsapi_llm import (
    DEFAULT_USER_AGENT,
    NOOP_JSON,
    GptsApiClient,
    GptsApiLLM,
)

KEY = "sk-test-secret-123"


class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _client_with(responder) -> tuple[GptsApiClient, list]:
    c = GptsApiClient(KEY, "https://api2.gptsapi.net")
    sent: list = []

    def fake_open(req, timeout=None):
        sent.append(req)
        return responder(req)

    c._opener.open = fake_open  # type: ignore[method-assign]  # noqa: SLF001
    return c, sent


def _json(data) -> _FakeResponse:
    return _FakeResponse(json.dumps(data).encode())


@pytest.mark.parametrize(
    "url",
    ["http://api2.gptsapi.net/v1", "https://api2.gptsapi.net/v1/chat/completions",
     "https://user:pw@api2.gptsapi.net", "https://api2.gptsapi.net/v1?x=1"],
)
def test_rejects_unsafe_base_urls(url: str) -> None:
    with pytest.raises(ValueError):
        GptsApiClient(KEY, url)


def test_requires_real_key_and_normalises_v1() -> None:
    with pytest.raises(ValueError):
        GptsApiClient("", "https://api2.gptsapi.net/v1")
    with pytest.raises(ValueError):
        GptsApiClient("sk-your-key-here")
    assert GptsApiClient(KEY, "https://api2.gptsapi.net/").base_url == "https://api2.gptsapi.net/v1"
    assert GptsApiClient(KEY, "https://api2.gptsapi.net/v1").base_url == "https://api2.gptsapi.net/v1"


def test_chat_request_shape_and_answer() -> None:
    c, sent = _client_with(lambda req: _json(
        {"model": "claude-opus-5-5", "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
         "usage": {"total_tokens": 46}}))
    out = c.chat([{"role": "user", "content": "hi"}], "claude-opus-5-5", 16)
    assert out["answer"] == "OK" and out["usage"] == {"total_tokens": 46}
    req = sent[0]
    assert req.full_url == "https://api2.gptsapi.net/v1/chat/completions"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == f"Bearer {KEY}"
    assert req.get_header("User-agent") == DEFAULT_USER_AGENT
    body = json.loads(req.data)
    assert body == {"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 16, "stream": False}


def test_models_lists_ids() -> None:
    c, sent = _client_with(lambda req: _json({"data": [{"id": "a"}, {"id": "b"}]}))
    assert c.models()["models"] == ["a", "b"]
    assert sent[0].get_method() == "GET"


def test_http_error_is_redacted() -> None:
    def boom(req):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(f"bad key {KEY}".encode()))

    c, _ = _client_with(boom)
    with pytest.raises(RuntimeError) as e:
        c.models()
    assert "HTTP 401" in str(e.value) and KEY not in str(e.value)


def test_api_error_payload_raises() -> None:
    c, _ = _client_with(lambda req: _json({"error": {"message": "model not found"}}))
    with pytest.raises(RuntimeError, match="model not found"):
        c.chat([{"role": "user", "content": "x"}])


def test_llm_backend_sends_system_and_user_and_falls_back_to_noop() -> None:
    c, sent = _client_with(lambda req: _json({"choices": [{"message": {"content": ' {"action":"noop"} '}}]}))
    llm = GptsApiLLM(c, model="m", max_tokens=99)
    assert llm.complete("SYS", "USER") == '{"action":"noop"}'
    body = json.loads(sent[0].data)
    assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert body["max_tokens"] == 99

    def down(req):
        raise urllib.error.URLError("connection reset")

    c._opener.open = lambda req, timeout=None: down(req)  # type: ignore[method-assign]  # noqa: SLF001
    assert llm.complete("SYS", "USER") == NOOP_JSON
    assert llm.last_error and "Network error" in llm.last_error


def test_game_defaults_to_stub_when_llm_disabled() -> None:
    from chaos_blackjack.ai.pipeline import StubLLM
    from chaos_blackjack.core.game_loop import GameLoop

    assert isinstance(GameLoop().pipeline.llm, StubLLM)


def test_env_file_parser_and_no_override(tmp_path, monkeypatch) -> None:
    from chaos_blackjack.ai.env import load_dotenv_from_project_root, parse_env_file

    p = tmp_path / ".env"
    p.write_text(
        "# comment\nexport A=1\nB = 'two words'\nC=x # trailing\nnot a line\nD=\"q\"\n",
        encoding="utf-8",
    )
    assert parse_env_file(p) == {"A": "1", "B": "two words", "C": "x", "D": "q"}
    monkeypatch.setenv("A", "from-process")
    monkeypatch.delenv("B", raising=False)
    load_dotenv_from_project_root(p)
    import os

    assert os.environ["A"] == "from-process" and os.environ["B"] == "two words"
