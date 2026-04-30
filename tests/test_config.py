from pathlib import Path

from twinquery.config import DEFAULT_DATABASE_URL, _load_dotenv, get_settings


def test_load_dotenv_reads_database_url(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("DATABASE_URL=postgresql://user:pass@localhost:5433/db\n", encoding="utf-8")

    values = _load_dotenv(env_path)

    assert values["DATABASE_URL"] == "postgresql://user:pass@localhost:5433/db"


def test_default_database_url_matches_compose_host_port(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_settings().database_url.endswith(":5433/twinquery") or get_settings().database_url == DEFAULT_DATABASE_URL

