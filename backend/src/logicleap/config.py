from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOGICLEAP_")

    database_url: str = "postgresql+psycopg://logicleap:logicleap@postgres:5432/logicleap"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()

