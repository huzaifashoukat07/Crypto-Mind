from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    binance_api_key: str = ""
    binance_api_secret: str = ""
    allow_live_trading: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    host: str = "0.0.0.0"
    port: int = 8000

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # If set, every API request (except /api/health) and the WebSocket must
    # present this token, since the API has no other access control. Leave
    # blank only for strictly localhost-only use -- required for anything
    # reachable from the internet (see README: Deploying for 24/7 uptime).
    api_auth_token: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
