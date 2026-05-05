"""Tests for structured watch filter helpers."""

from decimal import Decimal

import pytest

from car_watch_bot.core.models import ListingCandidate
from car_watch_bot.core.structured_filters import (
    StructuredFilterValidationError,
    WatchFilters,
    listing_year_from_candidate,
    parse_clear_fields,
)


def test_structured_filters_accept_listing_that_satisfies_all_dimensions() -> None:
    filters = WatchFilters.from_inputs(
        price_min="20000",
        price_max="35000",
        year_min=2001,
        year_max=2004,
        mileage_max=120000,
        transmission="manual",
        location="Austin",
        radius=100,
        body_style="coupe",
        must_have="HUD, targa",
    )
    listing = ListingCandidate(
        title="2002 Chevrolet Corvette C5 manual HUD targa coupe",
        url="https://example.test/c5",
        description="Six-speed manual coupe with targa roof.",
        location_text="Austin, TX",
        raw_payload={"distance_miles": 42},
    )

    result = filters.evaluate_listing(
        listing,
        converted_price_amount=Decimal("31000"),
        converted_mileage_value=90000,
        distance_unit="mi",
    )

    assert result.is_match is True
    assert result.reasons == []


def test_structured_filters_reject_missing_and_out_of_range_values() -> None:
    filters = WatchFilters.from_inputs(
        price_max="30000",
        year_min=2001,
        mileage_max=100000,
        must_have="HUD",
    )
    listing = ListingCandidate(
        title="1999 Chevrolet Corvette C5 manual",
        url="https://example.test/c5",
        description="Manual coupe.",
    )

    result = filters.evaluate_listing(
        listing,
        converted_price_amount=None,
        converted_mileage_value=120000,
        distance_unit="km",
    )

    assert result.is_match is False
    assert "structured filter: price missing" in result.reasons
    assert "structured filter: year below minimum" in result.reasons
    assert "structured filter: mileage above maximum" in result.reasons
    assert "structured filter: missing must-have term HUD" in result.reasons


def test_structured_filters_enforce_radius_when_distance_metadata_exists() -> None:
    filters = WatchFilters.from_inputs(location="Sydney", radius=50)
    listing = ListingCandidate(
        title="2002 Corvette manual",
        url="https://example.test/c5",
        location_text="Sydney NSW",
        raw_payload={"distance_km": "75 km"},
    )

    result = filters.evaluate_listing(
        listing,
        converted_price_amount=None,
        converted_mileage_value=None,
        distance_unit="km",
    )

    assert result.is_match is False
    assert result.reasons == ["structured filter: outside radius"]


def test_structured_filters_allow_location_match_without_radius_metadata() -> None:
    filters = WatchFilters.from_inputs(location="Sydney", radius=50)
    listing = ListingCandidate(
        title="2002 Corvette manual",
        url="https://example.test/c5",
        location_text="Sydney NSW",
    )

    result = filters.evaluate_listing(
        listing,
        converted_price_amount=None,
        converted_mileage_value=None,
        distance_unit="km",
    )

    assert result.is_match is True


def test_structured_filter_validation_rejects_bad_ranges() -> None:
    with pytest.raises(StructuredFilterValidationError, match="price_min"):
        WatchFilters.from_inputs(price_min="40000", price_max="30000")

    with pytest.raises(
        StructuredFilterValidationError,
        match="radius requires location",
    ):
        WatchFilters.from_inputs(radius=50)


def test_structured_filters_round_trip_compact_json() -> None:
    filters = WatchFilters.from_inputs(
        price_min="20000",
        year_max=2004,
        transmission="manual",
        must_have="HUD, HUD, targa",
    )

    restored = WatchFilters.from_dict(filters.to_dict())

    assert restored == filters
    assert restored.must_have_terms == ("HUD", "targa")


def test_listing_year_prefers_raw_payload_before_text() -> None:
    listing = ListingCandidate(
        title="2002 Corvette manual",
        url="https://example.test/c5",
        raw_payload={"model_year": 2004},
    )

    assert listing_year_from_candidate(listing) == 2004


def test_parse_clear_fields_supports_named_fields_and_all() -> None:
    assert parse_clear_fields("price_min, body_style") == {"price_min", "body_style"}
    assert parse_clear_fields("price, year, must_have, body") == {
        "price_min",
        "price_max",
        "year_min",
        "year_max",
        "must_have_terms",
        "body_style",
    }
    assert parse_clear_fields("all") == {
        "price_min",
        "price_max",
        "year_min",
        "year_max",
        "mileage_max",
        "transmission",
        "location",
        "radius",
        "body_style",
        "must_have_terms",
    }

    with pytest.raises(StructuredFilterValidationError, match="unknown"):
        parse_clear_fields("colour")
