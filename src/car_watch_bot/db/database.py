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
    _ensure_watch_thread_id_column(engine)
    _ensure_watch_digest_control_columns(engine)


def _ensure_watch_thread_id_column(engine: Engine) -> None:
    """Add watch thread persistence for existing prototype databases."""

    inspector = inspect(engine)
    if "watches" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("watches")}
    if "thread_id" in column_names:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE watches ADD COLUMN thread_id VARCHAR(32)"))


def _ensure_watch_digest_control_columns(engine: Engine) -> None:
    """Add watch digest controls for existing prototype databases."""

    inspector = inspect(engine)
    if "watches" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("watches")}
    columns = {
        "digest_no_update_enabled": "BOOLEAN NOT NULL DEFAULT 1",
        "digest_max_listings": "INTEGER",
        "digest_summary_only": "BOOLEAN NOT NULL DEFAULT 0",
        "digest_immediate_alerts": "BOOLEAN NOT NULL DEFAULT 0",
        "digest_quiet_hours_start": "TIME",
        "digest_quiet_hours_end": "TIME",
        "digest_frequency_minutes": "INTEGER NOT NULL DEFAULT 1440",
    }
    with engine.begin() as connection:
        for column_name, column_definition in columns.items():
            if column_name not in column_names:
                statement = (
                    f"ALTER TABLE watches ADD COLUMN {column_name} {column_definition}"
                )
                connection.execute(
                    text(statement)
                )
