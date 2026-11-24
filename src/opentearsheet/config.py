"""Runtime configuration.

Everything comes from environment variables or a local, git-ignored ``.env`` file.
Nothing secret is ever hardcoded; see ``.env.example`` for every supported key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

UA_HELP = (
    "Set SEC_USER_AGENT to your name and a real contact email, e.g. "
    "'Jane Doe jane@yourfirm.com'. The SEC asks every user of its free APIs to "
    "identify themselves this way: https://www.sec.gov/os/accessing-edgar-data"
)


class ConfigError(ValueError):
    """Raised when configuration is missing or unsafe."""


def load_dotenv(path: str | os.PathLike = ".env", override: bool = False) -> bool:
    """Minimal ``.env`` loader (no third-party dependency). Returns True if a file was read."""
    p = Path(path)
    if not p.is_file():
        return False
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        if key and (override or key not in os.environ):
            os.environ[key] = value
    return True


def is_local_url(url: str) -> bool:
    """True when ``url`` points at this machine (so data never leaves it)."""
    host = (urlparse(url).hostname or "").lower()
    return host in LOCAL_HOSTS or host.endswith(".localhost")


def validate_user_agent(ua: Optional[str]) -> str:
    ua = (ua or "").strip()
    lowered = ua.lower()
    placeholder = lowered.startswith("your name") or "example.com" in lowered or "yourdomain" in lowered
    if not ua or "@" not in ua or " " not in ua or placeholder:
        raise ConfigError(UA_HELP)
    return ua


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    try:
        return float(env.get(key, default))
    except (TypeError, ValueError):
        return float(default)


@dataclass
class Settings:
    sec_user_agent: str = ""
    data_dir: Path = field(default_factory=lambda: Path.home() / ".opentearsheet")
    max_rps: float = 5.0
    cache_ttl_hours: float = 6.0
    llm_provider: str = "none"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    openai_base_url: str = "http://localhost:1234/v1"
    openai_model: str = "local-model"
    openai_api_key: str = field(default="", repr=False)
    allow_remote_llm: bool = False
    llm_timeout: float = 180.0

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        e = os.environ if env is None else env
        data_dir = e.get("OPENTEARSHEET_DATA_DIR") or str(Path.home() / ".opentearsheet")
        return cls(
            sec_user_agent=(e.get("SEC_USER_AGENT") or "").strip(),
            data_dir=Path(data_dir).expanduser(),
            # SEC fair-access policy: never more than 10 requests per second.
            max_rps=min(max(_float(e, "SEC_MAX_RPS", 5.0), 0.1), 10.0),
            cache_ttl_hours=max(_float(e, "CACHE_TTL_HOURS", 6.0), 0.0),
            llm_provider=(e.get("LLM_PROVIDER") or "none").strip().lower(),
            ollama_base_url=(e.get("OLLAMA_BASE_URL") or cls.ollama_base_url).rstrip("/"),
            ollama_model=e.get("OLLAMA_MODEL") or cls.ollama_model,
            openai_base_url=(e.get("OPENAI_COMPAT_BASE_URL") or cls.openai_base_url).rstrip("/"),
            openai_model=e.get("OPENAI_COMPAT_MODEL") or cls.openai_model,
            openai_api_key=e.get("OPENAI_COMPAT_API_KEY") or "",
            allow_remote_llm=_truthy(e.get("ALLOW_REMOTE_LLM")),
            llm_timeout=max(_float(e, "LLM_TIMEOUT_SECONDS", 180.0), 5.0),
        )

    @property
    def cache_path(self) -> Path:
        return self.data_dir / "cache.sqlite3"

    def require_user_agent(self) -> str:
        return validate_user_agent(self.sec_user_agent)
