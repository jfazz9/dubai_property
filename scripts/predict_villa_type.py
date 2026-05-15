import argparse
import re
from pathlib import Path

import pandas as pd
from workflow_paths import (
    ensure_purpose_dirs,
    master_file,
    predicted_dir,
    price_history_file,
    processed_dir,
    prompt_for_purpose,
)


REFERENCE_FILE = Path("data/ar2_bayut_floorplan_reference.csv")
REFERENCE_BUA_COLUMNS = ["bua_reference_sqft", "pf_bua", "pf_bua_upgraded", "area_reference_sqft"]
REFERENCE_PLOT_COLUMNS = ["plot_reference_sqft", "pf_plot", "pf_plot_a", "area_reference_sqft"]
MASTER_TRACKING_COLUMNS = [
    "first_seen_date",
    "last_seen_date",
    "times_seen",
    "is_active",
]
PRICE_HISTORY_COLUMNS = [
    "url",
    "listing_purpose",
    "predicted_community",
    "predicted_type",
    "change_date",
    "old_price",
    "new_price",
    "price_change",
    "price_change_pct",
    "old_annual_rent",
    "new_annual_rent",
    "annual_rent_change",
    "annual_rent_change_pct",
    "title",
]


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


def score_size(value, reference_value, strong_points, medium_points, weak_points, label):
    if value is None or reference_value is None or pd.isna(reference_value):
        return 0, []

    diff = abs(value - int(reference_value))

    if diff <= 100:
        return strong_points, [f"{label} very close ({value} vs {int(reference_value)})"]

    if diff <= 250:
        return medium_points, [f"{label} close ({value} vs {int(reference_value)})"]

    if diff <= 500:
        return weak_points, [f"{label} roughly close ({value} vs {int(reference_value)})"]

    return -10, [f"{label} far from reference ({value} vs {int(reference_value)})"]


def first_clean_number(row, columns):
    for column in columns:
        value = clean_number(row.get(column))

        if value is not None:
            return value

    return None


def score_best_size(value, row, reference_columns, strong_points, medium_points, weak_points, label):
    best_score = 0
    best_reasons = []

    for column in reference_columns:
        reference_value = clean_number(row.get(column))

        if reference_value is None:
            continue

        score, reasons = score_size(
            value,
            reference_value,
            strong_points=strong_points,
            medium_points=medium_points,
            weak_points=weak_points,
            label=f"{label}/{column}",
        )

        if not best_reasons or score > best_score:
            best_score = score
            best_reasons = reasons

    return best_score, best_reasons


def predict_row(row, reference_df):
    community = extract_community(row, reference_df)
    direct_type = normalize_type(row.get("detected_type_from_description"))

    bedrooms = clean_number(row.get("bedrooms"))
    bathrooms = clean_number(row.get("bathrooms"))
    bua = first_clean_number(row, ["pf_bua", "bua_from_description"])
    plot = first_clean_number(row, ["pf_plot", "plot_from_description", "plot_size_sqft"])

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

    scored = []

    for _, candidate in candidates.iterrows():
        score = 0
        reasons = []

        candidate_type = normalize_type(candidate["type"])

        if direct_type and candidate_type == direct_type:
            score += 65
            reasons.append(f"description mentions {direct_type}")
        elif direct_type:
            score -= 15
            reasons.append(f"description mentions {direct_type}, not {candidate_type}")

        if bedrooms is not None and bedrooms == clean_number(candidate["bedrooms"]):
            score += 18
            reasons.append("bedrooms match")
        elif bedrooms is not None:
            score -= 8
            reasons.append(f"bedrooms differ ({bedrooms} vs {clean_number(candidate['bedrooms'])})")

        candidate_bathrooms = clean_number(candidate["bathrooms"])

        if bathrooms is not None and bathrooms == candidate_bathrooms:
            score += 10
            reasons.append("bathrooms match")
        elif bathrooms is not None and candidate_bathrooms is not None and abs(bathrooms - candidate_bathrooms) == 1:
            score += 4
            reasons.append(f"bathrooms close ({bathrooms} vs {candidate_bathrooms})")
        elif bathrooms is not None:
            score -= 3
            reasons.append(f"bathrooms differ ({bathrooms} vs {candidate_bathrooms})")

        size_score, size_reasons = score_best_size(
            bua,
            candidate,
            REFERENCE_BUA_COLUMNS,
            strong_points=28,
            medium_points=20,
            weak_points=10,
            label="BUA",
        )
        score += size_score
        reasons.extend(size_reasons)

        plot_score, plot_reasons = score_best_size(
            plot,
            candidate,
            REFERENCE_PLOT_COLUMNS,
            strong_points=18,
            medium_points=12,
            weak_points=6,
            label="plot",
        )
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

    source_parts = []

    if direct_type:
        source_parts.append("description")

    if bua:
        source_parts.append("bua")

    if plot:
        source_parts.append("plot")

    if bedrooms or bathrooms:
        source_parts.append("bed_bath")

    type_mismatch_flag = bool(
        direct_type
        and best["type"] != direct_type
        and best["score"] >= 55
    )

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


