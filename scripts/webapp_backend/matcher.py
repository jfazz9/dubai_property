import sys
from html import escape

import pandas as pd

from enquiry_matcher import clean_number, match_enquiry, parse_budget
from workflow_paths import normalize_purpose

from .constants import (
    DEFAULT_RESULT_LIMIT,
    DEFAULT_AI_SHORTLIST_LIMIT,
    MARKET_COMMUNITIES,
    OVER_BUDGET_LIMIT,
    RENT_OVER_BUDGET_RATIO,
    SALE_OVER_BUDGET_RATIO,
)
from .market_context import filter_master_by_listing_scope
from .prompt_parser import parse_community, parse_prompt
from .result_builder import result_payload


def _read_master(purpose):
    """Look up read_master through the package namespace so monkeypatching works."""
    pkg = sys.modules.get("webapp_backend") or sys.modules.get("scripts.webapp_backend")
    if pkg is not None and hasattr(pkg, "read_master"):
        return pkg.read_master(purpose)
    from .data_loader import read_master
    return read_master(purpose)


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

    master_df, path = _read_master(purpose)
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
    master_df, path = _read_master(enquiry["purpose"])
    search_df = filter_master_by_listing_scope(master_df, enquiry)
    bedroom_options = enquiry.get("bedrooms_options") or [None]
    frames = []

    for bedroom in bedroom_options:
        current_enquiry = dict(enquiry)
        current_enquiry["bedrooms"] = bedroom
        frames.append(match_enquiry(search_df, current_enquiry, limit=limit))

    matches_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if not matches_df.empty:
        matches_df = matches_df.sort_values(
            ["match_score", "budget_distance"],
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
