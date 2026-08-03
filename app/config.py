from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    KAI_OWNER_NAME: str = ""
    KAI_TZ: str = "Asia/Kolkata"
    KAI_MODEL: str = "qwen3:8b"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434/v1"
    OLLAMA_KEEP_ALIVE: str = "30m"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    DATABASE_URL: str = "sqlite:////data/kai.db"
    NTFY_URL: str = "https://ntfy.sh"
    NTFY_TOPIC: str = ""
    API_TOKEN: str = ""
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
