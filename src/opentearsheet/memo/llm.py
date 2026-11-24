"""Optional narrative engines. Local-first by design.

* ``none`` (default): deterministic template, no model at all.
* ``ollama``: a model running on your machine (https://ollama.com).
* ``openai_compatible``: any server speaking the OpenAI chat API. Defaults to LM Studio
  on localhost; llama.cpp and vLLM work too.

Endpoints that are not on this machine are refused unless ``ALLOW_REMOTE_LLM=true``.
Requests to local endpoints bypass any configured HTTP proxy so they never leave the box.
Only public filing facts and the entity name are sent; nothing else.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Optional
from urllib.parse import urlparse

from ..config import ConfigError, Settings, is_local_url


class LLMError(RuntimeError):
    pass


def post_json(url: str, payload: dict, headers: Optional[dict] = None, timeout: float = 180.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    handlers = [urllib.request.ProxyHandler({})] if is_local_url(url) else []
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError(f"HTTP {exc.code} from {url}: {exc.read()[:300]!r}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise LLMError(f"could not reach {url}: {exc}") from exc


PostFn = Callable[[str, dict, Optional[dict], float], dict]


class OllamaLLM:
    def __init__(self, base_url: str, model: str, timeout: float = 180.0, post: PostFn = post_json) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.is_local = is_local_url(self.base_url)
        self._post = post

    @property
    def label(self) -> str:
        return f"Ollama · {self.model}"

    def complete(self, messages: list[dict]) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False, "options": {"temperature": 0.1}}
        resp = self._post(f"{self.base_url}/api/chat", payload, None, self.timeout)
        try:
            return resp["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError("unexpected response shape from Ollama") from exc


class OpenAICompatibleLLM:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 180.0, post: PostFn = post_json) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self.timeout = timeout
        self.is_local = is_local_url(self.base_url)
        self._post = post

    @property
    def label(self) -> str:
        return f"{self.model} @ {urlparse(self.base_url).netloc}"

    def complete(self, messages: list[dict]) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        payload = {"model": self.model, "messages": messages, "temperature": 0.1, "stream": False}
        resp = self._post(f"{self.base_url}/chat/completions", payload, headers, self.timeout)
        try:
            return resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("unexpected response shape from OpenAI-compatible server") from exc


def make_llm(settings: Settings):
    """Build the configured LLM, or return None for template mode."""
    provider = (settings.llm_provider or "none").strip().lower()
    if provider in ("", "none", "off", "template"):
        return None
    if provider == "ollama":
        base = settings.ollama_base_url
    elif provider in ("openai_compatible", "openai-compatible", "openai"):
        base = settings.openai_base_url
    else:
        raise ConfigError(f"Unknown LLM_PROVIDER '{provider}'. Use none, ollama or openai_compatible.")

    if not is_local_url(base) and not settings.allow_remote_llm:
        raise ConfigError(
            f"LLM endpoint {base} is not on this machine, so filing facts would leave your computer. "
            "Use a local model, or set ALLOW_REMOTE_LLM=true if you accept that (check the provider's data-retention terms)."
        )
    if provider == "ollama":
        return OllamaLLM(base, settings.ollama_model, settings.llm_timeout)
    return OpenAICompatibleLLM(base, settings.openai_model, settings.openai_api_key, settings.llm_timeout)
