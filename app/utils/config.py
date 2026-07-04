"""Central application configuration, loaded once from the environment/.env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"

    # Search
    tavily_api_key: str = ""

    # Behaviour
    max_search_results_per_source: int = 5
    max_pages_to_scrape: int = 8
    search_cache_ttl_seconds: int = 3600
    relevance_score_threshold: float = 0.45
    http_timeout_seconds: int = 20
    log_level: str = "INFO"

    # Storage
    database_path: str = "data/db/research_agent.sqlite3"
    reports_dir: str = "data/reports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
