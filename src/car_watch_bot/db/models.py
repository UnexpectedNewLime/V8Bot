"""SQLAlchemy models for the local prototype."""

from datetime import datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class User(Base):
    """Discord user known to the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_user_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    watches: Mapped[list["Watch"]] = relationship(back_populates="user")


class Watch(Base):
    """A user's saved car search."""

    __tablename__ = "watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    guild_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    query: Mapped[str] = mapped_column(String(240))
    included_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_currency: Mapped[str] = mapped_column(String(3), default="AUD")
    distance_unit: Mapped[str] = mapped_column(String(2), default="km")
    notification_time: Mapped[time] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(64), default="Australia/Sydney")
    criteria_version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="watches")
    watch_sources: Mapped[list["WatchSource"]] = relationship(back_populates="watch")
    watch_listings: Mapped[list["WatchListing"]] = relationship(back_populates="watch")


class Source(Base):
    """A listing source."""

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("owner_user_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40), default="mock")
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    watch_sources: Mapped[list["WatchSource"]] = relationship(back_populates="source")
    listings: Mapped[list["Listing"]] = relationship(back_populates="source")


class WatchSource(Base):
    """Enabled source for a watch."""

    __tablename__ = "watch_sources"
    __table_args__ = (UniqueConstraint("watch_id", "source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watches.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    watch: Mapped[Watch] = relationship(back_populates="watch_sources")
    source: Mapped[Source] = relationship(back_populates="watch_sources")


class Listing(Base):
    """A normalized listing from a source."""

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_id", "url"),
        UniqueConstraint("source_id", "external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    converted_price_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    converted_price_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    mileage_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mileage_unit: Mapped[str | None] = mapped_column(String(2), nullable=True)
    converted_mileage_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    converted_mileage_unit: Mapped[str | None] = mapped_column(String(2), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(240), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    source: Mapped[Source] = relationship(back_populates="listings")
    watch_listings: Mapped[list["WatchListing"]] = relationship(back_populates="listing")


class WatchListing(Base):
    """A listing matched to a watch."""

    __tablename__ = "watch_listings"
    __table_args__ = (UniqueConstraint("watch_id", "listing_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watches.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    matched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    watch_criteria_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="pending_digest", index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    watch: Mapped[Watch] = relationship(back_populates="watch_listings")
    listing: Mapped[Listing] = relationship(back_populates="watch_listings")


class ScrapeAttempt(Base):
    """One scheduled scrape attempt."""

    __tablename__ = "scrape_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watches.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    adapter_kind: Mapped[str] = mapped_column(String(40))
    listings_seen: Mapped[int] = mapped_column(Integer, default=0)
    listings_matched: Mapped[int] = mapped_column(Integer, default=0)
    listings_created: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceTestAttempt(Base):
    """One user-triggered source test attempt."""

    __tablename__ = "source_test_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    detected_links: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
