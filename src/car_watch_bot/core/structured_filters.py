"""Structured watch filter helpers."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping

from car_watch_bot.core.models import ListingCandidate


FILTER_FIELD_NAMES = frozenset(
    {
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
)
ALL_CLEAR_FIELDS = {"all", "*"}
CLEAR_FIELD_GROUPS = {
    "price": {"price_min", "price_max"},
    "year": {"year_min", "year_max"},
    "location_radius": {"location", "radius"},
    "must_have": {"must_have_terms"},
    "body": {"body_style"},
}
_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
_DISTANCE_KEYS = (
    "distance",
    "distance_value",
    "distance_miles",
    "distance_mi",
    "distance_km",
    "distance_kilometres",
    "distance_kilometers",
)


class StructuredFilterValidationError(ValueError):
    """Raised when structured filter input is invalid."""


@dataclass(frozen=True)
class StructuredFilterResult:
    """Result of evaluating structured filters against a listing."""

    is_match: bool
    reasons: list[str]


@dataclass(frozen=True)
class WatchFilters:
    """Structured filters for one watch."""

    price_min: Decimal | None = None
    price_max: Decimal | None = None
    year_min: int | None = None
    year_max: int | None = None
    mileage_max: int | None = None
    transmission: str | None = None
    location: str | None = None
    radius: int | None = None
    body_style: str | None = None
    must_have_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate filter relationships."""

        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise StructuredFilterValidationError(
                "price_min must be less than price_max"
            )
        if self.year_min is not None and self.year_max is not None:
            if self.year_min > self.year_max:
                raise StructuredFilterValidationError(
                    "year_min must be less than year_max"
                )
        if self.radius is not None and not self.location:
            raise StructuredFilterValidationError("radius requires location")

    @classmethod
    def from_dict(cls, raw_filters: Mapping[str, Any] | None) -> "WatchFilters":
        """Build filters from persisted JSON."""

        raw = raw_filters or {}
        return cls(
            price_min=_parse_decimal(raw.get("price_min"), field_name="price_min"),
            price_max=_parse_decimal(raw.get("price_max"), field_name="price_max"),
            year_min=_parse_year(raw.get("year_min"), field_name="year_min"),
            year_max=_parse_year(raw.get("year_max"), field_name="year_max"),
            mileage_max=_parse_positive_int(
                raw.get("mileage_max"),
                field_name="mileage_max",
            ),
            transmission=_parse_optional_text(
                raw.get("transmission"),
                field_name="transmission",
                max_length=80,
            ),
            location=_parse_optional_text(
                raw.get("location"),
                field_name="location",
                max_length=120,
            ),
            radius=_parse_positive_int(raw.get("radius"), field_name="radius"),
            body_style=_parse_optional_text(
                raw.get("body_style"),
                field_name="body_style",
                max_length=80,
            ),
            must_have_terms=_parse_terms(raw.get("must_have_terms")),
        )

    @classmethod
    def from_inputs(
        cls,
        *,
        price_min: Decimal | int | str | None = None,
        price_max: Decimal | int | str | None = None,
        year_min: int | str | None = None,
        year_max: int | str | None = None,
        mileage_max: int | str | None = None,
        transmission: str | None = None,
        location: str | None = None,
        radius: int | str | None = None,
        body_style: str | None = None,
        must_have: str | list[str] | tuple[str, ...] | None = None,
    ) -> "WatchFilters":
        """Build filters from command or service inputs."""

        return cls(
            price_min=_parse_decimal(price_min, field_name="price_min"),
            price_max=_parse_decimal(price_max, field_name="price_max"),
            year_min=_parse_year(year_min, field_name="year_min"),
            year_max=_parse_year(year_max, field_name="year_max"),
            mileage_max=_parse_positive_int(mileage_max, field_name="mileage_max"),
            transmission=_parse_optional_text(
                transmission,
                field_name="transmission",
                max_length=80,
            ),
            location=_parse_optional_text(
                location,
                field_name="location",
                max_length=120,
            ),
            radius=_parse_positive_int(radius, field_name="radius"),
            body_style=_parse_optional_text(
                body_style,
                field_name="body_style",
                max_length=80,
            ),
            must_have_terms=_parse_terms(must_have),
        )

    def with_updates(
        self,
        *,
        clear_fields: set[str] | None = None,
        price_min: Decimal | int | str | None = None,
        price_max: Decimal | int | str | None = None,
        year_min: int | str | None = None,
        year_max: int | str | None = None,
        mileage_max: int | str | None = None,
        transmission: str | None = None,
        location: str | None = None,
        radius: int | str | None = None,
        body_style: str | None = None,
        must_have: str | list[str] | tuple[str, ...] | None = None,
    ) -> "WatchFilters":
        """Return filters with selected fields changed or cleared."""

        values: dict[str, Any] = self.to_dict()
        for field_name in clear_fields or set():
            values.pop(field_name, None)
        updates = {
            "price_min": price_min,
            "price_max": price_max,
            "year_min": year_min,
            "year_max": year_max,
            "mileage_max": mileage_max,
            "transmission": transmission,
            "location": location,
            "radius": radius,
            "body_style": body_style,
            "must_have_terms": must_have,
        }
        for field_name, value in updates.items():
            if value is not None:
                values[field_name] = value
        return WatchFilters.from_dict(values)

    def to_dict(self) -> dict[str, Any]:
        """Return a compact JSON-serializable representation."""

        payload: dict[str, Any] = {}
        if self.price_min is not None:
            payload["price_min"] = str(self.price_min)
        if self.price_max is not None:
            payload["price_max"] = str(self.price_max)
        if self.year_min is not None:
            payload["year_min"] = self.year_min
        if self.year_max is not None:
            payload["year_max"] = self.year_max
        if self.mileage_max is not None:
            payload["mileage_max"] = self.mileage_max
        if self.transmission is not None:
            payload["transmission"] = self.transmission
        if self.location is not None:
            payload["location"] = self.location
        if self.radius is not None:
            payload["radius"] = self.radius
        if self.body_style is not None:
            payload["body_style"] = self.body_style
        if self.must_have_terms:
            payload["must_have_terms"] = list(self.must_have_terms)
        return payload

    def is_empty(self) -> bool:
        """Return whether no structured filters are configured."""

        return not self.to_dict()

    def describe(
        self,
        *,
        preferred_currency: str,
        distance_unit: str,
    ) -> str:
        """Return a compact human-readable summary."""

        parts: list[str] = []
        if self.price_min is not None and self.price_max is not None:
            parts.append(
                f"price {preferred_currency} "
                f"{self.price_min:,.0f}-{self.price_max:,.0f}"
            )
        elif self.price_min is not None:
            parts.append(f"price >= {preferred_currency} {self.price_min:,.0f}")
        elif self.price_max is not None:
            parts.append(f"price <= {preferred_currency} {self.price_max:,.0f}")

        if self.year_min is not None and self.year_max is not None:
            parts.append(f"years {self.year_min}-{self.year_max}")
        elif self.year_min is not None:
            parts.append(f"year >= {self.year_min}")
        elif self.year_max is not None:
            parts.append(f"year <= {self.year_max}")

        if self.mileage_max is not None:
            parts.append(f"mileage <= {self.mileage_max:,} {distance_unit}")
        if self.transmission is not None:
            parts.append(f"transmission {self.transmission}")
        if self.body_style is not None:
            parts.append(f"body {self.body_style}")
        if self.location is not None:
            location_text = f"location {self.location}"
            if self.radius is not None:
                location_text += f" within {self.radius:,} {distance_unit}"
            parts.append(location_text)
        if self.must_have_terms:
            parts.append(f"must have {', '.join(self.must_have_terms)}")
        return "; ".join(parts) if parts else "none"

    def evaluate_listing(
        self,
        listing: ListingCandidate,
        *,
        converted_price_amount: Decimal | None,
        converted_mileage_value: int | None,
        distance_unit: str,
    ) -> StructuredFilterResult:
        """Evaluate whether a listing satisfies these filters."""

        if self.is_empty():
            return StructuredFilterResult(is_match=True, reasons=[])

        reasons: list[str] = []
        if self.price_min is not None or self.price_max is not None:
            if converted_price_amount is None:
                reasons.append("structured filter: price missing")
            elif self.price_min is not None and converted_price_amount < self.price_min:
                reasons.append("structured filter: price below minimum")
            elif self.price_max is not None and converted_price_amount > self.price_max:
                reasons.append("structured filter: price above maximum")

        if self.year_min is not None or self.year_max is not None:
            listing_year = listing_year_from_candidate(listing)
            if listing_year is None:
                reasons.append("structured filter: year missing")
            elif self.year_min is not None and listing_year < self.year_min:
                reasons.append("structured filter: year below minimum")
            elif self.year_max is not None and listing_year > self.year_max:
                reasons.append("structured filter: year above maximum")

        if self.mileage_max is not None:
            if converted_mileage_value is None:
                reasons.append("structured filter: mileage missing")
            elif converted_mileage_value > self.mileage_max:
                reasons.append("structured filter: mileage above maximum")

        searchable_text = _searchable_text(listing)
        if self.transmission is not None and not _text_matches_term(
            searchable_text,
            self.transmission,
            extra_terms=_transmission_aliases(self.transmission),
        ):
            reasons.append("structured filter: transmission did not match")

        if self.body_style is not None and not _text_matches_term(
            searchable_text,
            self.body_style,
        ):
            reasons.append("structured filter: body style did not match")

        if self.location is not None:
            location_text = _location_text(listing)
            if self.location.casefold() not in location_text.casefold():
                reasons.append("structured filter: location did not match")

        if self.radius is not None:
            distance_value = _candidate_distance(listing, distance_unit)
            if distance_value is not None and distance_value > self.radius:
                reasons.append("structured filter: outside radius")

        for term in self.must_have_terms:
            if term.casefold() not in searchable_text:
                reasons.append(f"structured filter: missing must-have term {term}")

        return StructuredFilterResult(is_match=not reasons, reasons=reasons)


