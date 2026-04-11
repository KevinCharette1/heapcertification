from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"

    # LinkedIn (required for `python main.py` chat; optional for `python main.py reports`)
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8888/callback"

    # ClickUp (required for `python main.py reports`)
    clickup_api_token: str = ""
    clickup_workspace_id: str = ""   # Team ID — visible in your ClickUp workspace URL

    # Google Docs service account (required for `python main.py reports`)
    google_sa_key_file: str = "google_sa_key.json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
