import os
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_url: str | None = None
    redis_url: str | None = None
    deepseek_api_key: SecretStr | None = None
    secret_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    values = {
        name: os.environ[name.upper()]
        for name in Settings.model_fields
        if name.upper() in os.environ
    }
    return Settings.model_validate(values)