def seen_date_from_row(row):
    scraped_at = row.get("scraped_at")

    if scraped_at is not None and not pd.isna(scraped_at):
        parsed = pd.to_datetime(scraped_at, errors="coerce")

        if not pd.isna(parsed):
            return parsed.strftime("%Y-%m-%d")

    return pd.Timestamp.now().strftime("%Y-%m-%d")


def prepare_master_update(master_df, predicted_df):
    if predicted_df.empty:
        return master_df

    master_df = master_df.copy() if master_df is not None else pd.DataFrame()
    predicted_df = predicted_df.copy()
    run_seen_date = pd.Timestamp.now().strftime("%Y-%m-%d")

    for column in MASTER_TRACKING_COLUMNS:
        if column not in master_df.columns:
            master_df[column] = pd.NA

    existing_by_url = {}

    if not master_df.empty and "url" in master_df.columns:
        existing_by_url = master_df.drop_duplicates(subset=["url"], keep="last").set_index("url").to_dict("index")

    seen_urls = set(predicted_df["url"].dropna().astype(str))
    run_communities = set(predicted_df["predicted_community"].dropna().astype(str))
    run_purposes = set(predicted_df["listing_purpose"].dropna().astype(str)) if "listing_purpose" in predicted_df.columns else set()

    updated_rows = []

    for _, row in predicted_df.iterrows():
        row_data = row.to_dict()
        url = str(row_data.get("url"))
        existing = existing_by_url.get(url, {})
        seen_date = seen_date_from_row(row_data) or run_seen_date
        previous_times_seen = clean_number(existing.get("times_seen")) or 0

        row_data["first_seen_date"] = existing.get("first_seen_date") or seen_date
        row_data["last_seen_date"] = seen_date
        row_data["times_seen"] = previous_times_seen + 1
        row_data["is_active"] = True
        updated_rows.append(row_data)

    if not master_df.empty and "url" in master_df.columns:
        for _, row in master_df.iterrows():
            row_data = row.to_dict()
            url = str(row_data.get("url"))

            if url in seen_urls:
                continue

            row_community = row_data.get("predicted_community")
            row_purpose = row_data.get("listing_purpose")
            same_run_scope = (
                row_community in run_communities
                and (not run_purposes or row_purpose in run_purposes)
            )

            if same_run_scope:
                row_data["is_active"] = False

            row_data["times_seen"] = clean_number(row_data.get("times_seen")) or 1
            row_data["first_seen_date"] = row_data.get("first_seen_date") or row_data.get("last_seen_date") or run_seen_date
            row_data["last_seen_date"] = row_data.get("last_seen_date") or row_data.get("first_seen_date")
            updated_rows.append(row_data)

    combined_df = pd.DataFrame(updated_rows)
    combined_df = combined_df.drop_duplicates(subset=["url"], keep="first")

    if "predicted_community" in combined_df.columns:
        combined_df = combined_df[combined_df["predicted_community"].notna()]

    regular_columns = [column for column in combined_df.columns if column not in MASTER_TRACKING_COLUMNS]
    return combined_df.reindex(columns=regular_columns + MASTER_TRACKING_COLUMNS)


def percent_change(old_value, new_value):
    old_number = clean_number(old_value)
    new_number = clean_number(new_value)

    if not old_number or new_number is None:
        return None

    return round(((new_number - old_number) / old_number) * 100, 2)


