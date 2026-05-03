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
                location="Lake Havasu City, AZ",
                first_seen="2026-04-28 08:10 AEST",
                last_seen="2026-04-29 11:20 AEST",
                seller_info="Dealer: Desert Cars",
                image_url="https://example.test/1.jpg",
                price_change="Down USD 1,000 from USD 18,900 to USD 17,900",
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
    fields = {field.name: field.value for field in embeds[0].fields}
    assert fields["Location"] == "Lake Havasu City, AZ"
    assert fields["First seen"] == "2026-04-28 08:10 AEST"
    assert fields["Last seen"] == "2026-04-29 11:20 AEST"
    assert fields["Seller info"] == "Dealer: Desert Cars"
    assert fields["Price change"] == "Down USD 1,000 from USD 18,900 to USD 17,900"
    assert embeds[0].to_dict()["thumbnail"]["url"] == "https://example.test/1.jpg"
    second_fields = {field.name: field.value for field in embeds[1].fields}
    assert "Location" not in second_fields
    assert "Price change" not in second_fields
