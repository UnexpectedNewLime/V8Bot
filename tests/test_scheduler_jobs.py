"""Tests for scheduler setup."""

from car_watch_bot.config import Settings
from car_watch_bot.scheduler.jobs import create_scheduler


async def _noop_job() -> int:
    """No-op async job."""

    return 0


def test_create_scheduler_registers_scrape_and_digest_jobs() -> None:
    settings = Settings(
        DISCORD_BOT_TOKEN="",
        SCRAPE_INTERVAL_MINUTES=15,
        DIGEST_POLL_INTERVAL_MINUTES=1,
    )

    scheduler = create_scheduler(
        settings=settings,
        scrape_job=_noop_job,
        digest_job=_noop_job,
    )

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {"collect_listings", "send_due_digests"}
    assert jobs["collect_listings"].trigger.interval.total_seconds() == 900
    assert jobs["send_due_digests"].trigger.interval.total_seconds() == 60
