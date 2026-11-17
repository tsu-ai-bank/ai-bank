import os
from functools import lru_cache

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    database_url: str | None = None
    redis_url: str | None = None
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: AnyHttpUrl = AnyHttpUrl("https://api.deepseek.com")
    deepseek_model: str = Field(default="deepseek-flash", min_length=1)
    deepseek_timeout_seconds: float = Field(default=30.0, gt=0)
    deepseek_max_retries: int = Field(default=3, ge=0, le=10)
    deepseek_requests_per_minute: int = Field(default=30, gt=0)
    deepseek_retry_base_seconds: float = Field(default=1.0, gt=0)
    secret_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    values = {
        name: os.environ[name.upper()]
        for name in Settings.model_fields
        if name.upper() in os.environ
    }
    return Settings.model_validate(values)
