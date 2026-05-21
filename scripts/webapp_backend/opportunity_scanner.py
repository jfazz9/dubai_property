"""Opportunity Scanner — standalone tool that scans the listing database for
poachable listings without needing a client brief.

Scoring logic:
  - Staleness: listed_age parsed to days → heavier score for 30 / 60 / 90+ days
  - Overpriced: price vs community median → flags >5% and >15% above median
  - Weak listing: description length below community average

Top candidates are sent to OpenAI for natural-language opportunity ranking.
"""

import json
import re
import sys

import pandas as pd

from .data_loader import read_master


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_master_dispatch(purpose):
    pkg = sys.modules.get("webapp_backend") or sys.modules.get("scripts.webapp_backend")
    if pkg is not None and hasattr(pkg, "read_master"):
        return pkg.read_master(purpose)
    return read_master(purpose)


def _parse_listed_age_days(text: str):
    """Convert 'X days ago', 'X months ago', 'X hours ago' → integer days.

    Returns None if the text cannot be parsed.
    """
    if not text:
        return None
    t = str(text).lower().strip()
    # hours / minutes → treat as 0 days (just listed)
    if re.search(r'\d+\s+hour|\d+\s+minute|just now', t):
        return 0
    m = re.match(r'(\d+)\s+day', t)
    if m:
        return int(m.group(1))
    m = re.match(r'(\d+)\s+month', t)
    if m:
        return int(m.group(1)) * 30
    m = re.match(r'(\d+)\s+year', t)
    if m:
        return int(m.group(1)) * 365
    m = re.match(r'(\d+)\s+week', t)
    if m:
        return int(m.group(1)) * 7
    return None


