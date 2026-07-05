import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MinutesAPP"
    app_version: str = "1.0.0"
    debug: bool = False

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/minutesdb"

    ollama_host: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_llm_model: str = "gemma3:4b"
    ollama_temperature: float = 0.2
    ollama_num_ctx: int = 1024

    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    allowed_extensions: tuple[str, ...] = (".pdf", ".docx", ".txt", ".md")
    cors_origins: str = ""

    @property
    def llm_options(self) -> dict:
        return {"temperature": self.ollama_temperature, "num_ctx": self.ollama_num_ctx}

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
