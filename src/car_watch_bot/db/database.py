"""Database setup."""

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.db.models import Base


def create_database_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL."""

    return create_engine(database_url, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a SQLAlchemy session factory."""

    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_database(engine: Engine) -> None:
    """Create database tables for the local prototype."""

    Base.metadata.create_all(engine)
    _ensure_watch_thread_columns(engine)


def _ensure_watch_thread_columns(engine: Engine) -> None:
    """Add watch thread persistence for existing prototype databases."""

    inspector = inspect(engine)
    if "watches" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("watches")}
    missing_columns = [
        column_name
        for column_name in ["thread_id", "starred_thread_id"]
        if column_name not in column_names
    ]
    if not missing_columns:
        return
    with engine.begin() as connection:
        for column_name in missing_columns:
            connection.execute(text(f"ALTER TABLE watches ADD COLUMN {column_name} VARCHAR(32)"))
