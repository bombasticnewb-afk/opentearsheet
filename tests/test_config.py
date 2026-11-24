import os

import pytest

from opentearsheet.config import ConfigError, Settings, is_local_url, load_dotenv, validate_user_agent
from opentearsheet.memo import make_llm


def test_load_dotenv_parses_quotes_comments_and_export(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        '# comment\nSEC_USER_AGENT="Jane Doe jane@firm.com"\nexport LLM_PROVIDER=ollama  # inline\nEMPTY=\n',
        encoding="utf-8",
    )
    for key in ("SEC_USER_AGENT", "LLM_PROVIDER", "EMPTY"):
        monkeypatch.delenv(key, raising=False)
    assert load_dotenv(env)
    assert os.environ["SEC_USER_AGENT"] == "Jane Doe jane@firm.com"
    assert os.environ["LLM_PROVIDER"] == "ollama"
    assert os.environ["EMPTY"] == ""


def test_load_dotenv_does_not_override_real_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=ollama\n", encoding="utf-8")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    load_dotenv(env)
    assert os.environ["LLM_PROVIDER"] == "none"


def test_missing_dotenv_is_fine(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") is False


@pytest.mark.parametrize("ua", ["", "jane", "jane@firm.com", "Your Name you@yourdomain.com", "Bob bob@example.com"])
def test_user_agent_rejected(ua):
    with pytest.raises(ConfigError):
        validate_user_agent(ua)


def test_user_agent_accepted():
    assert validate_user_agent("  Jane Doe jane@firm.com ") == "Jane Doe jane@firm.com"


@pytest.mark.parametrize("url,local", [
    ("http://localhost:11434", True),
    ("http://127.0.0.1:1234/v1", True),
    ("http://[::1]:8080", True),
    ("http://ollama.localhost", True),
    ("https://api.some-provider.com/v1", False),
    ("http://10.0.0.5:11434", False),
])
def test_is_local_url(url, local):
    assert is_local_url(url) is local


def test_rps_is_capped_at_sec_limit():
    assert Settings.from_env({"SEC_MAX_RPS": "50"}).max_rps == 10.0
    assert Settings.from_env({"SEC_MAX_RPS": "garbage"}).max_rps == 5.0


def test_api_key_hidden_from_repr():
    s = Settings.from_env({"OPENAI_COMPAT_API_KEY": "sk-secret"})
    assert "sk-secret" not in repr(s)


def test_default_is_template_mode():
    assert make_llm(Settings.from_env({})) is None


def test_local_ollama_allowed():
    llm = make_llm(Settings.from_env({"LLM_PROVIDER": "ollama"}))
    assert llm.is_local and "Ollama" in llm.label


def test_remote_llm_refused_without_opt_in():
    env = {"LLM_PROVIDER": "openai_compatible", "OPENAI_COMPAT_BASE_URL": "https://api.some-provider.com/v1"}
    with pytest.raises(ConfigError, match="ALLOW_REMOTE_LLM"):
        make_llm(Settings.from_env(env))
    llm = make_llm(Settings.from_env({**env, "ALLOW_REMOTE_LLM": "true"}))
    assert llm.is_local is False


def test_unknown_provider():
    with pytest.raises(ConfigError):
        make_llm(Settings.from_env({"LLM_PROVIDER": "magic"}))
