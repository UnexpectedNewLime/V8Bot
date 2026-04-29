"""Tests for pure conversion helpers."""

from decimal import Decimal

from car_watch_bot.core.conversions import (
    convert_mileage,
    convert_price,
    convert_usd_to_aud,
    miles_to_kilometres,
)


def test_convert_price_between_currencies() -> None:
    rates_to_aud = {
        "AUD": Decimal("1.0"),
        "USD": Decimal("0.65"),
    }

    converted_price = convert_price(
        Decimal("100.00"),
        from_currency="AUD",
        to_currency="USD",
        rates_to_base=rates_to_aud,
    )

    assert converted_price == Decimal("65.00")


def test_convert_mileage_defaults_to_kilometres() -> None:
    converted_mileage = convert_mileage(100, from_unit="mi", to_unit="km")

    assert converted_mileage == 161


def test_convert_usd_to_aud_with_static_rate() -> None:
    converted_price = convert_usd_to_aud(Decimal("22000.00"), Decimal("1.50"))

    assert converted_price == Decimal("33000.00")


def test_miles_to_kilometres_handles_missing_value() -> None:
    assert miles_to_kilometres(None) is None