def build_price_history_events(master_df, predicted_df):
    if predicted_df.empty or master_df is None or master_df.empty or "url" not in master_df.columns:
        return pd.DataFrame(columns=PRICE_HISTORY_COLUMNS)

    existing_by_url = master_df.drop_duplicates(subset=["url"], keep="last").set_index("url").to_dict("index")
    events = []

    for _, row in predicted_df.iterrows():
        row_data = row.to_dict()
        url = str(row_data.get("url"))
        existing = existing_by_url.get(url)

        if not existing:
            continue

        old_price = clean_number(existing.get("price"))
        new_price = clean_number(row_data.get("price"))
        old_annual_rent = clean_number(existing.get("annual_rent"))
        new_annual_rent = clean_number(row_data.get("annual_rent"))
        price_changed = old_price is not None and new_price is not None and old_price != new_price
        annual_rent_changed = (
            old_annual_rent is not None
            and new_annual_rent is not None
            and old_annual_rent != new_annual_rent
        )

        if not price_changed and not annual_rent_changed:
            continue

        events.append({
            "url": url,
            "listing_purpose": row_data.get("listing_purpose") or existing.get("listing_purpose"),
            "predicted_community": row_data.get("predicted_community") or existing.get("predicted_community"),
            "predicted_type": row_data.get("predicted_type") or existing.get("predicted_type"),
            "change_date": seen_date_from_row(row_data),
            "old_price": old_price,
            "new_price": new_price,
            "price_change": new_price - old_price if price_changed else None,
            "price_change_pct": percent_change(old_price, new_price) if price_changed else None,
            "old_annual_rent": old_annual_rent,
            "new_annual_rent": new_annual_rent,
            "annual_rent_change": new_annual_rent - old_annual_rent if annual_rent_changed else None,
            "annual_rent_change_pct": percent_change(old_annual_rent, new_annual_rent) if annual_rent_changed else None,
            "title": row_data.get("title") or existing.get("title"),
        })

    return pd.DataFrame(events).reindex(columns=PRICE_HISTORY_COLUMNS)


def update_price_history(price_events_df, purpose):
    if price_events_df.empty:
        return None

    current_price_history_file = price_history_file(purpose)

    if current_price_history_file.exists():
        history_df = pd.read_csv(current_price_history_file)
        combined_df = pd.concat([history_df, price_events_df], ignore_index=True)
    else:
        combined_df = price_events_df

    combined_df = combined_df.reindex(columns=PRICE_HISTORY_COLUMNS)
    combined_df = combined_df.drop_duplicates(
        subset=["url", "change_date", "old_price", "new_price", "old_annual_rent", "new_annual_rent"],
        keep="last",
    )
    return save_csv_with_fallback(combined_df, current_price_history_file)


def save_csv_with_fallback(df, output_file):
    try:
        df.to_csv(output_file, index=False)
        return output_file
    except PermissionError:
        fallback_file = output_file.with_name(
            f"{output_file.stem}_{pd.Timestamp.now().strftime('%Y-%m-%d_%H-%M-%S')}{output_file.suffix}"
        )
        df.to_csv(fallback_file, index=False)
        print(
            f"Could not update {output_file}. It may be open in Excel or another app. "
            f"Saved fallback file instead: {fallback_file}"
        )
        return fallback_file


def update_master(predicted_df, purpose):
    if predicted_df.empty:
        return None, None, 0

    current_master_file = master_file(purpose)

    if current_master_file.exists():
        master_df = pd.read_csv(current_master_file)
    else:
        master_df = pd.DataFrame()

    price_events_df = build_price_history_events(master_df, predicted_df)
    combined_df = prepare_master_update(master_df, predicted_df)
    price_history_output_file = update_price_history(price_events_df, purpose)

    try:
        return save_csv_with_fallback(combined_df, current_master_file), price_history_output_file, len(price_events_df)
    except PermissionError:
        fallback_file = current_master_file.with_name(
            f"{current_master_file.stem}_{pd.Timestamp.now().strftime('%Y-%m-%d_%H-%M-%S')}{current_master_file.suffix}"
        )
        combined_df.to_csv(fallback_file, index=False)
        print(
            f"Could not update {current_master_file}. It may be open in Excel or another app. "
            f"Saved fallback master file instead: {fallback_file}"
        )
        return fallback_file, price_history_output_file, len(price_events_df)


def main():
    parser = argparse.ArgumentParser(description="Predict Arabian Ranches 2 villa type from processed listing data.")
    parser.add_argument("--purpose", choices=["sale", "rent"], help="Listing purpose. If omitted, you will be prompted.")
    parser.add_argument("--input", help="Processed listing CSV. Defaults to latest output/processed/listing_details*.csv.")
    parser.add_argument("--reference", default=str(REFERENCE_FILE), help="AR2 floorplan reference CSV.")
    parser.add_argument("--output", help="Output CSV with prediction columns.")
    parser.add_argument("--no-master", action="store_true", help="Do not update output/listing_details_master.csv.")
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
        master_output_file, price_history_output_file, price_change_count = update_master(output_df, purpose)

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
