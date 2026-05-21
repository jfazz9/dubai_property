import argparse
from datetime import datetime
from pathlib import Path
import re

import pandas as pd

from extract_listing_details import (
    calculate_listed_date,
    clean_decimal,
    clean_number,
    extract_agency_from_description,
    extract_agent_and_agency,
    extract_agent_profile,
    extract_baths_from_body,
    extract_beds_from_body,
    extract_bua_from_description,
    extract_description,
    build_description_json,
    extract_header_metrics,
    extract_listed_age,
    extract_plot_from_description,
    extract_price_from_body,
    extract_villa_type,
)
from workflow_paths import ensure_purpose_dirs, master_file, processed_dir, prompt_for_purpose, raw_dir, timestamp


RUN_TIMESTAMP = timestamp()
AR2_COMMUNITIES = {
    "azalea",
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

PROCESSED_COLUMNS = [
    "listing_purpose",
    "url",
    "scraped_at",
    "title",
    "price",
    "sale_price",
    "rent_price",
    "rent_frequency",
    "annual_rent",
    "monthly_rent_equivalent",
    "bedrooms",
    "bathrooms",
    "property_size_sqft",
    "plot_size_sqft",
    "price_per_sqft",
    "sale_price_per_sqft",
    "rent_per_sqft",
    "detected_type_from_description",
    "bua_from_description",
    "plot_from_description",
    "agent_name",
    "agent_profile_url",
    "agent_rating",
    "agent_review_count",
    "agent_badge",
    "agent_is_superagent",
    "agent_properties_count",
    "agent_closed_deals",
    "agent_response_time",
    "agent_total_value",
    "agency_name",
    "listed_age",
    "listed_date",
    "description",
    "description_json",
]


def latest_raw_file(purpose):
    current_raw_dir = raw_dir(purpose)
    raw_files = sorted(current_raw_dir.glob("listing_pages_*.csv"), key=lambda path: path.stat().st_mtime)

    if not raw_files:
        raise FileNotFoundError(f"No raw listing page files found in {current_raw_dir}")

    return raw_files[-1]


def parse_scraped_at(value):
    if not value or pd.isna(value):
        return datetime.now()

    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.now()


def clean_optional_text(value):
    if value is None or pd.isna(value):
        return None

    value = str(value).strip()
    return value or None


def clean_bool(value):
    if value is None or pd.isna(value):
        return None

    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def calculate_price_per_sqft(price, size):
    if not price or not size:
        return None

    return round(price / size)


def extract_rent_frequency(text):
    if not text:
        return None

    normalized = str(text).lower()

    patterns = [
        (r"\b\d[\d,]*\s*(?:aed\s*)?(?:/|per\s+)?(year|yearly|annually|annual|pa|p\.a\.)\b", "yearly"),
        (r"\b\d[\d,]*\s*(?:aed\s*)?(?:/|per\s+)?(month|monthly)\b", "monthly"),
        (r"\b\d[\d,]*\s*(?:aed\s*)?(?:/|per\s+)?(week|weekly)\b", "weekly"),
        (r"\b\d[\d,]*\s*(?:aed\s*)?(?:/|per\s+)?(day|daily)\b", "daily"),
        (r"\b(year|yearly|annually|annual)\b", "yearly"),
        (r"\b(month|monthly)\b", "monthly"),
        (r"\b(week|weekly)\b", "weekly"),
        (r"\b(day|daily)\b", "daily"),
    ]

    for pattern, frequency in patterns:
        if re.search(pattern, normalized):
            return frequency

    return None


def annualize_rent(price, frequency):
    if not price or not frequency:
        return None

    multipliers = {
        "yearly": 1,
        "monthly": 12,
        "weekly": 52,
        "daily": 365,
    }
    multiplier = multipliers.get(frequency)

    if not multiplier:
        return None

    return clean_number(price * multiplier)


def is_arabian_ranches_2_listing(row):
    haystack = " ".join([
        str(row.get("url") or ""),
        str(row.get("current_url") or ""),
        str(row.get("title") or ""),
        str(row.get("full_page_text") or ""),
    ]).lower()

    if "arabian-ranches-2" in haystack or "arabian ranches 2" in haystack:
        return True

    return any(community in haystack for community in AR2_COMMUNITIES)


def process_raw_row(row, purpose="sale", target_area="Arabian Ranches 2"):
    body = str(row.get("full_page_text") or "")
    title = row.get("title")
    scraped_datetime = parse_scraped_at(row.get("scraped_at"))

    page_status = clean_optional_text(row.get("page_status")) or "ok"

    if page_status != "ok":
        return None

    if target_area and target_area.strip().lower() in {"arabian ranches 2", "ar2"}:
        if not is_arabian_ranches_2_listing(row):
            return None

    header_metrics = extract_header_metrics(body)
    price = clean_number(row.get("price_dom")) or header_metrics.get("price") or extract_price_from_body(body)
    bedrooms = clean_number(row.get("bedrooms_dom")) or header_metrics.get("bedrooms") or extract_beds_from_body(body)
    bathrooms = clean_number(row.get("bathrooms_dom")) or header_metrics.get("bathrooms") or extract_baths_from_body(body)
    property_size = clean_number(row.get("size_dom")) or header_metrics.get("property_size_sqft")
    plot_from_description = extract_plot_from_description(body)
    # plot_size_sqft is only set when explicitly found in the listing description.
    # Never fall back to property_size (BUA) — they are completely different measurements.
    # PPSF uses BUA (property_size) which is the Dubai/Property Finder standard.
    rent_frequency = extract_rent_frequency(body) if purpose == "rent" else None
    annual_rent = annualize_rent(price, rent_frequency) if purpose == "rent" else None
    rent_per_sqft = calculate_price_per_sqft(annual_rent, property_size) if purpose == "rent" else None
    sale_price_per_sqft = calculate_price_per_sqft(price, property_size) if purpose == "sale" else None
    price_per_sqft = rent_per_sqft if purpose == "rent" else sale_price_per_sqft

    description = extract_description(body)
    description_json = build_description_json(description)
    agent_name, agency_name = extract_agent_and_agency(body)
    agent_profile = extract_agent_profile(body)
    agent_name = clean_optional_text(row.get("agent_name_dom")) or agent_name
    agent_profile_url = clean_optional_text(row.get("agent_profile_url_dom"))
    agent_rating = clean_decimal(row.get("agent_rating_dom")) or agent_profile.get("agent_rating")
    agent_review_count = clean_number(row.get("agent_review_count_dom")) or agent_profile.get("agent_review_count")
    agent_is_superagent = clean_bool(row.get("agent_is_superagent_dom"))
    if agent_is_superagent is None:
        agent_is_superagent = agent_profile.get("agent_is_superagent")
    agent_badge = "SuperAgent" if agent_is_superagent else agent_profile.get("agent_badge")
    agent_properties_count = clean_number(row.get("agent_properties_count_dom")) or agent_profile.get("agent_properties_count")
    agent_closed_deals = clean_number(row.get("agent_closed_deals_dom")) or agent_profile.get("agent_closed_deals")
    agent_response_time = clean_optional_text(row.get("agent_response_time_dom")) or agent_profile.get("agent_response_time")
    agent_total_value = clean_optional_text(row.get("agent_total_value_dom")) or agent_profile.get("agent_total_value")
    agency_name = clean_optional_text(row.get("agency_name_dom")) or agency_name
    agency_name = agency_name or extract_agency_from_description(description)

    listed_age = clean_optional_text(row.get("listed_age_dom")) or extract_listed_age(body)
    listed_date = calculate_listed_date(listed_age, scraped_datetime)

    return {
        "listing_purpose": purpose,
        "url": row.get("url"),
        "scraped_at": row.get("scraped_at"),
        "title": title,
        "price": clean_number(price),
        "sale_price": clean_number(price) if purpose == "sale" else None,
        "rent_price": clean_number(price) if purpose == "rent" else None,
        "rent_frequency": rent_frequency,
        "annual_rent": annual_rent,
        "monthly_rent_equivalent": round(annual_rent / 12) if annual_rent else None,
        "bedrooms": clean_number(bedrooms),
        "bathrooms": clean_number(bathrooms),
        "property_size_sqft": clean_number(property_size),
        "plot_size_sqft": clean_number(plot_from_description),
        "price_per_sqft": clean_number(price_per_sqft),
        "sale_price_per_sqft": clean_number(sale_price_per_sqft),
        "rent_per_sqft": clean_number(rent_per_sqft),
        "detected_type_from_description": extract_villa_type(body),
        "bua_from_description": extract_bua_from_description(body),
        "plot_from_description": plot_from_description,
        "agent_name": agent_name,
        "agent_profile_url": agent_profile_url,
        "agent_rating": agent_rating,
        "agent_review_count": clean_number(agent_review_count),
        "agent_badge": agent_badge,
        "agent_is_superagent": agent_is_superagent,
        "agent_properties_count": clean_number(agent_properties_count),
        "agent_closed_deals": clean_number(agent_closed_deals),
        "agent_response_time": agent_response_time,
        "agent_total_value": agent_total_value,
        "agency_name": agency_name,
        "listed_age": listed_age,
        "listed_date": listed_date,
        "description": description,
        "description_json": description_json,
    }


def update_master(processed_df, purpose):
    if processed_df.empty:
        return None

    processed_df = processed_df.reindex(columns=PROCESSED_COLUMNS)

    current_master_file = master_file(purpose)

    if current_master_file.exists():
        master_df = pd.read_csv(current_master_file)
        combined_df = pd.concat([master_df, processed_df], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=["url"], keep="last")
    else:
        combined_df = processed_df

    combined_df = combined_df.reindex(columns=PROCESSED_COLUMNS)
    try:
        combined_df.to_csv(current_master_file, index=False)
        return current_master_file
    except PermissionError:
        fallback_file = current_master_file.with_name(
            f"{current_master_file.stem}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}{current_master_file.suffix}"
        )
        combined_df.to_csv(fallback_file, index=False)
        print(
            f"Could not update {current_master_file}. It may be open in Excel or another app. "
            f"Saved fallback master file instead: {fallback_file}"
        )
        return fallback_file


def main():
    parser = argparse.ArgumentParser(description="Process raw Property Finder listing pages into clean listing data.")
    parser.add_argument("--purpose", choices=["sale", "rent"], help="Listing purpose. If omitted, you will be prompted.")
    parser.add_argument("--input", help="Raw listing page CSV. Defaults to the latest output/raw/listing_pages_*.csv.")
    parser.add_argument("--output", help="CSV file for processed listing output.")
    parser.add_argument(
        "--target-area",
        default="Arabian Ranches 2",
        help="Skip out-of-area advertised listings. Use an empty string to disable. Default: Arabian Ranches 2.",
    )
    parser.add_argument(
        "--update-master",
        action="store_true",
        help="Update output/listing_details_master.csv from processed data. Normally the prediction step updates the final master.",
    )
    args = parser.parse_args()

    purpose = args.purpose or prompt_for_purpose()
    ensure_purpose_dirs(purpose)

    input_file = Path(args.input) if args.input else latest_raw_file(purpose)
    output_file = Path(args.output) if args.output else processed_dir(purpose) / f"listing_details_{RUN_TIMESTAMP}.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    raw_df = pd.read_csv(input_file)
    processed_rows = []
    skipped = 0
    skipped_out_of_area = 0

    for _, row in raw_df.iterrows():
        if args.target_area and args.target_area.strip().lower() in {"arabian ranches 2", "ar2"}:
            page_status = clean_optional_text(row.get("page_status")) or "ok"

            if page_status == "ok" and not is_arabian_ranches_2_listing(row):
                skipped_out_of_area += 1

        processed = process_raw_row(row, purpose, args.target_area)

        if processed is None:
            skipped += 1
            continue

        processed_rows.append(processed)

    processed_df = pd.DataFrame(processed_rows)
    processed_df = processed_df.reindex(columns=PROCESSED_COLUMNS)
    processed_df.to_csv(output_file, index=False)

    master_output_file = None

    if args.update_master:
        master_output_file = update_master(processed_df, purpose)

    print(f"Input raw file: {input_file}")
    print(f"Processed rows: {len(processed_df)}")
    print(f"Skipped rows: {skipped}")
    print(f"Skipped out-of-area rows: {skipped_out_of_area}")
    print(f"Processed output file: {output_file}")

    if args.update_master:
        print(f"Updated master file: {master_output_file}")


if __name__ == "__main__":
    main()
