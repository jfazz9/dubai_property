import json
import re
from pathlib import Path

import pandas as pd

from enquiry_matcher import clean_number
from workflow_paths import normalize_purpose

from .constants import CONDITION_FEATURES, VILLA_TYPE_REFERENCE_FILE
from .data_loader import clean_market_number, load_market_sales, read_master
from .market_context import compact_market_row
from .owner_lookup import clean_value
from .prompt_parser import (
    parse_bedroom_options,
    parse_communities_from_text,
    parse_community,
)


def load_villa_type_reference(path=VILLA_TYPE_REFERENCE_FILE):
    """Load the AR2 community+type reference CSV with BUA and plot min/max ranges."""
    ref_path = Path(path)
    if not ref_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(ref_path)
    for col in ["bua_ref_sqft", "bua_min_sqft", "bua_max_sqft",
                "plot_ref_sqft", "plot_min_sqft", "plot_max_sqft",
                "bedrooms", "bathrooms"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def lookup_type_reference(reference_df, community, villa_type):
    """Return the reference row dict for a specific community+type, or None.

    Where a type has both a villa and townhouse row (e.g. Lila Type 3),
    the villa row is preferred.
    """
    if reference_df.empty or not community or not villa_type:
        return None
    mask = (
        reference_df["community"].fillna("").str.strip().str.lower() == community.lower()
    ) & (
        reference_df["type"].fillna("").str.strip() == villa_type
    )
    matching = reference_df[mask]
    if matching.empty:
        return None
    # Prefer villa over townhouse when there are duplicate rows for the same type
    if "property_category" in matching.columns and len(matching) > 1:
        villa_rows = matching[matching["property_category"].str.lower() == "villa"]
        if not villa_rows.empty:
            matching = villa_rows
    return matching.iloc[0].to_dict()


def parse_villa_type_from_text(text):
    """Extract a villa type label like 'Type 3' from free text."""
    normalized = text.lower()
    match = re.search(r"\btype\s*(\d+[a-z]?)\b", normalized)
    return f"Type {match.group(1).upper()}" if match else None


def parse_condition_features(text):
    """Extract condition / feature keywords that affect valuation."""
    normalized = text.lower()
    seen = set()
    features = []
    for keyword, label in CONDITION_FEATURES:
        if keyword in normalized and label not in seen:
            seen.add(label)
            features.append(label)
    return features


def valuation_estimate(text, selected_purpose="sale", api_key=None, extra_communities=None):
    """Generate a property valuation estimate from a natural language description.

    Community + type are treated as an inseparable pair — a Type 2 in Samara is
    an entirely different product from a Type 2 in Casa or Rosa. The function
    filters by community AND type together.

    Multiple communities can be supplied either by mentioning them in the prompt text
    (e.g. "Rosa and Rasha Type 3") or via extra_communities (the webapp scope selector).
    All mentioned communities are used for comp filtering; the first one is the primary.
    """
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    purpose = normalize_purpose(selected_purpose) if selected_purpose not in ("auto", "") else "sale"

    # Parse all specific communities mentioned in the prompt.
    # extra_communities adds any that were selected via the webapp scope selector.
    communities_in_text = parse_communities_from_text(text)
    extra = [c for c in (extra_communities or []) if c not in communities_in_text]
    all_communities = communities_in_text + extra

    # Primary community: first mentioned, used for reference lookup and display.
    community = all_communities[0] if all_communities else parse_community(text)

    bedrooms_list = parse_bedroom_options(text)
    beds = bedrooms_list[0] if bedrooms_list else None
    villa_type = parse_villa_type_from_text(text)
    features = parse_condition_features(text)

    # Load master CSV
    master_df, path = read_master(purpose)

    for col in ["price", "price_per_sqft", "property_size_sqft", "plot_size_sqft", "bedrooms", "annual_rent"]:
        if col in master_df.columns:
            master_df[col] = pd.to_numeric(master_df[col], errors="coerce")

    # Keep only active listings
    if "is_active" in master_df.columns:
        from check_active_listings import is_active_value
        active_mask = master_df["is_active"].apply(is_active_value)
        comp_df = master_df[active_mask].copy()
    else:
        comp_df = master_df.copy()

    price_col = "annual_rent" if purpose == "rent" else "price"

    # Load the authoritative community+type reference
    type_reference_df = load_villa_type_reference()
    type_ref = lookup_type_reference(type_reference_df, community, villa_type)

    def _col_match(df, col, val):
        """Filter df by exact string match on col; return original df if result empty."""
        if not val or col not in df.columns:
            return df
        result = df[df[col].fillna("").astype(str).str.strip() == str(val).strip()]
        return result if not result.empty else df

    # --- Community + type are an inseparable pair ----------------------------
    # A "Type 2" in Samara is a completely different villa from a "Type 2" in
    # Casa, Rosa, or Palma — different BUA, different plot, different layout.
    # Never filter on type alone across multiple communities unless the user has
    # explicitly named those communities.

    community_type_matched = pd.DataFrame()
    community_only_matched = pd.DataFrame()
    cross_community_type_matched = pd.DataFrame()

    # Strip confidence prefixes ("Likely ", "Possible ") from predicted_type so we
    # match "Type 3", "Likely Type 3", and "Possible Type 3" all as the same type.
    def _bare_type(series):
        return (
            series.fillna("")
            .str.strip()
            .str.replace(r"^(Likely|Possible)\s+", "", regex=True)
        )

    has_pred_community = "predicted_community" in comp_df.columns
    has_pred_type = "predicted_type" in comp_df.columns

    # Use all mentioned communities — any community the user named counts.
    # This lets "Rosa and Rasha Type 3" pull comps from both.
    if all_communities and villa_type and has_pred_community and has_pred_type:
        community_type_matched = comp_df[
            comp_df["predicted_community"].fillna("").str.strip().isin(all_communities) &
            (_bare_type(comp_df["predicted_type"]) == villa_type)
        ]

    if all_communities and has_pred_community:
        community_only_matched = comp_df[
            comp_df["predicted_community"].fillna("").str.strip().isin(all_communities)
        ]

    if villa_type and has_pred_type:
        cross_community_type_matched = comp_df[_bare_type(comp_df["predicted_type"]) == villa_type]

    # Which communities in all_communities actually have this type in the data?
    type_available_in = []
    if villa_type and has_pred_community and has_pred_type:
        matched_comms = comp_df[_bare_type(comp_df["predicted_type"]) == villa_type]["predicted_community"].dropna().unique()
        type_available_in = [c for c in matched_comms if c != "Arabian Ranches 2"]

    # Community label for display
    if len(all_communities) > 1:
        community_label = " / ".join(all_communities)
    else:
        community_label = community or "AR2"

    # Pick the tightest match set with a meaningful sample
    if not community_type_matched.empty:
        comp_set = community_type_matched
        match_basis = f"{community_label} {villa_type} active listings"
        cross_community_warning = None
    elif not community_only_matched.empty and all_communities:
        comp_set = community_only_matched
        type_hint = (
            f" Found in: {', '.join(type_available_in[:5])}." if type_available_in else ""
        )
        match_basis = f"{community_label} active listings (no {villa_type} listings yet — using all types in {community_label})"
        cross_community_warning = (
            f"No '{villa_type}' listings found in {community_label}."
            f"{type_hint}"
            f" Tip: add one of those communities to your prompt to pull better comps."
            if type_available_in else
            f"No '{villa_type}' listings found in {community_label}. Comps are all types within {community_label}."
        )
    elif not cross_community_type_matched.empty and villa_type and not all_communities:
        # Last resort when no community was specified at all
        comp_set = cross_community_type_matched
        match_basis = f"AR2 {villa_type} listings across all communities (no community specified)"
        cross_community_warning = (
            f"No community specified. Using {villa_type} listings across ALL communities. "
            f"Villa types differ significantly between communities — add a community name for a better estimate."
        )
    else:
        comp_set = comp_df
        match_basis = "All AR2 active listings (no community or type match)"
        cross_community_warning = "No community or type match found. Using all AR2 listings — estimate confidence will be very low."

    # Filter by bedrooms (soft — only apply if it doesn't wipe out comps)
    if beds and "bedrooms" in comp_set.columns:
        bed_filtered = comp_set[comp_set["bedrooms"] == beds]
        if not bed_filtered.empty:
            comp_set = bed_filtered

    # --- Statistics -----------------------------------------------------------
    def _stats(series):
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return {}
        return {"count": int(len(s)), "min": int(s.min()), "median": int(s.median()), "max": int(s.max())}

    price_stats = _stats(comp_set[price_col]) if price_col in comp_set.columns else {}
    ppsf_stats = _stats(comp_set["price_per_sqft"]) if "price_per_sqft" in comp_set.columns and purpose == "sale" else {}
    plot_stats = _stats(comp_set["plot_size_sqft"]) if "plot_size_sqft" in comp_set.columns else {}
    bua_stats = _stats(comp_set["property_size_sqft"]) if "property_size_sqft" in comp_set.columns else {}

    # --- Extension detection using the authoritative reference file -----------
    # bua_max_sqft from the reference is the ceiling for a standard (unextended)
    # unit of this community+type. Any listing with BUA above that is extended.
    extension_evidence = []

    bua_max = clean_market_number(type_ref.get("bua_max_sqft")) if type_ref else None

    if bua_max and "property_size_sqft" in comp_set.columns:
        ext_df = comp_set[comp_set["property_size_sqft"] > bua_max].copy()
        if not ext_df.empty:
            for _, row in ext_df.sort_values("property_size_sqft", ascending=False).head(6).iterrows():
                extension_evidence.append({
                    "bua": clean_market_number(row.get("property_size_sqft")),
                    "plot": clean_market_number(row.get("plot_size_sqft")),
                    "price": clean_market_number(row.get(price_col)),
                    "price_per_sqft": clean_market_number(row.get("price_per_sqft")) if purpose == "sale" else None,
                })

    # --- Sample comparables near the median (for AI context) -----------------
    sample_comps = []
    if not comp_set.empty and price_col in comp_set.columns:
        med = comp_set[price_col].median()
        ranked = comp_set.copy()
        ranked["_pdist"] = (ranked[price_col] - med).abs()
        for _, row in ranked.sort_values("_pdist").head(10).iterrows():
            sample_comps.append({
                "community": clean_value(row.get("predicted_community")),
                "type": clean_value(row.get("predicted_type")),
                "beds": clean_market_number(row.get("bedrooms")),
                "bua_sqft": clean_market_number(row.get("property_size_sqft")),
                "plot_sqft": clean_market_number(row.get("plot_size_sqft")),
                "price": clean_market_number(row.get(price_col)),
                "price_per_sqft": clean_market_number(row.get("price_per_sqft")) if purpose == "sale" else None,
            })

    # --- Recent market transaction context (sale only) -----------------------
    market_txn_context = {}
    if purpose == "sale":
        market_df = load_market_sales()
        if not market_df.empty:
            scoped = market_df.copy()

            # Filter by community first (exact match, case-insensitive)
            if all_communities and "community" in scoped.columns:
                comm_rows = scoped[scoped["community"].str.strip().isin(all_communities)]
                if not comm_rows.empty:
                    scoped = comm_rows
            elif community and "community" in scoped.columns:
                comm_rows = scoped[scoped["community"].str.lower() == community.lower()]
                if not comm_rows.empty:
                    scoped = comm_rows

            # Filter by predicted_type if the market data has been enriched —
            # strip confidence prefixes so "Likely Type 3" matches "Type 3"
            if villa_type and "predicted_type" in scoped.columns:
                bare = (
                    scoped["predicted_type"].fillna("")
                    .str.strip()
                    .str.replace(r"^(Likely|Possible)\s+", "", regex=True)
                )
                type_rows = scoped[bare == villa_type]
                if not type_rows.empty:
                    scoped = type_rows

            # Soft bed filter as a final narrowing step
            if beds and "beds" in scoped.columns:
                bed_rows = scoped[scoped["beds"] == beds]
                if not bed_rows.empty:
                    scoped = bed_rows

            if "_sold_date" in scoped.columns:
                scoped = scoped.sort_values("_sold_date", ascending=False, na_position="last")

            market_txn_context = {
                "recent_transactions": [compact_market_row(r) for _, r in scoped.head(8).iterrows()],
                "price_stats": _stats(scoped["price"]) if "price" in scoped.columns else {},
                "ppsf_stats": _stats(scoped["price_per_sqft"]) if "price_per_sqft" in scoped.columns else {},
            }

    # --- Build the payload for OpenAI ----------------------------------------
    context = {
        "property_description": text,
        "parsed": {
            "community": community or "Not specified",
            "villa_type": villa_type or "Not specified",
            "bedrooms": beds or "Not specified",
            "detected_features": features,
            "purpose": purpose,
        },
        "match_basis": match_basis,
        "cross_community_warning": cross_community_warning,
        "active_listing_stats": {
            "comparable_count": price_stats.get("count", 0),
            price_col: price_stats,
            "price_per_sqft": ppsf_stats,
            "plot_size_sqft": plot_stats,
            "bua_sqft": bua_stats,
        },
        "villa_type_reference": {
            "community": community,
            "type": villa_type,
            "bedrooms": clean_market_number(type_ref.get("bedrooms")) if type_ref else None,
            "bathrooms": clean_market_number(type_ref.get("bathrooms")) if type_ref else None,
            "bua_ref_sqft": clean_market_number(type_ref.get("bua_ref_sqft")) if type_ref else None,
            "bua_min_sqft": clean_market_number(type_ref.get("bua_min_sqft")) if type_ref else None,
            "bua_max_sqft": clean_market_number(type_ref.get("bua_max_sqft")) if type_ref else None,
            "plot_ref_sqft": clean_market_number(type_ref.get("plot_ref_sqft")) if type_ref else None,
            "plot_min_sqft": clean_market_number(type_ref.get("plot_min_sqft")) if type_ref else None,
            "plot_max_sqft": clean_market_number(type_ref.get("plot_max_sqft")) if type_ref else None,
            "reference_found": type_ref is not None,
            "note": (
                f"BUA above {bua_max:,} sqft indicates an extension for {community} {villa_type}. "
                f"Plot ranges from {clean_market_number(type_ref.get('plot_min_sqft')):,} to "
                f"{clean_market_number(type_ref.get('plot_max_sqft')):,} sqft — "
                f"position within this range is a key price differentiator."
            ) if type_ref and bua_max and type_ref.get("plot_min_sqft") and type_ref.get("plot_max_sqft") else
            "No reference data found for this community+type combination.",
        },
        "extension_evidence_in_comps": extension_evidence,
        "sample_comparables": sample_comps,
        "market_transaction_context": market_txn_context,
    }

    # --- Call OpenAI ---------------------------------------------------------
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package not installed. Run: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=api_key, timeout=60.0)

    if purpose == "rent":
        system_prompt = """You are a specialist Dubai rental valuation analyst for Arabian Ranches 2 (AR2) villas.

Your task: given a property description and comparable active rental listing data, produce a realistic annual rental value estimate for today.

Critical AR2 rental valuation rules:
- Each community has its own villa type definitions. A "Type 2" in one community is a completely different product from a "Type 2" in another — different BUA, plot, and rental demand. NEVER compare types across communities.
- The villa_type_reference block contains authoritative BUA and plot ranges for this community+type. Use these as your anchor.
- BUA above bua_max_sqft indicates an extension — commands a rental premium.
- Condition/feature premiums (private pool, fully upgraded, furnished, excellent finishes, corner plot) meaningfully affect achievable rent.
- Furnished properties command a significant premium over unfurnished.
- Vacant/ready-to-move properties are more lettable and can achieve slightly higher asking rent.
- Anchor to the comparable annual rent median and adjust logically. Do not extrapolate wildly.
- All values are annual rent in AED.

Output ONLY valid JSON in this exact structure, no markdown fences:
{
  "low": <integer AED per year>,
  "mid": <integer AED per year>,
  "high": <integer AED per year>,
  "currency": "AED/yr",
  "confidence": "low|medium|high",
  "rationale": {
    "low": "<brief reason for low end>",
    "mid": "<brief reason for mid — anchor point>",
    "high": "<brief reason for high end>"
  },
  "premium_factors": ["<feature adding rental value>"],
  "discount_factors": ["<feature reducing rental value or risk>"],
  "key_risks": ["<important caveat or unknown>"],
  "data_basis": "<1-2 sentences on what comparables were used>",
  "comparable_count": <integer>
}"""
    else:
        system_prompt = """You are a specialist Dubai real estate valuation analyst for Arabian Ranches 2 (AR2) villas.

Your task: given a property description and comparable active listing data, produce a realistic market value estimate for today.

Critical AR2 valuation rules:
- Each community has its own villa type definitions with specific BUA and plot size ranges. A "Type 2" in Samara (4-bed, BUA 3,128–4,361 sqft) is a completely different product from a "Type 2" in Casa (3-bed, BUA 2,892–3,394 sqft). NEVER compare types across communities.
- The villa_type_reference block in the data contains the authoritative BUA and plot ranges for this exact community+type. Use these as your anchor.
- BUA above bua_max_sqft = extension. This is a strong premium driver — an extended villa commands meaningfully more than a standard one.
- Plot size within the plot_min_sqft to plot_max_sqft range is the primary differentiator between standard units of the same type. A plot at the top of the range is worth significantly more than one at the bottom.
- Condition/feature premiums (private pool, full upgrade, excellent finishes, corner plot, single row) add real value on top of the plot premium.
- If cross_community_warning is present, reflect that uncertainty clearly in confidence and key_risks.
- Anchor to the comparable median and adjust logically for plot position, extension, and condition. Do not extrapolate wildly.

Output ONLY valid JSON in this exact structure, no markdown fences:
{
  "low": <integer AED>,
  "mid": <integer AED>,
  "high": <integer AED>,
  "currency": "AED",
  "confidence": "low|medium|high",
  "rationale": {
    "low": "<brief reason for low end>",
    "mid": "<brief reason for mid — anchor point>",
    "high": "<brief reason for high end>"
  },
  "premium_factors": ["<feature adding value>"],
  "discount_factors": ["<feature reducing value or risk>"],
  "key_risks": ["<important caveat or unknown>"],
  "data_basis": "<1-2 sentences on what comparables were used>",
  "comparable_count": <integer>
}"""

    user_message = f"Property description:\n{text}\n\nMarket data:\n{json.dumps(context, indent=2)}"

    response = client.responses.create(
        model="gpt-5-mini",
        instructions=system_prompt,
        input=user_message,
        max_output_tokens=1400,
    )

    raw = response.output_text.strip()
    # Strip markdown fences if model adds them
    raw = re.sub(r"^```(?:json)?\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\n?```$", "", raw, flags=re.MULTILINE)
    # Extract only the JSON object if extra prose was included
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        raw = raw[brace_start:brace_end + 1]

    try:
        estimate = json.loads(raw)
    except json.JSONDecodeError:
        estimate = {"raw": raw, "parse_error": "Could not parse structured JSON from model response"}

    return {
        "purpose": purpose,
        "community": community or "Arabian Ranches 2",
        "all_communities": all_communities,
        "villa_type": villa_type,
        "bedrooms": beds,
        "features": features,
        "match_basis": match_basis,
        "cross_community_warning": cross_community_warning,
        "type_available_in": type_available_in,
        "comparable_count": price_stats.get("count", 0),
        "active_price_stats": price_stats,
        "ppsf_stats": ppsf_stats,
        "estimate": estimate,
        "sample_comparables": sample_comps[:6],
    }
