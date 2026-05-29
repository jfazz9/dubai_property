import argparse
import re
from pathlib import Path

import pandas as pd
from workflow_paths import (
    ensure_purpose_dirs,
    predicted_dir,
    processed_dir,
    prompt_for_purpose,
)
from listing_master import save_csv_with_fallback, update_master


REFERENCE_FILE = Path("data/ar2_villa_type_reference.csv")


def clean_text(value):
    if value is None or pd.isna(value):
        return ""

    return str(value)


def clean_number(value):
    if value is None or pd.isna(value):
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        match = re.search(r"[\d,]+", str(value))
        return int(match.group(0).replace(",", "")) if match else None


def latest_processed_file(purpose):
    current_processed_dir = processed_dir(purpose)
    files = sorted(current_processed_dir.glob("listing_details*.csv"), key=lambda path: path.stat().st_mtime)

    if not files:
        raise FileNotFoundError(f"No processed listing files found in {current_processed_dir}")

    return files[-1]


def extract_community(row, reference_df):
    haystack = " ".join([
        clean_text(row.get("title")),
        clean_text(row.get("description")),
        clean_text(row.get("url")),
    ]).lower()

    communities = sorted(reference_df["community"].dropna().unique(), key=len, reverse=True)

    for community in communities:
        if community.lower() in haystack:
            return community

    return None


def normalize_type(value):
    if not value:
        return None

    match = re.search(r"\btype\s*([0-9]+[a-zA-Z]?)\b", str(value), re.IGNORECASE)

    if match:
        return f"Type {match.group(1).upper()}"

    return str(value).strip()


def first_clean_number(row, columns):
    for column in columns:
        value = clean_number(row.get(column))

        if value is not None:
            return value

    return None


def score_bua_range(bua, candidate):
    """Score a listing BUA against the community+type min/max range.

    Within range  → strong match (listing is standard, unextended).
    Above max     → still this type but extended; score depends on how far over.
    Below min     → increasingly unlikely to be this type.
    """
    if bua is None:
        return 0, []

    bua_min = clean_number(candidate.get("bua_min_sqft"))
    bua_max = clean_number(candidate.get("bua_max_sqft"))
    bua_ref = clean_number(candidate.get("bua_ref_sqft"))

    # Fall back to point reference if range not available
    if bua_min is None or bua_max is None:
        if bua_ref is None:
            return 0, []
        diff = abs(bua - bua_ref)
        if diff <= 100:
            return 28, [f"BUA {bua} very close to reference {bua_ref}"]
        if diff <= 300:
            return 18, [f"BUA {bua} close to reference {bua_ref}"]
        if diff <= 600:
            return 8, [f"BUA {bua} roughly close to reference {bua_ref}"]
        return -10, [f"BUA {bua} far from reference {bua_ref}"]

    if bua_min <= bua <= bua_max:
        return 30, [f"BUA {bua} within standard range {bua_min}–{bua_max}"]

    if bua > bua_max:
        pct_over = (bua - bua_max) / bua_max
        if pct_over <= 0.12:
            return 22, [f"BUA {bua} slightly above range — possible extension (max {bua_max})"]
        if pct_over <= 0.30:
            return 14, [f"BUA {bua} above range — likely extended (max {bua_max})"]
        return 6, [f"BUA {bua} well above range — heavily extended or wrong type (max {bua_max})"]

    # Below bua_min
    pct_under = (bua_min - bua) / bua_min
    if pct_under <= 0.08:
        return 18, [f"BUA {bua} just below range — measurement difference likely (min {bua_min})"]
    if pct_under <= 0.20:
        return 6, [f"BUA {bua} below standard range (min {bua_min})"]
    return -12, [f"BUA {bua} well below reference range {bua_min}–{bua_max}"]