def parse_clear_fields(raw_clear_fields: str | None) -> set[str]:
    """Parse a comma-separated clear field list."""

    if not raw_clear_fields:
        return set()
    raw_fields = [
        field.strip().casefold()
        for field in raw_clear_fields.split(",")
        if field.strip()
    ]
    if not raw_fields:
        return set()
    if set(raw_fields) & ALL_CLEAR_FIELDS:
        return set(FILTER_FIELD_NAMES)
    fields: set[str] = set()
    for field in raw_fields:
        if field in CLEAR_FIELD_GROUPS:
            fields.update(CLEAR_FIELD_GROUPS[field])
        else:
            fields.add(field)
    unknown_fields = fields - FILTER_FIELD_NAMES
    if unknown_fields:
        names = ", ".join(sorted(unknown_fields))
        raise StructuredFilterValidationError(f"unknown filter field to clear: {names}")
    return fields


def listing_year_from_candidate(listing: ListingCandidate) -> int | None:
    """Extract a likely model year from normalized candidate fields."""

    raw_payload = listing.raw_payload or {}
    for key in ("year", "model_year", "vehicle_year"):
        raw_year = raw_payload.get(key)
        parsed_year = _parse_year(raw_year, field_name=key, allow_empty=True)
        if parsed_year is not None:
            return parsed_year

    match = _YEAR_PATTERN.search(_searchable_text(listing))
    if match is None:
        return None
    return int(match.group(1))


