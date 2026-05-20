import re

import pandas as pd


OUTDOOR_KEYWORDS = [
    "bbq",
    "barbecue",
    "garden",
    "landscaped",
    "landscape",
    "large plot",
    "huge plot",
    "single row",
    "park",
    "pool",
    "yard",
    "outdoor",
    "outside",
    "seating",
    "sitting",
    "terrace",
    "patio",
]
AR2_COMMUNITIES = {
    "azalea",
    "camel ia",
    "camelia",
    "casa",
    "lila",
    "palma",
    "rasha",
    "reem",
    "rosa",
    "samara",
    "yasmin",
}
AR2_SEARCH_TERMS = {"arabian ranches 2", "arabian ranches ii", "ar2"}
TOWNHOUSE_COMMUNITIES = {"camelia", "reem"}
OUTDOOR_INTENT_TERMS = {
    "bbq",
    "barbecue",
    "outdoor",
    "outside",
    "sitting",
    "seating",
    "garden",
    "terrace",
    "patio",
    "yard",
    "pool",
    "plot",
}
SOFT_INTENT_GROUPS = {
    "best_value": {
        "triggers": [
            "best value",
            "value",
            "deal",
            "best price",
            "great price",
            "cheap",
            "below market",
        ],
        "clues": {
            "best price": 16,
            "great price": 14,
            "price reduced": 16,
            "price reduction": 16,
            "motivated seller": 14,
            "motivated": 10,
            "investor deal": 12,
            "investment deal": 10,
            "vacant": 8,
            "vacant on transfer": 10,
            "vot": 10,
            "large plot": 8,
            "huge plot": 8,
            "big plot": 8,
            "single row": 6,
            "corner plot": 6,
        },
        "penalties": {
            "luxury villa": -8,
            "fully upgraded": -8,
            "one of a kind": -8,
            "fully done": -8,
            "exclusive": -5,
        },
    },
    "move_in_ready": {
        "triggers": [
            "nice",
            "clean",
            "ready",
            "move in",
            "move-in",
            "low hassle",
            "well maintained",
            "upgraded",
            "renovated",
            "modern",
            "immaculate",
            "spacious",
            "bright",
        ],
        "clues": {
            "ready to move": 16,
            "ready-to-move": 16,
            "move in ready": 16,
            "vacant": 12,
            "vacant on transfer": 14,
            "vot": 14,
            "well maintained": 14,
            "immaculate": 14,
            "pristine": 12,
            "upgraded": 12,
            "renovated": 12,
            "modern": 10,
            "turnkey": 14,
            "owner occupied": 8,
            "furnished": 6,
            "fully furnished": 8,
            "appliances included": 8,
            "landscaped": 6,
            "clean": 8,
            "spacious": 3,
            "bright": 3,
            "natural light": 3,
            "open-plan": 3,
            "open plan": 3,
            "family home": 5,
            "prime location": 2,
            "quiet": 4,
            "internal location": 4,
            "covered parking": 3,
        },
        "penalties": {
            "needs work": -18,
            "needs renovation": -18,
            "renovation opportunity": -16,
            "original condition": -14,
            "blank canvas": -10,
            "notice served": -6,
            "rented": -8,
        },
    },
    "upgrade_potential": {
        "triggers": [
            "upgrade potential",
            "renovation",
            "renovate",
            "extend",
            "extension",
            "investor",
            "opportunity",
            "value add",
            "project",
        ],
        "clues": {
            "upgrade potential": 16,
            "renovation": 14,
            "renovate": 14,
            "needs work": 14,
            "original condition": 14,
            "blank canvas": 14,
            "investor opportunity": 12,
            "investment opportunity": 10,
            "investor deal": 10,
            "notice served": 8,
            "extend": 12,
            "extension": 12,
            "large plot": 10,
            "huge plot": 10,
            "big plot": 10,
            "corner plot": 10,
            "corner": 8,
            "end unit": 8,
            "park backing": 8,
            "backing": 6,
            "green belt": 8,
            "treelined": 8,
            "tree lined": 8,
            "big garden": 8,
            "large garden": 8,
        },
        "penalties": {
            "fully upgraded": -24,
            "fully renovated": -24,
            "fully done": -24,
            "extended and upgraded": -22,
            "upgraded and extended": -22,
            "elegantly renovated": -20,
            "luxury villa": -18,
            "dream family home": -16,
            "one of a kind": -16,
            "maison lagom": -16,
            "turnkey": -14,
            "designer": -12,
            "furnished": -8,
            "upgraded": -8,
            "renovated": -8,
            "extended": -6,
        },
    },
    "negotiation": {
        "triggers": [
            "negotiation",
            "negotiate",
            "offer",
            "discount",
            "motivated",
            "price reduced",
        ],
        "clues": {
            "motivated seller": 18,
            "motivated": 12,
            "price reduced": 16,
            "price reduction": 16,
            "best price": 10,
            "great price": 10,
            "investor deal": 12,
            "vacant": 10,
            "vacant on transfer": 12,
            "vot": 12,
            "rented": 6,
            "notice served": 8,
            "owner occupied": 5,
        },
        "penalties": {
            "exclusive": -10,
            "rare": -6,
            "luxury": -6,
            "one of a kind": -8,
            "fully upgraded": -6,
        },
    },
    "listing_opportunity": {
        "triggers": [
            "listing opportunity",
            "poach",
            "owner lead",
            "landlord",
            "seller lead",
        ],
        "clues": {
            "motivated seller": 16,
            "motivated": 10,
            "vacant": 8,
            "vacant on transfer": 8,
            "vot": 8,
            "price reduced": 10,
            "investor deal": 10,
            "multiple options": 5,
            "rented": 5,
            "notice served": 6,
        },
        "penalties": {
            "exclusive": -24,
            "community expert": -4,
            "rare": -4,
            "luxury": -5,
        },
    },
    "outdoor_family": {
        "triggers": [
            "garden",
            "outdoor",
            "bbq",
            "barbecue",
            "dog",
            "pet",
            "family",
            "kids",
            "children",
        ],
        "clues": {
            "garden": 10,
            "private garden": 12,
            "private landscaped garden": 14,
            "beautifully landscaped garden": 12,
            "landscaped": 8,
            "large plot": 10,
            "huge plot": 10,
            "big plot": 10,
            "large garden": 10,
            "big garden": 10,
            "bbq": 8,
            "barbecue": 8,
            "outdoor": 8,
            "terrace": 6,
            "patio": 6,
            "pool": 6,
            "park": 6,
            "pool and park": 8,
            "pool park": 8,
            "close to pool": 8,
            "close to park": 8,
            "near pool": 6,
            "near park": 6,
            "walking trails": 5,
            "children play": 5,
            "kids play": 5,
            "children": 5,
            "kids": 5,
            "pet": 5,
        },
    },
}
SEARCH_INTENT_NAMES = set(SOFT_INTENT_GROUPS)
DESCRIPTION_COLUMNS = ["title", "description", "description_json", "url"]
COMMUNITY_RELATIONSHIPS = {
    "casa": {
        "similar": {"palma"},
        "secondary": {"samara", "azalea", "lila"},
        "stretch": {"rosa", "yasmin", "rasha"},
        "exclude": {"camelia", "reem"},
    },
    "palma": {
        "similar": {"casa"},
        "secondary": {"samara", "azalea", "lila"},
        "stretch": {"rosa", "yasmin", "rasha"},
        "exclude": {"camelia", "reem"},
    },
}
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def clean_number(value):
    if value is None or pd.isna(value):
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        match = re.search(r"\d[\d,]*", str(value))
        return int(match.group(0).replace(",", "")) if match else None