def score_plot_range(plot, candidate):
    """Score a listing plot size against the community+type min/max range.

    Plot varies more than BUA within a type (corner plots, irregular shapes)
    so tolerances are wider.
    """
    if plot is None:
        return 0, []

    plot_min = clean_number(candidate.get("plot_min_sqft"))
    plot_max = clean_number(candidate.get("plot_max_sqft"))
    plot_ref = clean_number(candidate.get("plot_ref_sqft"))

    if plot_min is None or plot_max is None:
        if plot_ref is None:
            return 0, []
        diff = abs(plot - plot_ref)
        if diff <= 150:
            return 18, [f"plot {plot} very close to reference {plot_ref}"]
        if diff <= 400:
            return 11, [f"plot {plot} close to reference {plot_ref}"]
        if diff <= 800:
            return 5, [f"plot {plot} roughly close to reference {plot_ref}"]
        return -8, [f"plot {plot} far from reference {plot_ref}"]

    if plot_min <= plot <= plot_max:
        return 20, [f"plot {plot} within standard range {plot_min}–{plot_max}"]

    if plot > plot_max:
        pct_over = (plot - plot_max) / plot_max
        if pct_over <= 0.20:
            return 14, [f"plot {plot} slightly above range — corner/large plot likely (max {plot_max})"]
        if pct_over <= 0.45:
            return 8, [f"plot {plot} above range (max {plot_max})"]
        return 3, [f"plot {plot} well above range — irregular plot or wrong type (max {plot_max})"]

    # Below plot_min
    pct_under = (plot_min - plot) / plot_min
    if pct_under <= 0.12:
        return 12, [f"plot {plot} just below range (min {plot_min})"]
    if pct_under <= 0.25:
        return 4, [f"plot {plot} below standard range (min {plot_min})"]
    return -8, [f"plot {plot} well below reference range {plot_min}–{plot_max}"]


def predict_row(row, reference_df):
    community = extract_community(row, reference_df)
    direct_type = normalize_type(row.get("detected_type_from_description"))

    bedrooms = clean_number(row.get("bedrooms"))
    bathrooms = clean_number(row.get("bathrooms"))
    bua = first_clean_number(row, ["property_size_sqft", "bua_from_description"])
    # Prefer plot_from_description — it is always extracted directly from the listing
    # text. plot_size_sqft may contain BUA in older data due to a processing bug.
    plot = first_clean_number(row, ["plot_from_description", "plot_size_sqft"])

    if not community:
        return {
            "predicted_community": None,
            "predicted_type": None,
            "prediction_confidence": 0,
            "prediction_reason": "No AR2 community detected in listing text",
            "prediction_source": "none",
            "type_mismatch_flag": False,
        }

    candidates = reference_df[reference_df["community"].str.lower() == community.lower()].copy()

    if candidates.empty:
        return {
            "predicted_community": community,
            "predicted_type": None,
            "prediction_confidence": 0,
            "prediction_reason": "No reference rows for detected community",
            "prediction_source": "none",
            "type_mismatch_flag": False,
        }

    # If the listing explicitly states the type, trust it — skip scoring entirely.
    # The description is ground truth; BUA/plot scoring is only a fallback for
    # listings that don't mention the type.
    if direct_type:
        return {
            "predicted_community": community,
            "predicted_type": direct_type,
            "predicted_type_candidate": direct_type,
            "prediction_confidence": 100,
            "prediction_reason": "type stated explicitly in listing description or title",
            "prediction_source": "description",
            "type_mismatch_flag": False,
        }

    scored = []

    for _, candidate in candidates.iterrows():
        score = 0
        reasons = []

        candidate_type = normalize_type(candidate["type"])

        # Bedrooms — authoritative from reference, hard mismatch is a strong negative
        ref_bedrooms = clean_number(candidate.get("bedrooms"))
        if bedrooms is not None and ref_bedrooms is not None:
            if bedrooms == ref_bedrooms:
                score += 20
                reasons.append("bedrooms match")
            else:
                score -= 12
                reasons.append(f"bedrooms differ ({bedrooms} vs {ref_bedrooms})")

        # Bathrooms — useful but can vary by fit-out
        ref_bathrooms = clean_number(candidate.get("bathrooms"))
        if bathrooms is not None and ref_bathrooms is not None:
            if bathrooms == ref_bathrooms:
                score += 10
                reasons.append("bathrooms match")
            elif abs(bathrooms - ref_bathrooms) == 1:
                score += 4
                reasons.append(f"bathrooms close ({bathrooms} vs {ref_bathrooms})")
            else:
                score -= 4
                reasons.append(f"bathrooms differ ({bathrooms} vs {ref_bathrooms})")

        # BUA — scored against community+type min/max range
        bua_score, bua_reasons = score_bua_range(bua, candidate)
        score += bua_score
        reasons.extend(bua_reasons)

        # Plot — scored against community+type min/max range
        plot_score, plot_reasons = score_plot_range(plot, candidate)
        score += plot_score
        reasons.extend(plot_reasons)

        scored.append({
            "type": candidate_type,
            "score": max(0, min(100, score)),
            "raw_score": score,
            "reason": "; ".join(reasons),
        })

    scored = sorted(scored, key=lambda item: item["raw_score"], reverse=True)
    best = scored[0]

    # If we reach here, direct_type was None — prediction is based on physical data
    source_parts = []

    if bua:
        source_parts.append("bua")

    if plot:
        source_parts.append("plot")

    if bedrooms or bathrooms:
        source_parts.append("bed_bath")

    type_mismatch_flag = False  # No description type to mismatch against

    if best["score"] >= 70:
        prediction_label = best["type"]
    elif best["score"] >= 45:
        prediction_label = f"Likely {best['type']}"
    elif best["score"] >= 25:
        prediction_label = f"Possible {best['type']}"
    else:
        prediction_label = "Unknown"

    return {
        "predicted_community": community,
        "predicted_type": prediction_label,
        "predicted_type_candidate": best["type"],
        "prediction_confidence": best["score"],
        "prediction_reason": best["reason"],
        "prediction_source": "+".join(source_parts) if source_parts else "reference",
        "type_mismatch_flag": type_mismatch_flag,
    }


