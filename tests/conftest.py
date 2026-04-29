"""Shared test fixtures."""

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from car_watch_bot.db.database import create_database_engine, create_session_factory, init_database


@pytest.fixture
def db_session_factory() -> sessionmaker[Session]:
    """Create an isolated in-memory SQLite session factory."""

    engine = create_database_engine("sqlite:///:memory:")
    init_database(engine)
    return create_session_factory(engine)


@pytest.fixture
def db_session(db_session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Create an isolated in-memory SQLite session."""

    with db_session_factory() as session:
        yield session
