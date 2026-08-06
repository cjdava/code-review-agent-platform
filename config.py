from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    openai_api_key: SecretStr
    github_token: SecretStr
    openai_model: str = "gpt-4.1-mini"
    log_level: str = "INFO"
    request_timeout: int = 30


settings = Settings()
