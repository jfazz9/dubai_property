import pandas as pd

from .constants import (
    MARKET_COMMUNITIES,
    MARKET_CONTEXT_TRANSACTION_LIMIT,
    MARKET_RENTALS_FILE,
    MARKET_SALES_FILE,
    SIMILAR_MARKET_GROUPS,
    TOWNHOUSE_COMMUNITIES,
    VILLA_COMMUNITIES,
)
from .data_loader import clean_market_number, load_market_rentals, load_market_sales
from .owner_lookup import clean_value
from .prompt_parser import normalize_market_communities, normalize_market_scope


def compact_market_row(row):
    return {
        "community": clean_value(row.get("community")),
        "predicted_type": clean_value(row.get("predicted_type")),
        "prediction_confidence": clean_market_number(row.get("prediction_confidence")),
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
        "predicted_type": clean_value(row.get("predicted_type")),
        "prediction_confidence": clean_market_number(row.get("prediction_confidence")),
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
        return similar_market_communities_for(prompt_community), "auto_similar"

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

    # Filter by predicted_type when the market data has been enriched and the
    # enquiry specifies a particular villa type (e.g. "Type 3")
    villa_types = enquiry.get("preferred_villa_types") or enquiry.get("villa_types") or []
    if villa_types and "predicted_type" in scoped.columns:
        bare = (
            scoped["predicted_type"].fillna("")
            .str.strip()
            .str.replace(r"^(Likely|Possible)\s+", "", regex=True)
        )
        by_type = scoped[bare.isin(villa_types)]
        if not by_type.empty:
            scoped = by_type

    # Exclude townhouse-only communities (Camelia, Reem) when the enquiry is
    # for a villa or a villa community — their transactions are not comparable.
    preferred_category = enquiry.get("preferred_category", "")
    is_villa_search = (
        preferred_category == "villa"
        or (community and community in VILLA_COMMUNITIES)
    )
    if is_villa_search and "community" in scoped.columns:
        # Use startswith to catch "Camelia 1", "Camelia 2", "Reem Community" etc.
        is_townhouse = scoped["community"].str.strip().apply(
            lambda loc: any(str(loc).startswith(c) for c in TOWNHOUSE_COMMUNITIES)
        )
        scoped = scoped[~is_townhouse]

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

    # Filter by predicted_type when the market data has been enriched and the
    # enquiry specifies a particular villa type (e.g. "Type 3")
    villa_types = enquiry.get("preferred_villa_types") or enquiry.get("villa_types") or []
    if villa_types and "predicted_type" in scoped.columns:
        bare = (
            scoped["predicted_type"].fillna("")
            .str.strip()
            .str.replace(r"^(Likely|Possible)\s+", "", regex=True)
        )
        by_type = scoped[bare.isin(villa_types)]
        if not by_type.empty:
            scoped = by_type

    # Exclude townhouse-only communities (Camelia, Reem) when the enquiry is
    # for a villa or a villa community — their transactions are not comparable.
    preferred_category = enquiry.get("preferred_category", "")
    is_villa_search = (
        preferred_category == "villa"
        or (community and community in VILLA_COMMUNITIES)
    )
    if is_villa_search and "Location" in scoped.columns:
        # Use startswith to catch "Camelia 1", "Camelia 2", "Reem Community" etc.
        is_townhouse = scoped["Location"].str.strip().apply(
            lambda loc: any(str(loc).startswith(c) for c in TOWNHOUSE_COMMUNITIES)
        )
        scoped = scoped[~is_townhouse]

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
