"""Deterministic listing scoring helpers."""

from car_watch_bot.core.models import ListingCandidate, ScoreResult


def keyword_match_score(
    title: str,
    included_keywords: list[str],
    excluded_keywords: list[str] | None = None,
) -> int:
    """Return a simple deterministic score for keyword matches."""

    normalized_title = title.casefold()
    exclusions = excluded_keywords or []
    if any(keyword.casefold() in normalized_title for keyword in exclusions):
        return 0

    return sum(
        1
        for keyword in included_keywords
        if keyword.casefold() in normalized_title
    )


def score_listing(
    listing: ListingCandidate,
    car_query: str,
    keywords: list[str],
    excluded_keywords: list[str],
) -> ScoreResult:
    """Score a listing against a watch query and keyword rules."""

    searchable_text = " ".join(
        part for part in [listing.title, listing.description or ""] if part
    ).casefold()
    reasons: list[str] = []

    rejected_terms = [
        keyword for keyword in excluded_keywords if keyword.casefold() in searchable_text
    ]
    if rejected_terms:
        return ScoreResult(
            score=-100,
            is_match=False,
            reasons=[f"excluded keyword: {term}" for term in rejected_terms],
        )

    score = 0
    for term in car_query.split():
        if term.casefold() in searchable_text:
            score += 2
            reasons.append(f"query term matched: {term}")

    for keyword in keywords:
        if keyword.casefold() in searchable_text:
            score += 5
            reasons.append(f"keyword matched: {keyword}")

    if listing.price_amount is None:
        reasons.append("price missing")
    if listing.mileage_value is None:
        reasons.append("mileage missing")

    return ScoreResult(score=score, is_match=score > 0, reasons=reasons)
