"""Pure builders for guided source presets."""

from dataclasses import dataclass
from urllib.parse import urlencode


AUTOTEMPEST_RESULTS_URL = "https://www.autotempest.com/results"
MIN_AUTOTEMPEST_YEAR = 1886
MAX_AUTOTEMPEST_YEAR = 2100
SOURCE_NAME_LIMIT = 120


class SourcePresetValidationError(ValueError):
    """Raised when guided source preset input is invalid."""


@dataclass(frozen=True)
class AutoTempestSearchCriteria:
    """Structured AutoTempest search fields."""

    make: str
    model: str
    year_min: int | None = None
    year_max: int | None = None
    transmission: str | None = None
    zip_postcode: str | None = None
    radius: int | None = None


@dataclass(frozen=True)
class _NormalizedAutoTempestCriteria:
    """Validated AutoTempest criteria normalized for builders."""

    make_display: str
    model_display: str
    make_param: str
    model_param: str
    year_min: int | None
    year_max: int | None
    transmission_label: str | None
    transmission_param: str | None
    zip_postcode: str | None
    radius: int | None


def build_autotempest_url(criteria: AutoTempestSearchCriteria) -> str:
    """Build a deterministic AutoTempest results URL."""

    normalized = _normalize_autotempest_criteria(criteria)
    params: list[tuple[str, str | int]] = [
        ("localization", "any"),
        ("make", normalized.make_param),
        ("model", normalized.model_param),
    ]
    if normalized.year_min is not None:
        params.append(("minyear", normalized.year_min))
    if normalized.year_max is not None:
        params.append(("maxyear", normalized.year_max))
    if normalized.transmission_param is not None:
        params.append(("transmission", normalized.transmission_param))
    if normalized.zip_postcode is not None:
        params.append(("zip", normalized.zip_postcode))
    if normalized.radius is not None:
        params.append(("radius", normalized.radius))
    return f"{AUTOTEMPEST_RESULTS_URL}?{urlencode(params)}"


def build_autotempest_watch_query(criteria: AutoTempestSearchCriteria) -> str:
    """Build a watch query label from AutoTempest criteria."""

    normalized = _normalize_autotempest_criteria(criteria)
    year_label = _year_label(normalized.year_min, normalized.year_max)
    parts = [
        part
        for part in [
            year_label,
            normalized.make_display,
            normalized.model_display,
        ]
        if part
    ]
    return " ".join(parts)


def build_autotempest_source_name(criteria: AutoTempestSearchCriteria) -> str:
    """Build a compact source name for a generated AutoTempest source."""

    normalized = _normalize_autotempest_criteria(criteria)
    year_label = _year_label(normalized.year_min, normalized.year_max)
    parts = [
        part
        for part in [
            "AutoTempest",
            normalized.make_display,
            normalized.model_display,
            year_label,
        ]
        if part
    ]
    return _truncate_text(" ".join(parts), SOURCE_NAME_LIMIT)


def build_autotempest_keywords(
    criteria: AutoTempestSearchCriteria,
    keywords: str | None,
) -> str:
    """Build watch keywords, using sensible defaults when omitted."""

    explicit_keywords = (keywords or "").strip()
    if explicit_keywords:
        return explicit_keywords

    normalized = _normalize_autotempest_criteria(criteria)
    default_keywords = [normalized.model_display]
    if normalized.transmission_label is not None:
        default_keywords.append(normalized.transmission_label)
    return ", ".join(_dedupe_casefold(default_keywords))


def _normalize_autotempest_criteria(
    criteria: AutoTempestSearchCriteria,
) -> _NormalizedAutoTempestCriteria:
    """Normalize and validate AutoTempest criteria."""

    make_display = _required_text(criteria.make, "make")
    model_display = _required_text(criteria.model, "model")
    year_min = _normalize_year(criteria.year_min, "year_min")
    year_max = _normalize_year(criteria.year_max, "year_max")
    if year_min is not None and year_max is not None and year_min > year_max:
        raise SourcePresetValidationError(
            "year_min must be before or equal to year_max"
        )
    zip_postcode = _optional_text(criteria.zip_postcode)
    radius = _normalize_radius(criteria.radius)
    if radius is not None and zip_postcode is None:
        raise SourcePresetValidationError("radius requires zip_postcode")
    transmission_label, transmission_param = _normalize_transmission(
        criteria.transmission
    )
    return _NormalizedAutoTempestCriteria(
        make_display=make_display,
        model_display=model_display,
        make_param=make_display.casefold(),
        model_param=model_display.casefold(),
        year_min=year_min,
        year_max=year_max,
        transmission_label=transmission_label,
        transmission_param=transmission_param,
        zip_postcode=zip_postcode,
        radius=radius,
    )


def _required_text(value: str, field_name: str) -> str:
    """Normalize required text."""

    normalized = _normalize_spaces(value)
    if not normalized:
        raise SourcePresetValidationError(f"{field_name} is required")
    return normalized


def _optional_text(value: str | None) -> str | None:
    """Normalize optional text."""

    normalized = _normalize_spaces(value or "")
    return normalized or None


def _normalize_spaces(value: str) -> str:
    """Collapse repeated whitespace."""

    return " ".join(value.strip().split())


def _normalize_year(value: int | None, field_name: str) -> int | None:
    """Validate an optional AutoTempest year."""

    if value is None:
        return None
    if value < MIN_AUTOTEMPEST_YEAR or value > MAX_AUTOTEMPEST_YEAR:
        raise SourcePresetValidationError(
            f"{field_name} must be between {MIN_AUTOTEMPEST_YEAR} and "
            f"{MAX_AUTOTEMPEST_YEAR}"
        )
    return value


def _normalize_radius(value: int | None) -> int | None:
    """Validate an optional AutoTempest search radius."""

    if value is None:
        return None
    if value <= 0:
        raise SourcePresetValidationError("radius must be greater than zero")
    return value


def _normalize_transmission(value: str | None) -> tuple[str | None, str | None]:
    """Normalize an optional transmission choice."""

    normalized = _normalize_spaces(value or "").casefold()
    if normalized in {"", "any"}:
        return None, None
    if normalized in {"manual", "man"}:
        return "manual", "man"
    if normalized in {"automatic", "auto"}:
        return "automatic", "auto"
    raise SourcePresetValidationError(
        "transmission must be any, manual, or automatic"
    )


def _year_label(year_min: int | None, year_max: int | None) -> str | None:
    """Build a compact year label for display/query text."""

    if year_min is None or year_max is None:
        return None
    if year_min == year_max:
        return str(year_min)
    return f"{year_min}-{year_max}"


def _dedupe_casefold(values: list[str]) -> list[str]:
    """Return values without case-insensitive duplicates."""

    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _truncate_text(value: str, max_length: int) -> str:
    """Truncate text without leaving trailing whitespace."""

    if len(value) <= max_length:
        return value
    return value[:max_length].rstrip()