def parse_budget(text):
    if not text:
        return None

    normalized = str(text).lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(k|thousand|m|mn|mil|million)?", normalized)

    if not match:
        return None

    number = float(match.group(1))
    suffix = match.group(2)

    if suffix in {"m", "mn", "mil", "million"}:
        number *= 1_000_000
    elif suffix in {"k", "thousand"} or number < 1000:
        number *= 1000

    return int(number)


def parse_bedrooms(text):
    if text is None:
        return None

    normalized = str(text).lower()
    match = re.search(r"\b(\d+)\s*(?:beds?|bedrooms?|br)\b", normalized)

    if match:
        return int(match.group(1))

    match = re.search(r"\b(\d+)\b", normalized)
    return int(match.group(1)) if match else None


def is_active_value(value):
    if value is None or pd.isna(value):
        return True

    return str(value).strip().lower() in {"true", "1", "yes", "active"}


def has_inactive_status(value):
    if value is None or pd.isna(value):
        return False

    status = str(value or "").strip().lower()

    if not status or status in {"nan", "none", "unknown", "unknown_unclear_page"}:
        return False

    inactive_terms = [
        "inactive",
        "not_found",
        "not found",
        "removed",
        "unavailable",
        "expired",
        "deleted",
        "sold",
        "rented",
        "404",
    ]
    return any(term in status for term in inactive_terms)