def _parse_decimal(value: Any, *, field_name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise StructuredFilterValidationError(f"{field_name} must be a number") from exc
    if amount < 0:
        raise StructuredFilterValidationError(f"{field_name} must be zero or greater")
    return amount


def _parse_year(
    value: Any,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> int | None:
    if value is None or value == "":
        return None
    try:
        year = int(str(value).strip())
    except ValueError as exc:
        if allow_empty:
            return None
        raise StructuredFilterValidationError(f"{field_name} must be a year") from exc
    if year < 1886 or year > 2100:
        raise StructuredFilterValidationError(
            f"{field_name} must be between 1886 and 2100"
        )
    return year


def _parse_positive_int(value: Any, *, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed_value = int(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise StructuredFilterValidationError(
            f"{field_name} must be a whole number"
        ) from exc
    if parsed_value < 0:
        raise StructuredFilterValidationError(f"{field_name} must be zero or greater")
    return parsed_value


def _parse_optional_text(
    value: Any,
    *,
    field_name: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    parsed_value = str(value).strip()
    if not parsed_value:
        return None
    if len(parsed_value) > max_length:
        raise StructuredFilterValidationError(
            f"{field_name} must be {max_length} characters or fewer"
        )
    return parsed_value


def _parse_terms(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        raw_terms = value.split(",")
    elif isinstance(value, (list, tuple)):
        raw_terms = [str(term) for term in value]
    else:
        raw_terms = [str(value)]

    terms: list[str] = []
    seen_terms: set[str] = set()
    for raw_term in raw_terms:
        term = raw_term.strip()
        if not term:
            continue
        if len(term) > 80:
            raise StructuredFilterValidationError(
                "must_have terms must be 80 characters or fewer"
            )
        normalized_term = term.casefold()
        if normalized_term not in seen_terms:
            terms.append(term)
            seen_terms.add(normalized_term)
    return tuple(terms)


def _searchable_text(listing: ListingCandidate) -> str:
    raw_payload = listing.raw_payload or {}
    payload_texts = [
        str(value)
        for key, value in raw_payload.items()
        if key
        in {
            "raw_text",
            "body_style",
            "bodyStyle",
            "transmission",
            "sellerDescription",
            "sellerComments",
            "listing_source_name",
        }
        and value is not None
    ]
    parts = [
        listing.title,
        listing.description or "",
        listing.location_text or "",
        *payload_texts,
    ]
    return " ".join(part.casefold() for part in parts if part)


def _location_text(listing: ListingCandidate) -> str:
    raw_payload = listing.raw_payload or {}
    parts = [
        listing.location_text or "",
        str(raw_payload.get("location") or ""),
        str(raw_payload.get("location_text") or ""),
    ]
    return " ".join(part for part in parts if part)


def _text_matches_term(
    searchable_text: str,
    term: str,
    *,
    extra_terms: set[str] | None = None,
) -> bool:
    terms = {term.casefold(), *(extra_terms or set())}
    return any(
        candidate_term and candidate_term in searchable_text
        for candidate_term in terms
    )


def _transmission_aliases(transmission: str) -> set[str]:
    normalized = transmission.casefold()
    if normalized in {"manual", "man", "stick", "stick shift"}:
        return {"manual", "6-speed", "6 speed", "5-speed", "5 speed", "stick"}
    if normalized in {"automatic", "auto"}:
        return {"automatic", "auto transmission"}
    return set()


def _candidate_distance(listing: ListingCandidate, distance_unit: str) -> int | None:
    raw_payload = listing.raw_payload or {}
    for key in _DISTANCE_KEYS:
        if key not in raw_payload:
            continue
        parsed_distance = _parse_distance_value(raw_payload[key])
        if parsed_distance is None:
            continue
        source_unit = _distance_unit_for_key(key, raw_payload)
        return _convert_distance(parsed_distance, source_unit, distance_unit)
    return None


def _parse_distance_value(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value).replace(",", ""))
    if match is None:
        return None
    return int(match.group(0))


def _distance_unit_for_key(key: str, raw_payload: Mapping[str, Any]) -> str:
    if (
        key.endswith("_km")
        or key.endswith("_kilometres")
        or key.endswith("_kilometers")
    ):
        return "km"
    if key.endswith("_mi") or key.endswith("_miles"):
        return "mi"
    unit = str(raw_payload.get("distance_unit") or "").casefold()
    if unit in {"km", "kilometres", "kilometers"}:
        return "km"
    return "mi"


def _convert_distance(value: int, source_unit: str, target_unit: str) -> int:
    if source_unit == target_unit:
        return value
    if source_unit == "mi" and target_unit == "km":
        return round(value * 1.609344)
    if source_unit == "km" and target_unit == "mi":
        return round(value / 1.609344)
    return value