def main():
    parser = argparse.ArgumentParser(description="Predict Arabian Ranches 2 villa type from processed listing data.")
    parser.add_argument("--purpose", choices=["sale", "rent"], help="Listing purpose. If omitted, you will be prompted.")
    parser.add_argument("--input", help="Processed listing CSV. Defaults to latest output/processed/listing_details*.csv.")
    parser.add_argument("--reference", default=str(REFERENCE_FILE), help="AR2 floorplan reference CSV.")
    parser.add_argument("--output", help="Output CSV with prediction columns.")
    parser.add_argument("--no-master", action="store_true", help="Do not update output/listing_details_master.csv.")
    parser.add_argument(
        "--partial-refresh",
        action="store_true",
        help=(
            "Update/add rows without treating this input as a complete scope refresh. "
            "Existing rows keep last_seen_date/times_seen and missing scoped rows are not marked inactive."
        ),
    )
    args = parser.parse_args()

    purpose = args.purpose or prompt_for_purpose()
    ensure_purpose_dirs(purpose)

    input_file = Path(args.input) if args.input else latest_processed_file(purpose)
    reference_file = Path(args.reference)

    if args.output:
        output_file = Path(args.output)
    else:
        predicted_dir(purpose).mkdir(parents=True, exist_ok=True)
        output_file = predicted_dir(purpose) / f"{input_file.stem}_predicted.csv"

    listings_df = pd.read_csv(input_file)
    reference_df = pd.read_csv(reference_file)

    predictions = listings_df.apply(lambda row: predict_row(row, reference_df), axis=1)
    predictions_df = pd.DataFrame(list(predictions))
    output_df = pd.concat([listings_df, predictions_df], axis=1)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file = save_csv_with_fallback(output_df, output_file)

    master_output_file = None
    price_history_output_file = None
    price_change_count = 0

    if not args.no_master:
        master_output_file, price_history_output_file, price_change_count = update_master(
            output_df,
            purpose,
            refresh_seen=not args.partial_refresh,
        )

    print(f"Input listings: {input_file}")
    print(f"Reference file: {reference_file}")
    print(f"Rows predicted: {len(output_df)}")
    print(f"Output file: {output_file}")

    if not args.no_master:
        print(f"Updated master file: {master_output_file}")
        print(f"Price changes recorded: {price_change_count}")

        if price_history_output_file:
            print(f"Updated price history file: {price_history_output_file}")

    print(output_df[[
        "title",
        "bedrooms",
        "bathrooms",
        "bua_from_description",
        "plot_size_sqft",
        "detected_type_from_description",
        "predicted_community",
        "predicted_type",
        "prediction_confidence",
        "type_mismatch_flag",
    ]].to_string(index=False, max_colwidth=60))


if __name__ == "__main__":
    main()
