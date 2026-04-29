"""Database setup."""

from sqlalchemy import Engine, create_engine
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
