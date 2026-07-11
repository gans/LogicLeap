from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from logicleap.config import get_settings


def create_database_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def database_is_ready(engine: Engine) -> bool:
    with engine.connect() as connection:
        result: object = connection.execute(text("SELECT 1")).scalar_one()
        return result == 1
