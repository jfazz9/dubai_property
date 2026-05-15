import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from ai_enquiry_ranker import merge_ai_rankings, rank_matches_with_ai
from enquiry_matcher import build_client_response, clean_number, match_enquiry, parse_bedrooms, parse_budget
from workflow_paths import master_file, normalize_purpose

OWNER_LEADS_FILE = "data/owner_property_leads.csv"
MARKET_SALES_FILE = "data/dxb_market_sales.csv"
MARKET_RENTALS_FILE = "data/arabian_ranches_2_rentals.csv"
DEFAULT_RESULT_LIMIT = 20
DEFAULT_AI_RESULT_LIMIT = 10
DEFAULT_AI_SHORTLIST_LIMIT = 12
DEFAULT_AI_BATCH_SIZE = 4
DEFAULT_AI_FINAL_CANDIDATE_LIMIT = 6
AI_DESCRIPTION_CHARS = 700
MARKET_CONTEXT_TRANSACTION_LIMIT = 5
OVER_BUDGET_LIMIT = 5
SALE_OVER_BUDGET_RATIO = 1.40
RENT_OVER_BUDGET_RATIO = 1.25
DEFAULT_SALE_STRETCH_RATIO = 1.08
DEFAULT_RENT_STRETCH_RATIO = 1.15
SALE_BUDGET_FLOOR_RATIO = 0.82
RENT_BUDGET_FLOOR_RATIO = 0.80
COMMUNITY_ALIASES = {
    "arabian ranches 2": "Arabian Ranches 2",
    "arabian ranches ii": "Arabian Ranches 2",
    "ar2": "Arabian Ranches 2",
    "azalea": "Azalea",
    "camelia": "Camelia",
    "casa": "Casa",
    "lila": "Lila",
    "palma": "Palma",
    "rasha": "Rasha",
    "reem": "Reem",
    "rosa": "Rosa",
    "samara": "Samara",
    "yasmin": "Yasmin",
}
MUST_HAVE_TERMS = [
    "bbq",
    "barbecue",
    "dog",
    "pet",
    "garden",
    "pool",
    "single row",
    "corner",
    "vacant",
    "upgraded",
    "furnished",
    "landscaped",
    "large plot",
    "huge plot",
]
VILLA_COMMUNITIES = {"Casa", "Palma", "Samara", "Azalea", "Lila", "Rosa", "Yasmin", "Rasha"}
MARKET_COMMUNITIES = ["Azalea", "Camelia", "Casa", "Lila", "Palma", "Rasha", "Reem", "Rosa", "Samara", "Yasmin"]
SIMILAR_MARKET_GROUPS = [
    {"Casa", "Samara"},
    {"Palma", "Lila"},
    {"Rosa", "Rasha", "Yasmin"},
    {"Camelia", "Reem"},
]
MONTH_ALIASES = {
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

SCENARIOS = {
    "best_value": {
        "label": "Best Value",
        "report_title": "Best Value Report",
        "focus": (
            "Rank the best value options for the client brief. Compare asking price, price per sqft, "
            "plot/BUA, vacancy, community, predicted type, recent transactions, and active shortlist pricing. "
            "Separate genuine value from listings that are cheap only because they are the wrong product or location."
        ),
    },
    "budget_reality": {
        "label": "Budget Reality",
        "report_title": "Budget Reality Report",
        "focus": (
            "Build a budget reality case. Show whether the client budget is realistic using active listings and recent transactions. "
            "If the requested product is above budget, show realistic options first and explain the market gap clearly."
        ),
    },
    "fallback": {
        "label": "Analyse Fallback",
        "report_title": "Analysed Fallback Options",
        "focus": (
            "Analyse only the fallback townhouse options. Rank the strongest premium compromise first, "
            "then separate stronger premium choices from cheaper budget-saving alternatives. Compare upgrade clues, "
            "single-row/corner/end-unit position, large plot/garden, vacancy, family usability, and value against recent rental transactions. "
            "Explain whether each fallback is a real compromise for a villa client or merely a cheaper townhouse."
        ),
    },
    "negotiation": {
        "label": "Negotiation Case",
        "report_title": "Negotiation Case",
        "focus": (
            "Build a negotiation case for the shortlist. Use market comps, active alternatives, listing age, vacancy, "
            "price per sqft, missing/weak features, size mismatches, and over-budget gaps. Suggest practical offer angles and verification questions."
        ),
    },
    "listing_opportunity": {
        "label": "Listing Opportunity",
        "report_title": "Listing Opportunity Report",
        "focus": (
            "Rank the best listing or poach opportunities. Prioritize non-exclusive listings, owner-lead availability, stale or repeated listings, "
            "vacant stock, price reductions, weak presentation, data mismatches, and owners who may benefit from a sharper pricing strategy."
        ),
    },
    "upgrade_potential": {
        "label": "Upgrade Potential",
        "report_title": "Upgrade Potential Report",
        "focus": (
            "Rank properties with extension, renovation, or value-add potential. Use the collected fields such as predicted_community, "
            "detected_type_from_description, predicted_type, property_size_sqft, plot_size_sqft, bua_from_description, plot_from_description, price_per_sqft, and description_json. "
            "Be type-aware: first use detected_type_from_description if it is present, otherwise use predicted_type. Only compare BUA and extension evidence within the same predicted_community plus same type group. "
            "Do not compare a Casa Type 1 directly with a Casa Type 2 and call the bigger one more extendable; bigger may simply be the natural layout. "
            "For example, a Type 1 can have a larger normal BUA than a Type 2, while the Type 2 may still have better extension potential depending on plot/layout. "
            "Compare similar community/type listings in the supplied rows: if the same type/community sometimes has a larger BUA, larger plot, "
            "or description clues such as extended, extension, upgrade potential, renovate, renovation, investor opportunity, original condition, "
            "blank canvas, large plot, corner, end unit, or big garden, flag it as potential only. Penalize fully turnkey listings unless the plot/BUA "
            "still suggests upside. Be careful: do not state extension is guaranteed; recommend verifying title deed, approvals, developer/community rules, and permissions."
        ),
    },
    "move_in_ready": {
        "label": "Move-in Ready",
        "report_title": "Move-in Ready Report",
        "focus": (
            "Rank the cleanest, lowest-hassle properties for an end user or tenant who wants a nice ready property. Use description_json and all row data. "
            "Prioritize upgraded, renovated, well maintained, immaculate, modern, turnkey, ready to move, vacant, vacant on transfer, furnished, appliances included, "
            "landscaped, owner occupied, new kitchen, clean, and strong maintenance clues. Penalize renovation projects, investor-only wording, needs work, tenanted, "
            "unclear availability, stale condition, and vague descriptions. Recommend verifying actual condition, photos, AC/maintenance, garden condition, and handover date."
        ),
    },
}


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


def read_master(purpose):
    path = master_file(purpose)

    if not path.exists():
        raise FileNotFoundError(f"Missing master file: {path}")

    return pd.read_csv(path), path


def clean_market_number(value):
    number = clean_number(value)
    return number if number is not None else None


def load_market_sales(path=MARKET_SALES_FILE):
    market_path = Path(path)

    if not market_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(market_path)

    for column in ["price", "price_per_sqft", "size_sqft", "beds"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "sold_date" in df.columns:
        df["_sold_date"] = pd.to_datetime(df["sold_date"], errors="coerce", dayfirst=True)

    return df


def load_market_rentals(path=MARKET_RENTALS_FILE):
    market_path = Path(path)

    if not market_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(market_path)

    numeric_columns = [
        "Bedrooms",
        "Size sqft",
        "Rental AED",
        "Rental Yield %",
        "Purchase Price AED",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "Start Date" in df.columns:
        df["_start_date"] = pd.to_datetime(df["Start Date"], errors="coerce", dayfirst=True)

    return df


def compact_market_row(row):
    return {
        "community": clean_value(row.get("community")),
        "price": clean_market_number(row.get("price")),
        "price_per_sqft": clean_market_number(row.get("price_per_sqft")),
        "size_sqft": clean_market_number(row.get("size_sqft")),
        "beds": clean_market_number(row.get("beds")),
        "sold_date": clean_value(row.get("sold_date")),
    }


def compact_rental_market_row(row):
    return {
        "location": clean_value(row.get("Location")),
        "community": clean_value(row.get("Community")),
        "property_type": clean_value(row.get("Property Type")),
        "bedrooms": clean_market_number(row.get("Bedrooms")),
        "size_sqft": clean_market_number(row.get("Size sqft")),
        "annual_rent": clean_market_number(row.get("Rental AED")),
        "rental_yield_percent": clean_value(row.get("Rental Yield %")),
        "status": clean_value(row.get("Status")),
        "start_date": clean_value(row.get("Start Date")),
    }


def numeric_summary(series):
    clean_series = pd.to_numeric(series, errors="coerce").dropna()

    if clean_series.empty:
        return {}

    return {
        "count": int(clean_series.count()),
        "min": int(clean_series.min()),
        "median": int(clean_series.median()),
        "max": int(clean_series.max()),
    }


def active_shortlist_market_summary(matches_df, enquiry):
    price_column = "annual_rent" if enquiry.get("purpose") == "rent" else "price"

    if matches_df.empty or price_column not in matches_df.columns:
        return {}

    summary = {
        "candidate_count": int(len(matches_df)),
        "asking_price": numeric_summary(matches_df[price_column]),
    }

    if "price_per_sqft" in matches_df.columns:
        pps_summary = numeric_summary(matches_df["price_per_sqft"])

        if pps_summary:
            summary["asking_price_per_sqft"] = pps_summary

    return summary


def active_match_communities(matches_df):
    if matches_df is None or matches_df.empty or "predicted_community" not in matches_df.columns:
        return []

    communities = []

    for community in matches_df["predicted_community"].dropna().astype(str):
        if community in MARKET_COMMUNITIES and community not in communities:
            communities.append(community)

    return communities


def similar_market_communities_for(community):
    if community not in MARKET_COMMUNITIES:
        return []

    for group in SIMILAR_MARKET_GROUPS:
        if community in group:
            return [item for item in MARKET_COMMUNITIES if item in group]

    return [community]


def market_context_communities(enquiry, matches_df):
    mode = normalize_market_scope(enquiry.get("market_scope_mode"))
    prompt_community = enquiry.get("community")
    selected = normalize_market_communities(enquiry.get("market_communities"))
    active_communities = active_match_communities(matches_df)

    if mode == "custom":
        return selected, "custom"

    if mode == "exact":
        if prompt_community and prompt_community != "Arabian Ranches 2":
            return [prompt_community], "exact"

        return active_communities[:1], "exact"

    if mode == "similar":
        base_community = prompt_community if prompt_community and prompt_community != "Arabian Ranches 2" else (active_communities[0] if active_communities else "")
        return similar_market_communities_for(base_community), "similar"

    if prompt_community and prompt_community != "Arabian Ranches 2":
        return [prompt_community], "auto_exact"

    return [], "auto_ar2"


def listing_scope_communities(enquiry):
    mode = normalize_market_scope(enquiry.get("listing_scope_mode"))
    selected = normalize_market_communities(enquiry.get("listing_communities"))
    prompt_community = enquiry.get("community")

    if mode == "custom":
        return selected

    if mode == "exact":
        return [prompt_community] if prompt_community and prompt_community != "Arabian Ranches 2" else []

    if mode == "similar":
        return similar_market_communities_for(prompt_community) if prompt_community and prompt_community != "Arabian Ranches 2" else []

    return []


def filter_master_by_listing_scope(master_df, enquiry):
    communities = listing_scope_communities(enquiry)

    if not communities or "predicted_community" not in master_df.columns:
        return master_df

    return master_df[master_df["predicted_community"].fillna("").astype(str).str.lower().isin(
        [community.lower() for community in communities]
    )]


def build_market_context(enquiry, matches_df, market_file=None):
    if enquiry.get("purpose") == "rent":
        return build_rental_market_context(enquiry, matches_df, market_file=market_file or MARKET_RENTALS_FILE)

    if enquiry.get("purpose") != "sale":
        return {
            "note": "No market context available for this enquiry purpose.",
            "active_shortlist": active_shortlist_market_summary(matches_df, enquiry),
        }

    market_file = market_file or MARKET_SALES_FILE
    market_df = load_market_sales(market_file)

    if market_df.empty:
        return {
            "note": f"Market sales CSV not found or empty: {market_file}",
            "active_shortlist": active_shortlist_market_summary(matches_df, enquiry),
        }

    bedrooms = enquiry.get("bedrooms")
    community = enquiry.get("community")
    comp_communities, scope_mode = market_context_communities(enquiry, matches_df)
    scoped = market_df.copy()

    if bedrooms and "beds" in scoped.columns:
        by_beds = scoped[scoped["beds"] == bedrooms]

        if not by_beds.empty:
            scoped = by_beds

    if comp_communities and "community" in scoped.columns:
        by_community = scoped[scoped["community"].str.lower().isin([item.lower() for item in comp_communities])]

        if not by_community.empty:
            scoped = by_community

    if "_sold_date" in scoped.columns:
        scoped = scoped.sort_values("_sold_date", ascending=False, na_position="last")

    market_summary = {
        "source": str(market_file),
        "scope": {
            "community": community or "Arabian Ranches 2",
            "market_scope_mode": scope_mode,
            "comp_communities": comp_communities or ["Arabian Ranches 2"],
            "beds": bedrooms or "any",
        },
        "dxb_report_summary": {
            "median_price": clean_market_number(market_df["median_price"].dropna().iloc[0]) if "median_price" in market_df.columns and not market_df["median_price"].dropna().empty else None,
            "median_price_per_sqft": clean_market_number(market_df["median_price_per_sqft"].dropna().iloc[0]) if "median_price_per_sqft" in market_df.columns and not market_df["median_price_per_sqft"].dropna().empty else None,
            "transactions": clean_market_number(market_df["transactions"].dropna().iloc[0]) if "transactions" in market_df.columns and not market_df["transactions"].dropna().empty else None,
            "rental_yield_percent": clean_market_number(market_df["rental_yield_percent"].dropna().iloc[0]) if "rental_yield_percent" in market_df.columns and not market_df["rental_yield_percent"].dropna().empty else None,
        },
        "recent_transaction_stats": {
            "price": numeric_summary(scoped["price"]) if "price" in scoped.columns else {},
            "price_per_sqft": numeric_summary(scoped["price_per_sqft"]) if "price_per_sqft" in scoped.columns else {},
        },
        "recent_transactions": [
            compact_market_row(row)
            for _, row in scoped.head(MARKET_CONTEXT_TRANSACTION_LIMIT).iterrows()
        ],
        "active_shortlist": active_shortlist_market_summary(matches_df, enquiry),
    }

    return market_summary


def build_rental_market_context(enquiry, matches_df, market_file=MARKET_RENTALS_FILE):
    market_df = load_market_rentals(market_file)

    if market_df.empty:
        return {
            "note": f"Rental market CSV not found or empty: {market_file}",
            "active_shortlist": active_shortlist_market_summary(matches_df, enquiry),
        }

    bedrooms = enquiry.get("bedrooms")
    community = enquiry.get("community")
    comp_communities, scope_mode = market_context_communities(enquiry, matches_df)
    scoped = market_df.copy()

    if bedrooms and "Bedrooms" in scoped.columns:
        by_beds = scoped[scoped["Bedrooms"] == bedrooms]

        if not by_beds.empty:
            scoped = by_beds

    if comp_communities and "Location" in scoped.columns:
        by_location = scoped[scoped["Location"].str.lower().isin([item.lower() for item in comp_communities])]

        if not by_location.empty:
            scoped = by_location

    if "_start_date" in scoped.columns:
        scoped = scoped.sort_values("_start_date", ascending=False, na_position="last")

    return {
        "source": str(market_file),
        "scope": {
            "community": community or "Arabian Ranches 2",
            "market_scope_mode": scope_mode,
            "comp_communities": comp_communities or ["Arabian Ranches 2"],
            "beds": bedrooms or "any",
            "purpose": "rent",
        },
        "recent_rental_stats": {
            "annual_rent": numeric_summary(scoped["Rental AED"]) if "Rental AED" in scoped.columns else {},
            "size_sqft": numeric_summary(scoped["Size sqft"]) if "Size sqft" in scoped.columns else {},
        },
        "recent_rental_transactions": [
            compact_rental_market_row(row)
            for _, row in scoped.head(MARKET_CONTEXT_TRANSACTION_LIMIT).iterrows()
        ],
        "active_shortlist": active_shortlist_market_summary(matches_df, enquiry),
    }


def clean_value(value):
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "item"):
        value = value.item()

    return value


def normalize_url(value):
    text = str(value or "").strip().strip('"').strip("'")

    if not text:
        return ""

    parsed = urlparse(text)
    path = parsed.path.rstrip("/")

    return f"{parsed.netloc.lower()}{path.lower()}"


def extract_urls(value):
    text = str(value or "")
    return re.findall(r"https?://[^\s,\"']+", text)


def find_column(df, candidates):
    normalized_columns = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:
        key = candidate.strip().lower()

        if key in normalized_columns:
            return normalized_columns[key]

    return None


def owner_row_value(row, df, candidates):
    column = find_column(df, candidates)

    if column is None:
        return ""

    value = row.get(column)
    return "" if value is None or pd.isna(value) else str(value)


def owner_property_summary(row, df):
    parts = [
        owner_row_value(row, df, ["No.", "Villa No.", "Villa No"]),
        owner_row_value(row, df, ["Street"]),
        owner_row_value(row, df, ["Community"]),
        owner_row_value(row, df, ["Area"]),
    ]
    return ", ".join(part for part in parts if part)


def owner_payload_from_row(row, df, matched_url, match_type):
    link_value = owner_row_value(row, df, ["Link", "Links", "propertyfinder_urls", "propertyfinder url"])
    urls = extract_urls(link_value)

    return {
        "found": True,
        "match_type": match_type,
        "matched_url": matched_url,
        "propertyfinder_urls": urls,
        "lead": {
            "date": owner_row_value(row, df, ["Date"]),
            "intent": owner_row_value(row, df, ["Sell/Rent", "Rent/Sell", "Intent"]),
            "owners": owner_row_value(row, df, ["Owners", "Owner"]),
            "numbers": owner_row_value(row, df, ["Numbers", "Phone", "Phones"]),
            "property": owner_property_summary(row, df),
            "beds": owner_row_value(row, df, ["Beds"]),
            "type": owner_row_value(row, df, ["Type"]),
            "gfa": owner_row_value(row, df, ["GFA"]),
            "bua": owner_row_value(row, df, ["BUA"]),
            "asking": owner_row_value(row, df, ["Asking"]),
            "rental": owner_row_value(row, df, ["Rental", "Rent"]),
            "notes": owner_row_value(row, df, ["Notes"]),
            "land_number": owner_row_value(row, df, ["Land Number"]),
            "latitude": owner_row_value(row, df, ["Latitude"]),
            "longitude": owner_row_value(row, df, ["Longitude"]),
        },
    }


def lookup_owner_in_df(owner_df, lookup_url):
    link_column = find_column(owner_df, ["Link", "Links", "propertyfinder_urls", "propertyfinder url"])

    if link_column is None:
        return {
            "found": False,
            "message": "Owner leads file does not have a Link column.",
        }

    normalized_lookup = normalize_url(lookup_url)

    if not normalized_lookup:
        return {
            "found": False,
            "message": "Paste a valid Property Finder URL.",
        }

    for _, row in owner_df.iterrows():
        urls = extract_urls(row.get(link_column))

        for url in urls:
            if normalize_url(url) == normalized_lookup:
                return owner_payload_from_row(row, owner_df, url, "exact_url")

    return {
        "found": False,
        "message": "No owner lead matched this Property Finder URL.",
    }


def lookup_owner(lookup_url, owner_file=OWNER_LEADS_FILE):
    path = Path(owner_file)

    if not path.exists():
        return {
            "found": False,
            "message": f"Owner leads file not found: {owner_file}",
        }

    owner_df = pd.read_csv(path)
    return lookup_owner_in_df(owner_df, lookup_url)


def money(value, purpose):
    number = clean_number(value)

    if number is None:
        return "Unknown"

    suffix = " AED/year" if purpose == "rent" else " AED"
    return f"{number:,}{suffix}"


def metric_html(label, value):
    return f'<div class="metric"><span>{escape(label)}</span><strong>{escape(str(value or "Unknown"))}</strong></div>'


def match_prompt(
    text,
    selected_purpose="auto",
    selected_intent="auto",
    listing_scope="auto",
    listing_communities=None,
    market_scope="auto",
    market_communities=None,
    limit=DEFAULT_RESULT_LIMIT,
):
    enquiry = parse_prompt(
        text,
        selected_purpose,
        selected_intent,
        market_scope,
        market_communities,
        listing_scope,
        listing_communities,
    )
    matches_df, master_df, path = build_matches_dataframe(enquiry, limit)
    reality_df = build_budget_reality_primary_dataframe(enquiry, master_df, limit=limit)

    if not reality_df.empty:
        matches_df = reality_df

    over_budget_df = build_over_budget_dataframe(enquiry, master_df, matches_df, limit=OVER_BUDGET_LIMIT)
    fallback_df = build_budget_fallback_dataframe(enquiry, master_df, limit=OVER_BUDGET_LIMIT)

    return result_payload(enquiry, matches_df, master_df, path, over_budget_df=over_budget_df, fallback_df=fallback_df)


def normalize_quick_text(value):
    return str(value or "").strip()


def quick_int(value):
    number = clean_number(value)
    return int(number) if number is not None else None


def quick_money(value):
    text = normalize_quick_text(value)

    if not text:
        return None

    return parse_budget(text)


def quick_category_mask(df, category):
    category = normalize_quick_text(category).lower()

    if category not in {"villa", "townhouse"}:
        return pd.Series([True] * len(df), index=df.index)

    text = (
        df.get("url", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str)
        + " "
        + df.get("title", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str)
        + " "
        + df.get("detected_type_from_description", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str)
    ).str.lower()

    if category == "townhouse":
        return text.str.contains(r"town\s*house|townhouse", regex=True, na=False)

    return text.str.contains(r"\bvilla\b|villa-for-", regex=True, na=False)


def quick_listing_query(
    selected_purpose="sale",
    min_beds=None,
    max_beds=None,
    min_price=None,
    max_price=None,
    community="",
    category="any",
    limit=DEFAULT_RESULT_LIMIT,
):
    purpose = normalize_purpose(selected_purpose)

    if purpose not in {"sale", "rent"}:
        purpose = "sale"

    master_df, path = read_master(purpose)
    df = master_df.copy()
    price_column = "annual_rent" if purpose == "rent" else "price"
    bedroom_min = quick_int(min_beds)
    bedroom_max = quick_int(max_beds)
    price_min = quick_money(min_price)
    price_max = quick_money(max_price)
    community_text = normalize_quick_text(community)
    parsed_community = parse_community(community_text) or community_text

    if "bedrooms" in df.columns:
        bedrooms = pd.to_numeric(df["bedrooms"], errors="coerce")

        if bedroom_min is not None:
            df = df[bedrooms >= bedroom_min]
            bedrooms = bedrooms.loc[df.index]

        if bedroom_max is not None:
            df = df[bedrooms <= bedroom_max]
            bedrooms = bedrooms.loc[df.index]

    if price_column in df.columns:
        prices = df[price_column].apply(clean_number)

        if price_min is not None:
            df = df[prices >= price_min]
            prices = prices.loc[df.index]

        if price_max is not None:
            df = df[prices <= price_max]
            prices = prices.loc[df.index]

    if parsed_community and parsed_community.lower() not in {"any", "all"} and "predicted_community" in df.columns:
        if parsed_community == "Arabian Ranches 2":
            allowed = [community.lower() for community in MARKET_COMMUNITIES]
            df = df[df["predicted_community"].fillna("").astype(str).str.lower().isin(allowed)]
        else:
            df = df[df["predicted_community"].fillna("").astype(str).str.lower() == parsed_community.lower()]

    df = df[quick_category_mask(df, category)]

    if price_column in df.columns:
        df["_quick_price"] = df[price_column].apply(clean_number)
        df = df.sort_values(["_quick_price", "bedrooms"], ascending=[True, True], na_position="last")

    df = df.head(limit).copy()
    df["match_score"] = 100
    reasons = []

    if bedroom_min is not None or bedroom_max is not None:
        if bedroom_min == bedroom_max:
            reasons.append(f"{bedroom_min} bedrooms")
        elif bedroom_min is not None and bedroom_max is not None:
            reasons.append(f"{bedroom_min}-{bedroom_max} bedrooms")
        elif bedroom_min is not None:
            reasons.append(f"{bedroom_min}+ bedrooms")
        else:
            reasons.append(f"up to {bedroom_max} bedrooms")

    if price_min is not None or price_max is not None:
        if price_min is not None and price_max is not None:
            reasons.append(f"price {int(price_min):,}-{int(price_max):,}")
        elif price_max is not None:
            reasons.append(f"up to {int(price_max):,}")
        else:
            reasons.append(f"from {int(price_min):,}")

    if parsed_community:
        reasons.append(parsed_community)

    if category and category != "any":
        reasons.append(f"{category} stock")

    df["match_reasons"] = "; ".join(reasons) if reasons else "quick listing query"
    bedrooms_label = "Any"

    if bedroom_min == bedroom_max and bedroom_min is not None:
        bedrooms_label = str(bedroom_min)
    elif bedroom_min is not None and bedroom_max is not None:
        bedrooms_label = f"{bedroom_min}-{bedroom_max}"
    elif bedroom_min is not None:
        bedrooms_label = f"{bedroom_min}+"
    elif bedroom_max is not None:
        bedrooms_label = f"Up to {bedroom_max}"

    enquiry = {
        "purpose": purpose,
        "raw_prompt": "Quick query",
        "search_intent": "quick_query",
        "market_scope_mode": "auto",
        "market_communities": [],
        "listing_scope_mode": "auto",
        "listing_communities": [],
        "bedrooms": bedroom_min if bedroom_min == bedroom_max else None,
        "bedrooms_options": [],
        "bedrooms_label": bedrooms_label,
        "budget": price_max,
        "budget_floor": price_min,
        "stretch_budget": price_max,
        "community": parsed_community or "Any",
        "must_haves": [],
        "preferred_villa_types": [],
        "preferred_category": category if category in {"villa", "townhouse"} else "",
        "strict_category": bool(category in {"villa", "townhouse"}),
        "budget_reality_mode": False,
        "move_month": None,
    }
    result = result_payload(enquiry, df, master_df, path)
    result["report_title"] = "Quick Query Results"
    result["client_response"] = f"Quick query found {len(df)} listing(s) from {len(master_df)} {purpose} rows using direct filters only."
    return result


def build_matches_dataframe(enquiry, limit=DEFAULT_RESULT_LIMIT):
    master_df, path = read_master(enquiry["purpose"])
    search_df = filter_master_by_listing_scope(master_df, enquiry)
    bedroom_options = enquiry.get("bedrooms_options") or [None]
    frames = []

    for bedroom in bedroom_options:
        current_enquiry = dict(enquiry)
        current_enquiry["bedrooms"] = bedroom
        frames.append(match_enquiry(search_df, current_enquiry, limit=limit))

    matches_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if not matches_df.empty:
        sort_tiebreaker = "budget_distance" if enquiry["purpose"] == "sale" else "budget_gap"
        matches_df = matches_df.sort_values(
            ["match_score", sort_tiebreaker],
            ascending=[False, True],
        ).drop_duplicates(subset=["url"]).head(limit)

    return matches_df, master_df, path


def over_budget_ceiling(enquiry):
    budget = enquiry.get("budget")

    if not budget:
        return None

    ratio = SALE_OVER_BUDGET_RATIO if enquiry.get("purpose") == "sale" else RENT_OVER_BUDGET_RATIO
    return int(round(budget * ratio))


def build_over_budget_dataframe(enquiry, master_df, matches_df, limit=OVER_BUDGET_LIMIT):
    stretch_budget = enquiry.get("stretch_budget") or enquiry.get("budget")

    if not stretch_budget:
        return pd.DataFrame()

    bedroom_options = enquiry.get("bedrooms_options") or [enquiry.get("bedrooms")]
    frames = []

    for bedroom in bedroom_options:
        current_enquiry = dict(enquiry)
        current_enquiry["bedrooms"] = bedroom
        current_enquiry["allow_over_ceiling"] = True
        frames.append(match_enquiry(master_df, current_enquiry, limit=DEFAULT_RESULT_LIMIT))

    watchlist_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if watchlist_df.empty:
        return watchlist_df

    price_column = "annual_rent" if enquiry["purpose"] == "rent" else "price"
    watchlist_df["_price_number"] = watchlist_df[price_column].apply(clean_number)
    watchlist_df = watchlist_df[watchlist_df["_price_number"] > stretch_budget]
    ceiling = over_budget_ceiling(enquiry)

    if ceiling:
        watchlist_df = watchlist_df[watchlist_df["_price_number"] <= ceiling]

    if not matches_df.empty and "url" in matches_df.columns:
        watchlist_df = watchlist_df[~watchlist_df["url"].isin(matches_df["url"])]

    if watchlist_df.empty:
        return watchlist_df

    return (
        watchlist_df
        .sort_values(["match_score", "budget_gap"], ascending=[False, True])
        .drop_duplicates(subset=["url"])
        .head(limit)
        .drop(columns=["_price_number"], errors="ignore")
    )


def build_budget_reality_primary_dataframe(enquiry, master_df, limit=DEFAULT_AI_SHORTLIST_LIMIT):
    if not enquiry.get("budget_reality_mode") or not enquiry.get("preferred_category"):
        return pd.DataFrame()

    reality_enquiry = dict(enquiry)
    reality_enquiry["allow_over_ceiling"] = True
    reality_enquiry["strict_category"] = True
    reality_enquiry["budget_floor"] = None
    frames = []

    for bedroom in enquiry.get("bedrooms_options") or [enquiry.get("bedrooms")]:
        current_enquiry = dict(reality_enquiry)
        current_enquiry["bedrooms"] = bedroom
        frames.append(match_enquiry(master_df, current_enquiry, limit=DEFAULT_RESULT_LIMIT))

    reality_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if reality_df.empty:
        return reality_df

    price_column = "annual_rent" if enquiry["purpose"] == "rent" else "price"
    stretch_budget = enquiry.get("stretch_budget") or enquiry.get("budget")
    reality_df["_price_number"] = reality_df[price_column].apply(clean_number)

    if stretch_budget:
        reality_df = reality_df[reality_df["_price_number"] > stretch_budget]

    ceiling = over_budget_ceiling(enquiry)

    if ceiling:
        reality_df = reality_df[reality_df["_price_number"] <= ceiling]

    if reality_df.empty:
        return reality_df

    return (
        reality_df
        .sort_values(["budget_gap", "match_score"], ascending=[True, False])
        .drop_duplicates(subset=["url"])
        .head(limit)
        .drop(columns=["_price_number"], errors="ignore")
    )


def build_budget_fallback_dataframe(enquiry, master_df, limit=OVER_BUDGET_LIMIT):
    if not enquiry.get("budget_reality_mode") or enquiry.get("preferred_category") != "villa":
        return pd.DataFrame()

    budget = enquiry.get("budget")
    fallback_enquiry = dict(enquiry)
    fallback_enquiry["preferred_category"] = "townhouse"
    fallback_enquiry["strict_category"] = True
    fallback_enquiry["budget_reality_fallback"] = True
    fallback_enquiry["allow_over_ceiling"] = True
    frames = []

    for bedroom in enquiry.get("bedrooms_options") or [enquiry.get("bedrooms")]:
        current_enquiry = dict(fallback_enquiry)
        current_enquiry["bedrooms"] = bedroom
        frames.append(match_enquiry(master_df, current_enquiry, limit=max(DEFAULT_RESULT_LIMIT, 100)))

    fallback_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if fallback_df.empty:
        return fallback_df

    price_column = "annual_rent" if enquiry["purpose"] == "rent" else "price"
    fallback_df["_price_number"] = fallback_df[price_column].apply(clean_number)
    compromise_ceiling = fallback_compromise_ceiling(enquiry, master_df)

    if compromise_ceiling:
        fallback_df = fallback_df[fallback_df["_price_number"] <= compromise_ceiling]

    if fallback_df.empty:
        return fallback_df

    fallback_df["_budget_distance"] = (
        (fallback_df["_price_number"] - budget).abs()
        if budget else 0
    )
    fallback_df["_premium_band"] = fallback_df["_price_number"].apply(
        lambda price: premium_fallback_band(price, budget)
    )
    fallback_df["_premium_score"] = fallback_df.apply(
        lambda row: premium_townhouse_score(row, enquiry),
        axis=1,
    )

    return (
        fallback_df
        .sort_values(
            ["_premium_band", "_premium_score", "_price_number", "match_score", "_budget_distance"],
            ascending=[True, False, False, False, True],
        )
        .drop_duplicates(subset=["url"])
        .head(limit)
        .drop(columns=["_price_number", "_budget_distance", "_premium_band", "_premium_score"], errors="ignore")
    )


def premium_townhouse_score(row, enquiry):
    budget = enquiry.get("budget")
    price_column = "annual_rent" if enquiry["purpose"] == "rent" else "price"
    price = clean_number(row.get(price_column))
    size = clean_number(row.get("property_size_sqft"))
    plot = clean_number(row.get("plot_size_sqft"))
    text = " ".join(
        str(row.get(column) or "")
        for column in ["title", "description", "description_json", "predicted_type", "outdoor_matches"]
    ).lower()
    score = 0

    clue_scores = {
        "upgraded": 16,
        "renovated": 16,
        "fully furnished": 12,
        "furnished": 8,
        "appliances included": 10,
        "smart shutters": 10,
        "single row": 14,
        "corner": 14,
        "end unit": 14,
        "park backing": 14,
        "treelined backing": 12,
        "large plot": 12,
        "large garden": 12,
        "big garden": 12,
        "private garden": 10,
        "landscaped": 8,
        "vacant": 8,
        "ready to move": 8,
        "available now": 8,
        "close to pool": 6,
        "close to park": 6,
        "near pool": 6,
        "near park": 6,
        "by the amenities": 6,
        "premium location": 6,
        "great location": 5,
    }

    for clue, points in clue_scores.items():
        if clue in text:
            score += points

    if size:
        if size >= 2_000:
            score += 12
        elif size >= 1_900:
            score += 9
        elif size >= 1_800:
            score += 6
        elif size < 1_550:
            score -= 4

    if plot:
        if plot >= 2_000:
            score += 10
        elif plot >= 1_900:
            score += 7
        elif plot >= 1_800:
            score += 4

    if price and budget:
        ratio = price / budget

        if ratio > 1:
            score += 18
        elif ratio >= 0.95:
            score += 12
        elif ratio >= 0.9:
            score += 6
        elif ratio < 0.85:
            score -= 12

    return score


def premium_fallback_band(price, budget):
    if price is None or not budget:
        return 2

    if price > budget:
        return 0

    if price >= budget * 0.9:
        return 1

    return 2


def fallback_compromise_ceiling(enquiry, master_df):
    budget = enquiry.get("budget")

    if not budget:
        return None

    price_column = "annual_rent" if enquiry["purpose"] == "rent" else "price"
    reality_df = build_budget_reality_primary_dataframe(enquiry, master_df, limit=DEFAULT_RESULT_LIMIT)
    cheapest_primary = None

    if not reality_df.empty and price_column in reality_df.columns:
        primary_prices = reality_df[price_column].apply(clean_number).dropna()

        if not primary_prices.empty:
            cheapest_primary = primary_prices.min()

    ratio = 1.15 if enquiry["purpose"] == "rent" else 1.08
    budget_ceiling = budget * ratio

    if cheapest_primary:
        return min(cheapest_primary - 1, budget_ceiling)

    return budget_ceiling


def rows_payload(matches_df, price_column):
    columns = [
        "ai_rank",
        "ai_score",
        "ai_fit_summary",
        "ai_opportunity_angle",
        "ai_strengths",
        "ai_concerns",
        "ai_verify",
        "match_score",
        price_column,
        "budget_gap",
        "bedrooms",
        "bathrooms",
        "property_size_sqft",
        "predicted_community",
        "predicted_type",
        "outdoor_matches",
        "match_reasons",
        "title",
        "description",
        "description_json",
        "url",
    ]
    existing_columns = [column for column in columns if column in matches_df.columns]
    rows = []

    for row in matches_df[existing_columns].to_dict("records") if existing_columns else []:
        exclusive_text = " ".join([
            str(row.get("title") or ""),
            str(row.get("description") or ""),
            str(row.get("description_json") or ""),
        ])
        item = {key: clean_value(value) for key, value in row.items()}
        item.pop("description", None)
        item.pop("description_json", None)
        item["has_exclusive_warning"] = has_exclusive_warning(exclusive_text)
        item["price"] = clean_number(item.get(price_column))
        rows.append(item)

    return rows


def has_exclusive_warning(value):
    return "exclusive" in str(value or "").lower()


def duplicate_text_tokens(value):
    text = str(value or "").lower()
    return {
        token
        for token in [
            "single row",
            "vacant soon",
            "vacant",
            "vot",
            "owner occupied",
            "ready to move",
            "large layout",
            "large plot",
            "corner",
            "upgraded",
            "landscaped",
            "type 1",
            "type 2",
            "type 3",
        ]
        if token in text
    }


def likely_duplicate_group_key(item):
    price = clean_number(item.get("price"))
    bedrooms = clean_number(item.get("bedrooms"))
    community = str(item.get("predicted_community") or "").strip().lower()
    property_size = clean_number(item.get("property_size_sqft"))

    if not price or not bedrooms or not community:
        return None

    rounded_price = round(price / 50_000) * 50_000
    rounded_size = round(property_size / 100) * 100 if property_size else ""
    return (community, bedrooms, rounded_price, rounded_size)


def add_similar_listing_warnings(items):
    groups = []

    for item in items:
        key = likely_duplicate_group_key(item)
        tokens = duplicate_text_tokens(" ".join([
            str(item.get("title") or ""),
            str(item.get("predicted_type") or ""),
            str(item.get("outdoor_matches") or ""),
        ]))
        matched_group = None

        for group in groups:
            if key and group["key"] == key:
                matched_group = group
                break

            if key and group["key"] and key[:3] == group["key"][:3] and tokens and len(tokens & group["tokens"]) >= 2:
                matched_group = group
                break

        if matched_group:
            matched_group["items"].append(item)
            matched_group["tokens"].update(tokens)
        else:
            groups.append({
                "key": key,
                "tokens": set(tokens),
                "items": [item],
            })

    similar_urls_by_url = {}

    for group in groups:
        urls = [
            item.get("url")
            for item in group["items"]
            if item.get("url")
        ]

        for url in urls:
            similar_urls_by_url[url] = urls

    warned_items = []

    for item in items:
        item = item.copy()
        urls = similar_urls_by_url.get(item.get("url"), [])
        item["similar_count"] = len(urls)
        item["similar_urls"] = urls
        warned_items.append(item)

    return warned_items


def result_payload(
    enquiry,
    matches_df,
    master_df,
    path,
    ai_result=None,
    over_budget_df=None,
    fallback_df=None,
):
    response_enquiry = dict(enquiry)
    response_enquiry["bedrooms"] = enquiry["bedrooms"]
    client_response = ai_result.get("client_response") if ai_result else build_client_response(matches_df, response_enquiry)
    price_column = "annual_rent" if enquiry["purpose"] == "rent" else "price"

    payload = {
        "master_file": str(path),
        "rows_searched": int(len(master_df)),
        "enquiry": enquiry,
        "client_response": client_response,
        "matches": add_similar_listing_warnings(rows_payload(matches_df, price_column)),
        "over_budget_matches": add_similar_listing_warnings(rows_payload(over_budget_df, price_column)) if over_budget_df is not None else [],
        "fallback_matches": add_similar_listing_warnings(rows_payload(fallback_df, price_column)) if fallback_df is not None else [],
    }

    if ai_result:
        payload["ai"] = ai_result

    return payload


def ai_fallback_prompt(
    text,
    selected_purpose="auto",
    api_key=None,
    limit=DEFAULT_AI_RESULT_LIMIT,
    skip_final_report=False,
    ranked_urls=None,
    listing_scope="auto",
    listing_communities=None,
    market_scope="auto",
    market_communities=None,
):
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    enquiry = parse_prompt(text, selected_purpose, "auto", market_scope, market_communities, listing_scope, listing_communities)
    master_df, path = read_master(enquiry["purpose"])
    fallback_df = build_budget_fallback_dataframe(enquiry, master_df, limit=max(limit, DEFAULT_AI_SHORTLIST_LIMIT))

    if fallback_df.empty:
        raise RuntimeError("No fallback options were found for this brief. Run a budget-reality villa enquiry with townhouse fallback first.")

    if ranked_urls:
        order = {url: index for index, url in enumerate(ranked_urls)}
        fallback_df = fallback_df[fallback_df["url"].isin(order)].copy()

        if fallback_df.empty:
            raise RuntimeError("The previous fallback shortlist is no longer available. Run Analyse fallback again.")

        fallback_df["_ranked_order"] = fallback_df["url"].map(order)
        fallback_df = fallback_df.sort_values("_ranked_order").drop(columns=["_ranked_order"])

    fallback_enquiry = dict(enquiry)
    fallback_enquiry["preferred_category"] = "townhouse"
    fallback_enquiry["strict_category"] = True
    fallback_enquiry["analysis_focus"] = (
        "Analyse only the fallback townhouse options. Rank the strongest premium compromise first, "
        "then separate stronger premium choices from cheaper budget-saving alternatives. Compare upgrade clues, "
        "single-row/corner/end-unit position, large plot/garden, vacancy, family usability, and value against recent rental transactions. "
        "Explain whether each fallback is a real compromise for a villa client or merely a cheaper townhouse."
    )

    ai_result = rank_matches_with_ai(
        fallback_df,
        fallback_enquiry,
        model="gpt-5-mini",
        description_chars=AI_DESCRIPTION_CHARS,
        api_key=api_key,
        market_context=build_market_context(enquiry, fallback_df),
        batch_size=DEFAULT_AI_BATCH_SIZE,
        final_candidate_limit=DEFAULT_AI_FINAL_CANDIDATE_LIMIT,
        skip_final_report=skip_final_report,
    )
    enriched_df = merge_ai_rankings(fallback_df, ai_result).head(limit)
    result = result_payload(
        fallback_enquiry,
        enriched_df,
        master_df,
        path,
        ai_result=ai_result,
    )
    result["report_title"] = "Analysed Fallback Options"

    if skip_final_report:
        result["report_title"] = "Analysed Fallback Options Ranking"
        result["rank_context"] = {
            "scenario": "fallback",
            "ranked_urls": [
                url
                for url in enriched_df["url"].head(limit).tolist()
                if url
            ],
        }

    return result


def ai_scenario_prompt(text, scenario, selected_purpose="auto", api_key=None, limit=DEFAULT_AI_RESULT_LIMIT, listing_scope="auto", listing_communities=None, market_scope="auto", market_communities=None):
    return ai_scenario_result(
        text,
        scenario,
        selected_purpose=selected_purpose,
        api_key=api_key,
        limit=limit,
        listing_scope=listing_scope,
        listing_communities=listing_communities,
        market_scope=market_scope,
        market_communities=market_communities,
        skip_final_report=False,
    )


def ai_scenario_rank_prompt(text, scenario, selected_purpose="auto", api_key=None, limit=DEFAULT_AI_RESULT_LIMIT, listing_scope="auto", listing_communities=None, market_scope="auto", market_communities=None):
    return ai_scenario_result(
        text,
        scenario,
        selected_purpose=selected_purpose,
        api_key=api_key,
        limit=limit,
        listing_scope=listing_scope,
        listing_communities=listing_communities,
        market_scope=market_scope,
        market_communities=market_communities,
        skip_final_report=True,
    )


def ai_scenario_report_prompt(text, scenario, ranked_urls=None, selected_purpose="auto", api_key=None, limit=DEFAULT_AI_RESULT_LIMIT, listing_scope="auto", listing_communities=None, market_scope="auto", market_communities=None):
    return ai_scenario_result(
        text,
        scenario,
        selected_purpose=selected_purpose,
        api_key=api_key,
        limit=min(limit, 6),
        ranked_urls=ranked_urls or [],
        listing_scope=listing_scope,
        listing_communities=listing_communities,
        market_scope=market_scope,
        market_communities=market_communities,
        skip_final_report=False,
    )


def ai_scenario_result(
    text,
    scenario,
    selected_purpose="auto",
    api_key=None,
    limit=DEFAULT_AI_RESULT_LIMIT,
    ranked_urls=None,
    listing_scope="auto",
    listing_communities=None,
    market_scope="auto",
    market_communities=None,
    skip_final_report=False,
):
    if scenario == "fallback":
        if skip_final_report:
            return ai_fallback_prompt(text, selected_purpose=selected_purpose, api_key=api_key, limit=limit, skip_final_report=True, ranked_urls=ranked_urls, listing_scope=listing_scope, listing_communities=listing_communities, market_scope=market_scope, market_communities=market_communities)
        return ai_fallback_prompt(text, selected_purpose=selected_purpose, api_key=api_key, limit=limit, ranked_urls=ranked_urls, listing_scope=listing_scope, listing_communities=listing_communities, market_scope=market_scope, market_communities=market_communities)

    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    scenario_config = SCENARIOS.get(scenario)

    if not scenario_config:
        raise RuntimeError(f"Unknown scenario: {scenario}")

    scenario_intent = scenario if scenario in {"best_value", "negotiation", "listing_opportunity", "upgrade_potential", "move_in_ready"} else "auto"
    enquiry = parse_prompt(text, selected_purpose, scenario_intent, market_scope, market_communities, listing_scope, listing_communities)

    if scenario == "budget_reality":
        enquiry["budget_reality_mode"] = True

    enquiry["analysis_focus"] = scenario_config["focus"]
    shortlist_limit = max(limit, DEFAULT_AI_SHORTLIST_LIMIT)
    matches_df, master_df, path = build_matches_dataframe(dict(enquiry), shortlist_limit)

    if scenario == "budget_reality" or enquiry.get("budget_reality_mode"):
        reality_df = build_budget_reality_primary_dataframe(enquiry, master_df, limit=shortlist_limit)

        if not reality_df.empty:
            matches_df = reality_df

    if matches_df.empty:
        raise RuntimeError("No suitable rows were found for this scenario.")

    if ranked_urls:
        order = {url: index for index, url in enumerate(ranked_urls)}
        matches_df = matches_df[matches_df["url"].isin(order)].copy()

        if matches_df.empty:
            raise RuntimeError("The previous ranked shortlist is no longer available. Run the scenario rank again.")

        matches_df["_ranked_order"] = matches_df["url"].map(order)
        matches_df = matches_df.sort_values("_ranked_order").drop(columns=["_ranked_order"])

    ai_result = rank_matches_with_ai(
        matches_df,
        enquiry,
        model="gpt-5-mini",
        description_chars=AI_DESCRIPTION_CHARS,
        api_key=api_key,
        market_context=build_market_context(enquiry, matches_df),
        batch_size=DEFAULT_AI_BATCH_SIZE,
        final_candidate_limit=DEFAULT_AI_FINAL_CANDIDATE_LIMIT,
        skip_final_report=skip_final_report,
    )
    enriched_df = merge_ai_rankings(matches_df, ai_result).head(limit)
    over_budget_df = build_over_budget_dataframe(enquiry, master_df, enriched_df, limit=OVER_BUDGET_LIMIT)
    fallback_df = build_budget_fallback_dataframe(enquiry, master_df, limit=OVER_BUDGET_LIMIT)
    result = result_payload(
        enquiry,
        enriched_df,
        master_df,
        path,
        ai_result=ai_result,
        over_budget_df=over_budget_df,
        fallback_df=fallback_df,
    )
    result["report_title"] = scenario_config["report_title"]

    if skip_final_report:
        result["report_title"] = f"{scenario_config['report_title']} Ranking"
        result["rank_context"] = {
            "scenario": scenario,
            "ranked_urls": [
                url
                for url in enriched_df["url"].head(limit).tolist()
                if url
            ],
        }

    return result


def ai_feedback_prompt(text, selected_purpose="auto", selected_intent="auto", listing_scope="auto", listing_communities=None, market_scope="auto", market_communities=None, api_key=None, limit=DEFAULT_AI_RESULT_LIMIT):
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    enquiry = parse_prompt(text, selected_purpose, selected_intent, market_scope, market_communities, listing_scope, listing_communities)
    shortlist_limit = max(limit, DEFAULT_AI_SHORTLIST_LIMIT)
    matches_df, master_df, path = build_matches_dataframe(dict(enquiry), shortlist_limit)
    reality_df = build_budget_reality_primary_dataframe(enquiry, master_df, limit=shortlist_limit)

    if not reality_df.empty:
        matches_df = reality_df

    ai_result = rank_matches_with_ai(
        matches_df,
        enquiry,
        model="gpt-5-mini",
        description_chars=AI_DESCRIPTION_CHARS,
        api_key=api_key,
        market_context=build_market_context(enquiry, matches_df),
        batch_size=DEFAULT_AI_BATCH_SIZE,
        final_candidate_limit=DEFAULT_AI_FINAL_CANDIDATE_LIMIT,
    )
    enriched_df = merge_ai_rankings(matches_df, ai_result).head(limit)

    over_budget_df = build_over_budget_dataframe(enquiry, master_df, enriched_df, limit=OVER_BUDGET_LIMIT)
    fallback_df = build_budget_fallback_dataframe(enquiry, master_df, limit=OVER_BUDGET_LIMIT)

    return result_payload(
        enquiry,
        enriched_df,
        master_df,
        path,
        ai_result=ai_result,
        over_budget_df=over_budget_df,
        fallback_df=fallback_df,
    )


def check_openai_key(api_key):
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is not installed. Run: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=api_key, timeout=20.0, max_retries=0)
    response = client.responses.create(
        model="gpt-5-mini",
        instructions="You are checking whether this OpenAI API key can make a basic response.",
        input="Reply with OK only.",
        max_output_tokens=16,
    )

    return {
        "ok": True,
        "message": "OpenAI connection is ready. You can now use AI feedback.",
    }

