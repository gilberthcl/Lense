"""Central configuration, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    postgres_user: str = "lens"
    postgres_password: str = "lens_dev_change_me"
    postgres_db: str = "lens"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Backend
    secret_key: str = "dev-secret-change-me"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    max_upload_bytes: int = 20 * 1024 * 1024  # 20 MB — methodology hard cap

    # Ollama (host-local, multi-agent)
    ollama_base_url: str = "http://localhost:11434"
    ollama_analyst_model: str = "gemma3:27b"
    ollama_reviewer_model: str = "gpt-oss:20b"
    ollama_qa_model: str = "gpt-oss:20b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout: int = 600

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
