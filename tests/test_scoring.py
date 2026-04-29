"""Tests for deterministic keyword scoring."""

from decimal import Decimal

from car_watch_bot.core.models import ListingCandidate
from car_watch_bot.core.scoring import keyword_match_score, score_listing


def test_keyword_match_score_counts_included_keywords() -> None:
    score = keyword_match_score(
        "Toyota Supra manual turbo",
        included_keywords=["supra", "manual", "automatic"],
    )

    assert score == 2


def test_keyword_match_score_returns_zero_for_excluded_keyword() -> None:
    score = keyword_match_score(
        "Toyota Supra automatic",
        included_keywords=["supra"],
        excluded_keywords=["automatic"],
    )

    assert score == 0


def test_c5_corvette_manual_hud_targa_positive_match() -> None:
    listing = ListingCandidate(
        title="2002 Chevrolet Corvette C5 manual HUD targa",
        url="https://example.test/c5",
        price_amount=Decimal("22000.00"),
        price_currency="USD",
        mileage_value=72000,
        mileage_unit="mi",
    )

    result = score_listing(
        listing,
        car_query="C5 Corvette",
        keywords=["manual", "HUD", "targa"],
        excluded_keywords=["automatic", "convertible"],
    )

    assert result.is_match is True
    assert result.score > 0
    assert "keyword matched: manual" in result.reasons


def test_automatic_convertible_is_rejected() -> None:
    listing = ListingCandidate(
        title="2001 Corvette C5 automatic convertible",
        url="https://example.test/c5-auto",
    )

    result = score_listing(
        listing,
        car_query="C5 Corvette",
        keywords=["manual", "HUD", "targa"],
        excluded_keywords=["automatic", "convertible"],
    )

    assert result.is_match is False
    assert result.score < 0


def test_scoring_handles_missing_price_and_mileage() -> None:
    listing = ListingCandidate(title="C5 Corvette manual", url="https://example.test/c5")

    result = score_listing(
        listing,
        car_query="C5 Corvette",
        keywords=["manual"],
        excluded_keywords=[],
    )

    assert result.is_match is True
    assert "price missing" in result.reasons
    assert "mileage missing" in result.reasons