def searchable_active_row(row):
    if "active_check_status" in row and has_inactive_status(row.get("active_check_status")):
        return False

    if "is_active" not in row:
        return True

    if is_active_value(row.get("is_active")):
        return True

    status = row.get("active_check_status")

    if status is None or pd.isna(status):
        return True

    return not str(status).strip()


def text_contains(value, needle):
    if not needle:
        return True

    return str(value or "").lower().find(str(needle).lower()) >= 0


def combined_listing_text(row):
    return " ".join(str(row.get(column) or "") for column in DESCRIPTION_COLUMNS).lower()


def outdoor_matches(row):
    haystack = combined_listing_text(row)

    return [keyword for keyword in OUTDOOR_KEYWORDS if keyword in haystack]


def is_ar2_query(community):
    normalized = str(community or "").strip().lower()
    return normalized in AR2_SEARCH_TERMS


def matches_community(row, community):
    if not community:
        return True

    predicted_community = str(row.get("predicted_community") or "").lower()
    haystack = combined_listing_text(row)

    if is_ar2_query(community):
        return (
            "arabian-ranches-2" in haystack
            or "arabian ranches 2" in haystack
            or predicted_community in AR2_COMMUNITIES
        )

    return str(community).lower() in predicted_community or str(community).lower() in haystack


def has_outdoor_intent(must_haves):
    for item in must_haves:
        words = set(re.findall(r"[a-z]+", item.lower()))

        if words & OUTDOOR_INTENT_TERMS:
            return True

    return False


def price_column_for_purpose(purpose):
    return "annual_rent" if purpose == "rent" else "price"


def listing_category(row):
    haystack = combined_listing_text(row)
    community = str(row.get("predicted_community") or "").strip().lower()

    if "townhouse" in haystack or community in TOWNHOUSE_COMMUNITIES:
        return "townhouse"

    if "villa" in haystack:
        return "villa"

    return "unknown"


def community_relationship(row, community):
    if not community or is_ar2_query(community):
        return "parent" if is_ar2_query(community) else "any"

    requested = str(community).strip().lower()
    row_community = str(row.get("predicted_community") or "").strip().lower()

    if not row_community:
        return "unknown"

    if row_community == requested:
        return "preferred"

    relationship = COMMUNITY_RELATIONSHIPS.get(requested, {})

    for band in ["similar", "secondary", "stretch", "exclude"]:
        if row_community in relationship.get(band, set()):
            return band

    return "other"


