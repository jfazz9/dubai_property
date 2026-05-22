import re
from datetime import date

from enquiry_matcher import parse_bedrooms, parse_budget
from workflow_paths import normalize_purpose

from .constants import (
    COMMUNITY_ALIASES,
    MARKET_COMMUNITIES,
    MONTH_ALIASES,
    MUST_HAVE_TERMS,
    VILLA_COMMUNITIES,
    DEFAULT_SALE_STRETCH_RATIO,
    DEFAULT_RENT_STRETCH_RATIO,
    SALE_BUDGET_FLOOR_RATIO,
    RENT_BUDGET_FLOOR_RATIO,
)


def infer_purpose(text, selected):
    if selected and selected != "auto":
        return normalize_purpose(selected)

    normalized = text.lower()

    if re.search(r"\b(rent|rental|tenant|lease|let)\b", normalized):
        return "rent"

    if re.search(r"\b(buy|buyer|sale|purchase|mortgage|end user)\b", normalized):
        return "sale"

    if re.search(r"\d+(?:\.\d+)?\s*m\b", normalized):
        return "sale"

    if re.search(r"\d+(?:\.\d+)?\s*k\b", normalized):
        return "rent"

    return "sale"


def parse_budget_from_prompt(text):
    normalized = text.lower().replace(",", "")
    suffix_pattern = r"(m|mn|mil|million|k|thousand)?"
    budget_patterns = [
        rf"(?:budget|upto|up to|under|less than|max|maximum|around|at|of)\s*(?:aed\s*)?(\d+(?:\.\d+)?)\s*{suffix_pattern}",
        rf"(?:aed\s*)?(\d+(?:\.\d+)?)\s*{suffix_pattern}\b",
    ]

    for pattern in budget_patterns:
        matches = re.findall(pattern, normalized)

        if matches:
            for number, suffix in reversed(matches):
                if suffix or float(number) >= 1000:
                    return parse_budget(f"{number}{suffix}")

    return None


def has_strict_budget_language(text):
    return bool(re.search(r"\b(under|less than|max|maximum|up to|upto)\b", text.lower()))


def parse_stretch_budget_from_prompt(text):
    normalized = text.lower().replace(",", "")
    suffix_pattern = r"(m|mn|mil|million|k|thousand)?"
    stretch_patterns = [
        rf"(?:stretch|up to|upto|maximum|max)\s*(?:aed\s*)?(\d+(?:\.\d+)?)\s*{suffix_pattern}",
    ]

    for pattern in stretch_patterns:
        matches = re.findall(pattern, normalized)

        if matches:
            number, suffix = matches[-1]
            return parse_budget(f"{number}{suffix}")

    return None


def default_stretch_budget(purpose, budget, explicit_stretch=None, strict_budget=False):
    if explicit_stretch:
        return explicit_stretch

    if strict_budget:
        return budget

    if purpose == "sale" and budget:
        return int(round(budget * DEFAULT_SALE_STRETCH_RATIO))

    if purpose == "rent" and budget:
        return int(round(budget * DEFAULT_RENT_STRETCH_RATIO))

    return budget


def default_budget_floor(purpose, budget):
    if not budget:
        return None

    ratio = SALE_BUDGET_FLOOR_RATIO if purpose == "sale" else RENT_BUDGET_FLOOR_RATIO
    return int(round(budget * ratio))


def parse_bedroom_options(text):
    normalized = text.lower()
    slash_match = re.search(r"\b(\d+)\s*/\s*(\d+)\s*(?:beds?|bedrooms?|br)\b", normalized)

    if slash_match:
        return sorted({int(slash_match.group(1)), int(slash_match.group(2))})

    match = re.search(r"\b(\d+)\s*(?:beds?|bedrooms?|br|bhk)\b", normalized)

    if match:
        return [int(match.group(1))]

    match = re.search(r"\b(?:beds?|bedrooms?|br|bhk)\s*(\d+)\b", normalized)
    return [int(match.group(1))] if match else []


