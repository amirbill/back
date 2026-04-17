import re
import unicodedata


def normalize_search_text(value: str) -> str:
    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def get_search_terms(query: str) -> list[str]:
    normalized_query = normalize_search_text(query)
    terms = [normalized_query] if normalized_query else []
    terms.extend(token for token in normalized_query.split(" ") if len(token) >= 2)

    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            unique_terms.append(term)

    return unique_terms


def score_search_match(
    query: str,
    *,
    title: str = "",
    sku: str = "",
    brand: str = "",
    category: str = "",
) -> float:
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return 0.0

    candidate_parts = [title, sku, brand, category]
    candidate_text = " ".join(
        normalize_search_text(part) for part in candidate_parts if part
    ).strip()

    if not candidate_text:
        return 0.0

    candidate_tokens = candidate_text.split()
    score = 0.0

    normalized_title = normalize_search_text(title)
    normalized_sku = normalize_search_text(sku)
    normalized_brand = normalize_search_text(brand)
    normalized_category = normalize_search_text(category)
    search_terms = get_search_terms(query)

    if normalized_sku and normalized_query == normalized_sku:
        score += 500
    elif normalized_sku and normalized_query in normalized_sku:
        score += 260

    if normalized_title and normalized_query == normalized_title:
        score += 320
    elif normalized_title.startswith(normalized_query):
        score += 180
    elif normalized_query in normalized_title:
        score += 120

    if normalized_brand:
        if normalized_query == normalized_brand:
            score += 150
        elif normalized_query in normalized_brand:
            score += 90

    if normalized_category:
        if normalized_query == normalized_category:
            score += 100
        elif normalized_query in normalized_category:
            score += 60

    matched_terms = 0
    prefix_matches = 0

    for term in search_terms:
        if term in candidate_text:
            matched_terms += 1
            score += 18

        if any(token.startswith(term) for token in candidate_tokens):
            prefix_matches += 1
            score += 14

    if search_terms and matched_terms == len(search_terms):
        score += 70

    score += prefix_matches * 6
    score += len(candidate_tokens) * 0.15

    return round(score, 4)