from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://hr:change-me@localhost:5432/hr"
    app_admin_token: str = ""
    telegram_bot_token: str = ""
    telegram_user_id: int | None = None
    hh_access_token: str = ""
    hh_user_agent: str = ""
    hh_autonomy_enabled: bool = False
    hh_api_verified: bool = False
    hh_api_apply_unavailable: bool = False
    hh_daily_limit: int = 200
    browser_enabled: bool = True
    hh_browser_writes_verified: bool = False
    browser_state_path: str = "/app/browser_profile/storage_state.json"
    model_api_url: str = ""
    model_api_key: str = ""
    model_name: str = ""


settings = Settings()
