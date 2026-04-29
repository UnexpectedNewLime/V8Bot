"""Tests for Discord embed builders."""

from car_watch_bot.bot.client import _build_digest_embeds
from car_watch_bot.core.models import DigestListing, DigestPayload


def test_digest_embeds_use_one_embed_per_listing() -> None:
    digest = DigestPayload(
        watch_name="C5 digest",
        watch_query="C5 Corvette",
        listing_count=2,
        listings=[
            DigestListing(
                listing_id=1,
                title="2001 Chevrolet Corvette",
                source_name="Cars.com",
                original_price="USD 17,900",
                converted_price="AUD 26,850",
                original_mileage="88,279 mi",
                converted_mileage="142,071 km",
                score_reasons=["query term matched: Corvette"],
                url="https://example.test/1",
            ),
            DigestListing(
                listing_id=2,
                title="2001 Chevrolet Corvette Z06",
                source_name="eBay",
                original_price="USD 25,995",
                converted_price="AUD 38,992",
                original_mileage="54,222 mi",
                converted_mileage="87,262 km",
                score_reasons=[],
                url="https://example.test/2",
            ),
        ],
    )

    embeds = _build_digest_embeds(digest)

    assert len(embeds) == 2
    assert embeds[0].title == "2001 Chevrolet Corvette"
    assert embeds[0].url == "https://example.test/1"
