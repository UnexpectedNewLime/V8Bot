"""Pure conversion helpers for prices and mileage."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping


def convert_price(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    rates_to_base: Mapping[str, Decimal],
) -> Decimal:
    """Convert a price using rates expressed against the same base currency."""

    source_currency = from_currency.upper()
    target_currency = to_currency.upper()
    if source_currency == target_currency:
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    source_rate = rates_to_base[source_currency]
    target_rate = rates_to_base[target_currency]
    converted_amount = amount / source_rate * target_rate
    return converted_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def convert_usd_to_aud(amount: Decimal | None, usd_to_aud_rate: Decimal) -> Decimal | None:
    """Convert a USD amount to AUD using a configured static rate."""

    if amount is None:
        return None
    converted_amount = amount * usd_to_aud_rate
    return converted_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def convert_mileage(value: int, from_unit: str, to_unit: str) -> int:
    """Convert mileage between kilometres and miles."""

    source_unit = from_unit.lower()
    target_unit = to_unit.lower()
    if source_unit == target_unit:
        return value
    if source_unit == "mi" and target_unit == "km":
        return round(value * 1.609344)
    if source_unit == "km" and target_unit == "mi":
        return round(value / 1.609344)
    raise ValueError(f"Unsupported mileage conversion: {from_unit} to {to_unit}")


def miles_to_kilometres(value: int | None) -> int | None:
    """Convert miles to kilometres, preserving missing values."""

    if value is None:
        return None
    return convert_mileage(value, from_unit="mi", to_unit="km")
