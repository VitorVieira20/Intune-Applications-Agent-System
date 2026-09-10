from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://intune_user:changeme@postgres:5432/intune_agent"
    redis_url: str = "redis://redis:6379/0"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:14b"
    storage_downloads_dir: str = "/app/storage/downloads"
    storage_packages_dir: str = "/app/storage/packages"
    max_correction_loops: int = 4
    log_level: str = "INFO"


settings = Settings()
