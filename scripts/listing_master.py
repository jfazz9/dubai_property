import re

import pandas as pd

from workflow_paths import master_file, price_history_file


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


def clean_number(value):
    if value is None or pd.isna(value):
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        match = re.search(r"[\d,]+", str(value))
        return int(match.group(0).replace(",", "")) if match else None


def seen_date_from_row(row):
    scraped_at = row.get("scraped_at")

    if scraped_at is not None and not pd.isna(scraped_at):
        parsed = pd.to_datetime(scraped_at, errors="coerce")

        if not pd.isna(parsed):
            return parsed.strftime("%Y-%m-%d")

    return pd.Timestamp.now().strftime("%Y-%m-%d")


def prepare_master_update(master_df, predicted_df, refresh_seen=True):
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

        if refresh_seen or not existing:
            row_data["last_seen_date"] = seen_date
            row_data["times_seen"] = previous_times_seen + 1
        else:
            row_data["last_seen_date"] = existing.get("last_seen_date") or existing.get("first_seen_date") or seen_date
            row_data["times_seen"] = previous_times_seen or 1

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

            if refresh_seen and same_run_scope:
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


def update_master(predicted_df, purpose, refresh_seen=True):
    if predicted_df.empty:
        return None, None, 0

    current_master_file = master_file(purpose)

    if current_master_file.exists():
        master_df = pd.read_csv(current_master_file)
    else:
        master_df = pd.DataFrame()

    price_events_df = build_price_history_events(master_df, predicted_df)
    combined_df = prepare_master_update(master_df, predicted_df, refresh_seen=refresh_seen)
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
