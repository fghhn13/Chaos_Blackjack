"""GPTsAPI relay backend (OpenAI-compatible chat completions), stdlib only.

Ported from github.com/fghhn13/gptsapi-agent-starter (api.py). Contract:

* Base URL `https://api2.gptsapi.net/v1` (include `/v1` once)
* `Authorization: Bearer <GPTSAPI_API_KEY>`
* `GET /models` -> `data[].id`; `POST /chat/completions` with
  `model`, `messages`, `max_tokens`, `stream: false`
* Answer at `choices[0].message.content`
* A browser User-Agent is sent (the default Python UA got Cloudflare 1010)
* Redirects are rejected so the key is never forwarded elsewhere; TLS
  verification stays on; errors never include the key; no automatic retries.

Configuration (environment or project `.env`, process env wins):
  GPTSAPI_API_KEY, GPTSAPI_BASE_URL, GPTSAPI_MODEL,
  GPTSAPI_USER_AGENT, GPTSAPI_TIMEOUT, GPTSAPI_MAX_TOKENS
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.ai.env import load_dotenv_from_project_root

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://api2.gptsapi.net/v1"
DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_TIMEOUT = 45.0
DEFAULT_MAX_TOKENS = 256
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
PLACEHOLDER_KEY = "sk-your-key-here"
NOOP_JSON = '{"action":"noop"}'


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GptsApiClient:
    def __init__(
        self,
        key: str,
        base_url: str = DEFAULT_BASE,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if not key or key == PLACEHOLDER_KEY:
            raise ValueError("Set GPTSAPI_API_KEY in .env or the process environment")
        base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/v1")):
            raise ValueError("Base URL must be an HTTPS origin, optionally ending with /v1")
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        self.base_url = base_url if parsed.path == "/v1" else base_url + "/v1"
        self._key = key
        self.timeout = timeout
        self._headers = {
            "Authorization": "Bearer " + key,
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._opener = urllib.request.build_opener(_RejectRedirects())

    def redact(self, text: str) -> str:
        return text.replace(self._key, "[REDACTED]")

    def request(self, endpoint: str, payload: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + endpoint, data=body, headers=self._headers,
            method="GET" if payload is None else "POST",
        )
        start = time.monotonic()
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                data = json.load(response)
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = self.redact(exc.read(4096).decode("utf-8", errors="replace"))
            raise RuntimeError(f"HTTP {exc.code}: {detail[:1000]}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("Network error: " + self.redact(str(exc))) from None
        except (ValueError, UnicodeError):
            raise RuntimeError("API returned invalid JSON") from None
        if not isinstance(data, dict):
            raise RuntimeError("API returned an unexpected JSON shape")
        if "error" in data:
            detail = self.redact(json.dumps(data["error"], ensure_ascii=False))
            raise RuntimeError("API error: " + detail[:1000])
        return data, {"status": status, "seconds": round(time.monotonic() - start, 2)}

    def models(self) -> dict[str, Any]:
        data, meta = self.request("/models")
        try:
            ids = [item["id"] for item in data["data"]]
        except (KeyError, TypeError):
            raise RuntimeError("Model response is missing data[].id") from None
        return {**meta, "count": len(ids), "models": ids}

    def chat(self, messages: list[dict[str, str]], model: str = DEFAULT_MODEL, max_tokens: int = 128) -> dict[str, Any]:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        data, meta = self.request("/chat/completions", {
            "model": model, "messages": messages, "max_tokens": max_tokens, "stream": False,
        })
        try:
            answer = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("Chat response is missing choices[0].message.content") from None
        if not isinstance(answer, str):
            raise RuntimeError("Chat response content is not text")
        return {**meta, "model": data.get("model", model), "answer": answer,
                "usage": data.get("usage"), "finish_reason": data["choices"][0].get("finish_reason")}


@dataclass
class GptsApiLLM:
    """`LLMBackend` for ChaosPipeline. Never raises into the game loop:
    a failed request becomes a noop action and is kept in `last_error`."""

    client: GptsApiClient
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    last_error: str | None = field(default=None, init=False)
    last_usage: dict[str, Any] | None = field(default=None, init=False)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            result = self.client.chat(messages, self.model, self.max_tokens)
        except (RuntimeError, ValueError) as exc:
            self.last_error = str(exc)
            log.warning("Chaos LLM request failed: %s", self.last_error)
            return NOOP_JSON
        self.last_error = None
        self.last_usage = result.get("usage")
        text = result["answer"].strip()
        return text or NOOP_JSON


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def create_client_from_env() -> GptsApiClient:
    """Raises ValueError when the key / URL is missing or invalid."""
    load_dotenv_from_project_root()
    return GptsApiClient(
        os.environ.get("GPTSAPI_API_KEY", "").strip(),
        os.environ.get("GPTSAPI_BASE_URL", "").strip() or DEFAULT_BASE,
        _env_float("GPTSAPI_TIMEOUT", DEFAULT_TIMEOUT),
        os.environ.get("GPTSAPI_USER_AGENT", "").strip() or DEFAULT_USER_AGENT,
    )


def try_create_gptsapi_llm() -> GptsApiLLM | None:
    """GptsApiLLM from env/.env, or None (with a warning) if not configured."""
    try:
        client = create_client_from_env()
    except ValueError as exc:
        log.warning("GPTsAPI disabled: %s", exc)
        return None
    return GptsApiLLM(
        client,
        model=os.environ.get("GPTSAPI_MODEL", "").strip() or DEFAULT_MODEL,
        max_tokens=int(_env_float("GPTSAPI_MAX_TOKENS", DEFAULT_MAX_TOKENS)),
    )