def availability_points(row, enquiry):
    target_month = enquiry.get("move_month")

    if not target_month:
        return 0, []

    haystack = combined_listing_text(row)
    reasons = []
    score = 0

    if "vacant on transfer" in haystack or re.search(r"\bvot\b", haystack):
        score += 18
        reasons.append("vacant on transfer clue")
    elif "ready to move" in haystack or "move-in ready" in haystack or "vacant now" in haystack:
        score += 18
        reasons.append("ready/vacant now clue")
    elif "vacant soon" in haystack or "available soon" in haystack:
        score += 10
        reasons.append("vacant soon clue")

    mentioned_months = {
        month_number
        for month_name, month_number in MONTHS.items()
        if re.search(rf"\b{re.escape(month_name)}\b", haystack)
    }

    if target_month in mentioned_months:
        score += 22
        reasons.append("mentions requested move month")
    elif mentioned_months and min(mentioned_months) > target_month:
        score -= 24
        reasons.append("availability appears after requested move month")
    elif "tenanted" in haystack or "rented" in haystack:
        score -= 12
        reasons.append("tenanted/rented clue")

    return score, reasons


def villa_type_points(row, enquiry):
    preferred_types = enquiry.get("preferred_villa_types") or []

    if not preferred_types:
        return 0, []

    predicted_type = str(row.get("predicted_type") or row.get("detected_type_from_description") or "").lower()
    haystack = combined_listing_text(row)

    for villa_type in preferred_types:
        normalized_type = villa_type.lower()

        if normalized_type in predicted_type:
            return 34, [f"matches requested {villa_type}"]

        if re.search(rf"\b{re.escape(normalized_type)}\b", haystack):
            return 26, [f"description mentions requested {villa_type}"]

    if predicted_type and predicted_type not in {"unknown", "nan"}:
        return -22, [f"{row.get('predicted_type')} vs requested {'/'.join(preferred_types)}"]

    return -8, [f"type unclear vs requested {'/'.join(preferred_types)}"]


def price_fit_points(price, budget, purpose):
    if price is None or not budget:
        return 0, []

    ratio = price / budget

    if purpose == "sale":
        near_floor = 0.85
        value_floor = 0.7
        stretch_ceiling = 1.08
    else:
        near_floor = 0.9
        value_floor = 0.8
        stretch_ceiling = 1.15

    if near_floor <= ratio <= 1:
        return 18, ["near the stated budget"]
    if 1 < ratio <= stretch_ceiling:
        return 16, ["premium stretch option"]
    if value_floor <= ratio < near_floor:
        return 8, ["comfortably under budget"]
    if ratio < value_floor:
        return -10, ["well below budget, likely lower-spec alternative"]

    return 0, []


def requested_soft_intents(enquiry):
    selected_intent = str(enquiry.get("search_intent") or "auto").lower().strip()

    if selected_intent in SEARCH_INTENT_NAMES:
        return [selected_intent]

    prompt_text = str(enquiry.get("raw_prompt") or "").lower()
    must_haves = " ".join(str(item).lower() for item in enquiry.get("must_haves", []))
    haystack = f"{prompt_text} {must_haves}"
    intents = []

    for intent_name, config in SOFT_INTENT_GROUPS.items():
        if any(trigger in haystack for trigger in config["triggers"]):
            intents.append(intent_name)

    return intents


def soft_intent_points(row, enquiry):
    intents = requested_soft_intents(enquiry)

    if not intents:
        return 0, []

    haystack = combined_listing_text(row)
    matched_points = {}
    matched_penalties = {}

    for intent_name in intents:
        for clue, points in SOFT_INTENT_GROUPS[intent_name]["clues"].items():
            if phrase_in_text(clue, haystack):
                matched_points[clue] = max(points, matched_points.get(clue, 0))

        for clue, points in SOFT_INTENT_GROUPS[intent_name].get("penalties", {}).items():
            if phrase_in_text(clue, haystack):
                matched_penalties[clue] = min(points, matched_penalties.get(clue, 0))

    if not matched_points and not matched_penalties:
        return 0, []

    score = sum(matched_points.values()) + sum(matched_penalties.values())
    matches = sorted(matched_points, key=lambda clue: (-matched_points[clue], -len(clue), clue))
    penalties = sorted(matched_penalties, key=lambda clue: (matched_penalties[clue], -len(clue), clue))
    reasons = []

    if matches:
        reasons.append(f"soft match clues: {', '.join(matches[:8])}")

    if penalties:
        reasons.append(f"soft weak clues: {', '.join(penalties[:6])}")

    return max(min(score, 55), -35), reasons