def parse_community(text):
    normalized = text.lower()

    for alias, community in sorted(COMMUNITY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return community

    return ""


def parse_communities_from_text(text):
    """Return all specific AR2 sub-communities mentioned in text, in order of appearance.

    The parent alias "Arabian Ranches 2" / "ar2" is excluded from the list — it means
    the whole area, not a specific sub-community. Returns an empty list when no specific
    community is found.
    """
    normalized = text.lower()
    # Track which communities have been matched to avoid duplicates
    seen = set()
    # We want to return them in the order they appear in the text, not alias-length order.
    # Build a map from community name → earliest match position.
    positions = {}
    for alias, community in sorted(COMMUNITY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if community == "Arabian Ranches 2":
            continue
        if community in seen:
            continue
        match = re.search(rf"\b{re.escape(alias)}\b", normalized)
        if match:
            seen.add(community)
            positions[community] = match.start()
    # Return in the order they appear in the text
    return [c for c, _ in sorted(positions.items(), key=lambda item: item[1])]


def parse_must_haves(text):
    normalized = text.lower()
    return [term for term in MUST_HAVE_TERMS if term in normalized]


def parse_preferred_villa_types(text):
    normalized = text.lower()
    types = set()

    for match in re.finditer(r"\btype\s*(\d+[a-z]?)\b", normalized):
        types.add(f"Type {match.group(1).upper()}")

    return sorted(types)


def parse_move_month(text):
    normalized = text.lower()

    for month_name, month_number in MONTH_ALIASES.items():
        if re.search(rf"\b{re.escape(month_name)}\b", normalized):
            return month_number

    if "month end" in normalized or "end of month" in normalized:
        return date.today().month

    return None


def parse_explicit_category(text):
    normalized = text.lower()

    if re.search(r"\b(no|not|dont|don't|doesnt|doesn't|without)\s+(?:want\s+)?(?:a\s+)?(?:town\s*house|townhouse)s?\b", normalized):
        return "villa"

    if re.search(r"\bvilla\b", normalized) and re.search(r"\b(alternative|fallback|compromise|backup)\b.{0,40}\b(?:town\s*house|townhouse)s?\b", normalized):
        return "villa"

    if re.search(r"\btown\s*house\b|\btownhouse\b", normalized):
        return "townhouse"

    if re.search(r"\bvilla\b", normalized):
        return "villa"

    return None


def parse_budget_reality_mode(text):
    normalized = text.lower()
    return bool(re.search(r"\b(unrealistic|reality|build a case|prove|budget issue|not realistic)\b", normalized))


def parse_preferred_category(text, purpose, budget, community=""):
    explicit_category = parse_explicit_category(text)

    if explicit_category:
        return explicit_category

    if community in VILLA_COMMUNITIES:
        return "villa"

    if purpose == "sale" and budget and budget >= 4_500_000:
        return "villa"

    return None


def normalize_search_intent(intent):
    normalized = str(intent or "auto").strip().lower().replace("-", "_").replace(" ", "_")
    allowed = {
        "auto",
        "best_value",
        "move_in_ready",
        "upgrade_potential",
        "negotiation",
        "listing_opportunity",
    }
    aliases = {
        "moveinready": "move_in_ready",
        "ready": "move_in_ready",
        "upgrade": "upgrade_potential",
        "renovation": "upgrade_potential",
        "negotiate": "negotiation",
        "listing": "listing_opportunity",
        "poach": "listing_opportunity",
        "value": "best_value",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in allowed else "auto"


def normalize_market_scope(scope):
    normalized = str(scope or "auto").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in {"auto", "exact", "similar", "custom"} else "auto"


def normalize_market_communities(communities):
    if not communities:
        return []

    if isinstance(communities, str):
        communities = re.split(r"[,|]", communities)

    aliases = {value.lower(): value for value in MARKET_COMMUNITIES}
    cleaned = []

    for community in communities:
        key = str(community or "").strip().lower()

        if key in aliases and aliases[key] not in cleaned:
            cleaned.append(aliases[key])

    return cleaned


def parse_prompt(
    text,
    selected_purpose,
    selected_intent="auto",
    market_scope="auto",
    market_communities=None,
    listing_scope="auto",
    listing_communities=None,
):
    purpose = infer_purpose(text, selected_purpose)
    bedrooms = parse_bedroom_options(text)
    budget = parse_budget_from_prompt(text)
    explicit_stretch = parse_stretch_budget_from_prompt(text)
    strict_budget = has_strict_budget_language(text)
    stretch_budget = default_stretch_budget(purpose, budget, explicit_stretch, strict_budget)
    community = parse_community(text)
    explicit_category = parse_explicit_category(text)

    return {
        "purpose": purpose,
        "raw_prompt": text,
        "search_intent": normalize_search_intent(selected_intent),
        "listing_scope_mode": normalize_market_scope(listing_scope),
        "listing_communities": normalize_market_communities(listing_communities),
        "market_scope_mode": normalize_market_scope(market_scope),
        "market_communities": normalize_market_communities(market_communities),
        "budget": budget,
        "stretch_budget": stretch_budget,
        "budget_floor": default_budget_floor(purpose, budget),
        "budget_strategy": (
            "8% negotiation stretch" if purpose == "sale" and budget and not explicit_stretch
            else "15% rental stretch" if purpose == "rent" and budget and not explicit_stretch
            else ""
        ) if not strict_budget else "strict budget",
        "bedrooms_options": bedrooms,
        "bedrooms": bedrooms[0] if bedrooms else None,
        "bedrooms_label": "/".join(str(value) for value in bedrooms) if bedrooms else "Any",
        "community": community,
        "must_haves": parse_must_haves(text),
        "preferred_villa_types": parse_preferred_villa_types(text),
        "preferred_category": parse_preferred_category(text, purpose, budget, community),
        "strict_category": bool(explicit_category),
        "budget_reality_mode": parse_budget_reality_mode(text),
        "move_month": parse_move_month(text),
    }
