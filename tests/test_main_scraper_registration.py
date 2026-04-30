"""Tests for runtime scraper registration."""

from types import SimpleNamespace

from car_watch_bot.main import _scraper_adapters


def test_runtime_scraper_adapters_include_static_sources() -> None:
    settings = SimpleNamespace(
        scraper_user_agent="V8Bot test",
        scraper_timeout_seconds=10.0,
        scraper_min_interval_seconds=0.0,
    )

    adapters = _scraper_adapters(settings)

    assert set(adapters) >= {
        "autotempest",
        "cars_on_line",
        "corvette_magazine",
        "mock",
        "vettefinders",
    }
