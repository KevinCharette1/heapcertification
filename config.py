from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"

    linkedin_client_id: str
    linkedin_client_secret: str
    linkedin_redirect_uri: str = "http://localhost:8888/callback"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
