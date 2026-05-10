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
    _ensure_watch_digest_control_columns(engine)
    _ensure_watch_listing_columns(engine)


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
            connection.execute(
                text(f"ALTER TABLE watches ADD COLUMN {column_name} VARCHAR(32)")
            )


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
                connection.execute(
                    text(f"ALTER TABLE watches ADD COLUMN {column_name} {column_definition}")
                )


def _ensure_watch_listing_columns(engine: Engine) -> None:
    """Add watch-listing action metadata for existing prototype databases."""

    inspector = inspect(engine)
    if "watch_listings" not in inspector.get_table_names():
        return
    column_names = {
        column["name"] for column in inspector.get_columns("watch_listings")
    }
    if "starred_message_id" in column_names:
        return
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE watch_listings ADD COLUMN starred_message_id VARCHAR(32)")
        )