def _rule_score(row: dict, community_medians: dict, purpose: str) -> int:
    """Compute a simple rule-based opportunity score (higher = better candidate)."""
    score = 0

    # Staleness
    days = row.get("_days_on_market")
    if days is not None:
        if days >= 90:
            score += 4
        elif days >= 60:
            score += 3
        elif days >= 30:
            score += 2
        elif days >= 14:
            score += 1

    # Overpriced vs community median
    price_col = "annual_rent" if purpose == "rent" else "price"
    community = str(row.get("predicted_community") or "")
    price = row.get(price_col)
    if community and price and community in community_medians:
        median = community_medians.get(community)
        if median and median > 0:
            ratio = price / median
            if ratio > 1.15:
                score += 3
            elif ratio > 1.05:
                score += 1

    # Description quality (shorter → weaker listing presentation)
    desc_len = len(str(row.get("description") or ""))
    if desc_len < 1000:
        score += 2
    elif desc_len < 1200:
        score += 1

    return score


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def opportunity_scan(
    api_key=None,
    community_filter=None,
    beds_filter=None,
    purpose_filter="both",
    limit=15,
):
    """Scan the active listing database for poachable opportunities.

    Parameters
    ----------
    api_key : str
        OpenAI API key.
    community_filter : list[str] | None
        Restrict to specific communities.
    beds_filter : int | None
        Restrict to this bedroom count.
    purpose_filter : "sale" | "rent" | "both"
        Which master CSV(s) to scan.
    limit : int
        Maximum number of opportunity cards to return.
    """
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    # --- Load master CSVs ----------------------------------------------------
    purposes_to_load = []
    if purpose_filter in ("both", "sale"):
        purposes_to_load.append("sale")
    if purpose_filter in ("both", "rent"):
        purposes_to_load.append("rent")

    frames = []
    for purpose in purposes_to_load:
        try:
            df, _ = _read_master_dispatch(purpose)
            df = df.copy()
            df["_purpose"] = purpose
            frames.append(df)
        except Exception:
            pass

    if not frames:
        raise RuntimeError("No listing data found.")

    master_df = pd.concat(frames, ignore_index=True)

    # Coerce numeric columns
    for col in ["price", "annual_rent", "bedrooms", "property_size_sqft", "plot_size_sqft"]:
        if col in master_df.columns:
            master_df[col] = pd.to_numeric(master_df[col], errors="coerce")

    # --- Active listings only ------------------------------------------------
    if "is_active" in master_df.columns:
        try:
            from check_active_listings import is_active_value
            active_mask = master_df["is_active"].apply(is_active_value)
        except ImportError:
            active_mask = master_df["is_active"].astype(str).str.lower().isin(["true", "1", "yes"])
        master_df = master_df[active_mask].copy()

    if master_df.empty:
        raise RuntimeError("No active listings found in the database.")

    total_active = len(master_df)

    # --- Parse staleness -----------------------------------------------------
    if "listed_age" in master_df.columns:
        master_df["_days_on_market"] = master_df["listed_age"].apply(_parse_listed_age_days)
    else:
        master_df["_days_on_market"] = None

    # --- Optional filters ----------------------------------------------------
    if community_filter:
        comms = [c.strip() for c in community_filter if c.strip()]
        if comms and "predicted_community" in master_df.columns:
            mask = master_df["predicted_community"].fillna("").isin(comms)
            filtered = master_df[mask]
            if not filtered.empty:
                master_df = filtered

    if beds_filter is not None:
        try:
            beds = int(beds_filter)
            if "bedrooms" in master_df.columns:
                mask = master_df["bedrooms"] == beds
                filtered = master_df[mask]
                if not filtered.empty:
                    master_df = filtered
        except (ValueError, TypeError):
            pass

    # --- Community price medians (per purpose — MUST NOT mix sale/rent prices) --
    # Keyed as {purpose: {community: median_price}} so sale prices are never
    # compared against rent medians (which would produce absurd % differences).
    community_medians: dict = {"sale": {}, "rent": {}}
    for purpose in purposes_to_load:
        price_col = "annual_rent" if purpose == "rent" else "price"
        subset = master_df[master_df["_purpose"] == purpose].copy()
        if price_col in subset.columns and "predicted_community" in subset.columns:
            for comm, grp in subset.groupby("predicted_community"):
                if comm:
                    med = grp[price_col].median()
                    if not pd.isna(med):
                        community_medians[purpose][str(comm)] = float(med)

    # --- Rule-based scoring --------------------------------------------------
    master_df["_opp_score"] = master_df.apply(
        lambda row: _rule_score(
            row.to_dict(),
            community_medians.get(row.get("_purpose", "sale"), {}),
            row.get("_purpose", "sale"),
        ),
        axis=1,
    )

    # Take top 30 by rule score (with staleness as tiebreak)
    positive_candidates = master_df[master_df["_opp_score"] > 0].sort_values(
        ["_opp_score", "_days_on_market"],
        ascending=[False, False],
    ).head(30)

    # If somehow nothing scored, fall back to top-30 by staleness
    if positive_candidates.empty:
        positive_candidates = master_df.sort_values(
            "_days_on_market", ascending=False, na_position="last"
        ).head(30)

    candidates = positive_candidates

    # --- Build AI payload ----------------------------------------------------
    candidate_rows = []
    for i, (_, row) in enumerate(candidates.iterrows(), start=1):
        purpose = row.get("_purpose", "sale")
        price_col = "annual_rent" if purpose == "rent" else "price"
        community = str(row.get("predicted_community") or "Unknown")
        price = row.get(price_col)
        # Use purpose-specific medians so sale prices are never vs rent medians
        purpose_medians = community_medians.get(purpose, {})
        median = purpose_medians.get(community)
        price_vs_median = None
        if price and median and median > 0:
            price_vs_median = round((float(price) / median - 1) * 100, 1)

        candidate_rows.append({
            "candidate_ref": f"opp_{i}",
            "purpose": purpose,
            "community": community,
            "predicted_type": str(row.get("predicted_type") or "Unknown"),
            "bedrooms": int(row["bedrooms"]) if pd.notna(row.get("bedrooms")) else None,
            "property_size_sqft": int(row["property_size_sqft"]) if pd.notna(row.get("property_size_sqft")) else None,
            "plot_size_sqft": int(row["plot_size_sqft"]) if pd.notna(row.get("plot_size_sqft")) else None,
            "price": int(price) if price and not pd.isna(price) else None,
            "price_currency": "AED/yr" if purpose == "rent" else "AED",
            "price_vs_median_pct": price_vs_median,
            "community_median": int(median) if median else None,
            "days_on_market": int(row["_days_on_market"]) if pd.notna(row.get("_days_on_market")) else None,
            "listed_age_text": str(row.get("listed_age") or "Unknown"),
            "agent_name": str(row.get("agent_name") or "Unknown"),
            "agency_name": str(row.get("agency_name") or "Unknown"),
            "description_length": len(str(row.get("description") or "")),
            "description_snippet": str(row.get("description") or "")[:350],
            "rule_score": int(row.get("_opp_score", 0)),
        })

    if not candidate_rows:
        raise RuntimeError("No opportunity candidates found — try removing filters or running a fresh data scrape.")

    # --- OpenAI call ---------------------------------------------------------
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package not installed. Run: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=api_key, timeout=90.0)

    system_prompt = (
        "You are a Dubai real estate business development analyst specialising in Arabian Ranches 2 (AR2).\n"
        "Your task: review these active listings and identify the best poaching opportunities for a buyer's / selling agent.\n\n"
        "A POACHABLE listing is one where the current agent is likely failing the owner:\n"
        "- Stale on market (30+ days) without a price reduction → owner may be frustrated\n"
        "- Overpriced vs community median → owner needs a price-reality conversation\n"
        "- Weak, generic, or very short listing description → agent is not actively marketing it\n"
        "- Both stale AND overpriced → highest-priority opportunity\n\n"
        "For each opportunity you select, provide:\n"
        "- opportunity_type: one of stale_overpriced | stale_listing | overpriced | weak_listing | motivated_seller\n"
        "- opportunity_score: 1-10 (10 = best opportunity)\n"
        "- headline: punchy 1-line summary (e.g. '3 Months Stale + 12% Above Median — Owner Likely Frustrated')\n"
        "- reason: 2-3 sentences explaining WHY this is an opportunity\n"
        "- approach: recommended agent action (e.g. 'Co-broke approach to current agent', 'Direct owner call', 'Price reduction conversation')\n"
        "- talking_point: the single best talking point to open the approach call\n\n"
        "Select and rank only the TOP 12 opportunities. Discard weak candidates.\n\n"
        "Return ONLY valid JSON — no markdown, no prose:\n"
        '{"opportunities":[{"candidate_ref":"opp_N","opportunity_type":"...","opportunity_score":N,'
        '"headline":"...","reason":"...","approach":"...","talking_point":"..."}],'
        '"scan_note":"1-2 sentence summary of the current opportunity landscape."}'
    )

    user_message = (
        f"Active listings to analyse ({len(candidate_rows)} candidates):\n"
        + json.dumps(candidate_rows, indent=2, ensure_ascii=False)
    )

    response = client.responses.create(
        model="gpt-5-mini",
        instructions=system_prompt,
        input=user_message,
        max_output_tokens=5000,
    )

    raw = response.output_text.strip()
    # Strip markdown fences if model adds them
    raw = re.sub(r"^```(?:json)?\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\n?```$", "", raw, flags=re.MULTILINE)
    # Extract the outermost JSON object
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        raw = raw[brace_start:brace_end + 1]

    # Replace smart/curly quotes that the model sometimes emits
    raw = (
        raw
        .replace("“", '"').replace("”", '"')   # left/right double
        .replace("‘", "'").replace("’", "'")   # left/right single
        .replace("—", "-").replace("–", "-")   # em/en dash in values
    )

    ai_result = None
    try:
        ai_result = json.loads(raw)
    except json.JSONDecodeError:
        # Attempt a graceful recovery: strip control characters and retry
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", raw)
        try:
            ai_result = json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    if ai_result is None:
        # Last resort: tell the user the scan worked but we couldn't parse results
        ai_result = {
            "opportunities": [],
            "scan_note": "AI returned data but it could not be parsed — try again.",
            "parse_error": True,
        }

    # --- Merge AI results with candidate data --------------------------------
    candidate_map = {row["candidate_ref"]: row for row in candidate_rows}
    enriched = []
    for opp in ai_result.get("opportunities", [])[:limit]:
        ref = opp.get("candidate_ref", "")
        base = candidate_map.get(ref, {})
        enriched.append({**base, **opp})

    return {
        "opportunities": enriched,
        "scan_note": ai_result.get("scan_note", ""),
        "total_active_scanned": total_active,
        "candidates_sent_to_ai": len(candidate_rows),
    }