def intent_price_position_points(price, budget, enquiry):
    if price is None or not budget:
        return 0, []

    intents = requested_soft_intents(enquiry)

    if "move_in_ready" not in intents:
        return 0, []

    ratio = price / budget
    purpose = enquiry.get("purpose", "rent")
    stretch_ceiling = 1.08 if purpose == "sale" else 1.15

    if 1 < ratio <= stretch_ceiling:
        return 18, ["move-in ready premium stretch"]
    if 0.9 <= ratio <= 1:
        return 8, ["move-in ready near budget"]
    if 0.8 <= ratio < 0.9:
        return -6, ["move-in ready lower-budget option"]
    if ratio < 0.8:
        return -14, ["move-in ready well below budget"]

    return 0, []


def phrase_in_text(phrase, text):
    normalized_phrase = re.escape(str(phrase).lower()).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){normalized_phrase}(?![a-z0-9])", text) is not None


def score_listing(row, enquiry):
    score = 0
    reasons = []
    budget = enquiry.get("budget")
    stretch_budget = enquiry.get("stretch_budget") or budget
    bedrooms = enquiry.get("bedrooms")
    community = enquiry.get("community")
    must_haves = [item.lower() for item in enquiry.get("must_haves", [])]
    purpose = enquiry.get("purpose", "rent")
    price_column = price_column_for_purpose(purpose)
    price = clean_number(row.get(price_column)) or clean_number(row.get("price"))
    row_bedrooms = clean_number(row.get("bedrooms"))
    preferred_category = enquiry.get("preferred_category")
    category = listing_category(row)

    if community:
        relation = community_relationship(row, community)

        if matches_community(row, community):
            score += 25 if is_ar2_query(community) else 40
            reasons.append(f"matches preferred community ({community})")
        elif relation == "similar":
            score += 22
            reasons.append(f"similar community to {community}")
        elif relation == "secondary":
            score += 10
            reasons.append(f"secondary alternative to {community}")
        elif relation == "stretch":
            score += 4
            reasons.append(f"larger-villa alternative to {community}")
        elif relation == "exclude":
            score -= 60
            reasons.append(f"excluded community for {community}-style enquiry")
        else:
            score -= 30
            reasons.append(f"not in preferred community ({community})")

    if bedrooms is not None and row_bedrooms is not None:
        if row_bedrooms == bedrooms:
            score += 30
            reasons.append(f"{bedrooms} bedrooms")
        elif row_bedrooms == bedrooms + 1:
            score += 8
            reasons.append(f"{row_bedrooms} bedrooms, one above request")
        else:
            score -= 45
            reasons.append(f"{row_bedrooms} bedrooms vs requested {bedrooms}")

    if price is not None and budget:
        if price <= budget:
            score += 30
            reasons.append("within budget")
        elif stretch_budget and price <= stretch_budget:
            score += 24
            reasons.append(f"within stretch budget ({price:,})")
        else:
            gap = price - stretch_budget if stretch_budget else price - budget
            score -= min(40, max(5, round(gap / 5000)))
            reasons.append(f"{gap:,} above stretch budget")

        fit_score, fit_reasons = price_fit_points(price, budget, purpose)
        score += fit_score
        reasons.extend(fit_reasons)

    if preferred_category:
        if category == preferred_category:
            score += 20
            reasons.append(f"{preferred_category} stock")
        elif category != "unknown":
            score -= 28
            reasons.append(f"{category} alternative, not {preferred_category}")

    type_score, type_reasons = villa_type_points(row, enquiry)
    score += type_score
    reasons.extend(type_reasons)

    availability_score, availability_reasons = availability_points(row, enquiry)
    score += availability_score
    reasons.extend(availability_reasons)

    soft_score, soft_reasons = soft_intent_points(row, enquiry)
    score += soft_score
    reasons.extend(soft_reasons)

    intent_price_score, intent_price_reasons = intent_price_position_points(price, budget, enquiry)
    score += intent_price_score
    reasons.extend(intent_price_reasons)

    matched_outdoor = outdoor_matches(row)

    if "dog" in must_haves or "pet" in must_haves or has_outdoor_intent(must_haves):
        if matched_outdoor:
            score += 18
            reasons.append("has outdoor/garden clues")
        else:
            score -= 8
            reasons.append("no clear outdoor/garden clues")

    return score, reasons, matched_outdoor


