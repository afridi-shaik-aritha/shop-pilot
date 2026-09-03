from app.config import Settings


def test_llm_defaults_disabled():
    s = Settings()
    assert s.llm_provider == "none"
    assert s.llm_base_url == ""
    assert s.llm_api_key == ""
    assert s.llm_model == ""
    assert s.db_path == "data/shop.db"
    assert s.has_llm() is False


def test_llm_env_mapping(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "anthropic/claude-3.5-sonnet")
    monkeypatch.setenv("ASA_DB_PATH", "/tmp/t.db")
    s = Settings.from_env()
    assert s.llm_provider == "openrouter"
    assert s.llm_base_url == "https://openrouter.ai/api/v1"
    assert s.llm_model == "anthropic/claude-3.5-sonnet"
    assert s.db_path == "/tmp/t.db"
    assert s.has_llm() is True


def test_llm_partial_config_not_ready(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nim")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert Settings.from_env().has_llm() is False