def match_enquiry(master_df, enquiry, limit=5):
    purpose = enquiry.get("purpose", "rent")
    price_column = price_column_for_purpose(purpose)
    stretch_budget = enquiry.get("stretch_budget") or enquiry.get("budget")

    df = master_df.copy()

    if "is_active" in df.columns or "active_check_status" in df.columns:
        df = df[df.apply(searchable_active_row, axis=1)]

    if "listing_purpose" in df.columns:
        df = df[df["listing_purpose"].fillna(purpose).str.lower() == purpose]

    scored_rows = []

    for _, row in df.iterrows():
        price = clean_number(row.get(price_column)) or clean_number(row.get("price"))
        budget_floor = enquiry.get("budget_floor")

        if price is not None and budget_floor and price < budget_floor:
            continue

        if price is not None and stretch_budget and price > stretch_budget and not enquiry.get("allow_over_ceiling"):
            continue

        if enquiry.get("strict_category") and enquiry.get("preferred_category"):
            if listing_category(row) != enquiry.get("preferred_category"):
                continue

        score, reasons, matched_outdoor = score_listing(row, enquiry)
        row_data = row.to_dict()
        row_data["match_score"] = score
        row_data["match_reasons"] = "; ".join(reasons)
        row_data["outdoor_matches"] = ", ".join(matched_outdoor)
        row_data["budget_gap"] = price - stretch_budget if price is not None and stretch_budget else None
        row_data["budget_distance"] = abs(price - stretch_budget) if price is not None and stretch_budget else None
        scored_rows.append(row_data)

    result_df = pd.DataFrame(scored_rows)

    if result_df.empty:
        return result_df

    sort_columns = ["match_score", "budget_distance"]
    ascending = [False, True]

    return result_df.sort_values(sort_columns, ascending=ascending).head(limit)


def format_currency(value):
    number = clean_number(value)
    return f"{number:,}" if number is not None else "unknown"


def build_client_response(matches_df, enquiry):
    purpose = enquiry.get("purpose", "rent")
    price_label = "rent" if purpose == "rent" else "price"
    budget = enquiry.get("budget")
    stretch_budget = enquiry.get("stretch_budget")
    community = enquiry.get("community")
    bedrooms = enquiry.get("bedrooms")

    if matches_df.empty:
        return (
            f"I checked the current active listings for {community or 'the preferred area'}. "
            f"I could not find a strong {bedrooms or ''} bedroom match around {format_currency(budget)}."
        )

    best = matches_df.iloc[0]
    best_price = best.get("annual_rent") if purpose == "rent" else best.get("price")
    intro = (
        f"I checked the current active listings. For {community or 'the preferred area'}, "
        f"the closest {bedrooms or ''} bedroom options I found start from around {format_currency(best_price)}."
    )

    if budget and clean_number(best_price) and clean_number(best_price) > (stretch_budget or budget):
        intro += f" That is above the stated budget of {format_currency(budget)}."

    lines = [intro, "", "Best options I would check first:"]

    for index, (_, row) in enumerate(matches_df.iterrows(), start=1):
        price = row.get("annual_rent") if purpose == "rent" else row.get("price")
        lines.append(
            f"{index}. {format_currency(price)} {price_label} - "
            f"{clean_number(row.get('bedrooms')) or '?'} bed - "
            f"{row.get('predicted_community') or 'Unknown area'} - "
            f"{row.get('title') or 'Untitled listing'}"
        )

    return "\n".join(lines)
