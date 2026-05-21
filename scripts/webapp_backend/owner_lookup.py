import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from .constants import OWNER_LEADS_FILE


def clean_value(value):
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "item"):
        value = value.item()

    return value


def clean_owner_text(value):
    value = clean_value(value)

    if value is None:
        return ""

    text = str(value).strip()
    text = re.sub(r"\s*\r?\n\s*", ", ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    return text.strip(" ,")


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


def propertyfinder_listing_id(value):
    text = str(value or "")
    match = re.search(r"-(\d+)\.html(?:\b|$)", text)

    if match:
        return match.group(1)

    match = re.search(r"/(?:buy|rent|sale)/(\d+)(?:\b|/|$)", text)
    return match.group(1) if match else ""


def clean_owner_dataframe(df):
    clean_df = df.copy()
    clean_df = clean_df.drop(columns=[
        column for column in clean_df.columns
        if not str(column).strip() or str(column).startswith("Unnamed")
    ], errors="ignore")
    clean_df.columns = [str(column).strip() for column in clean_df.columns]
    return clean_df


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

    return clean_owner_text(row.get(column))


def owner_row_first_value(row, df, candidate_groups):
    for candidates in candidate_groups:
        value = owner_row_value(row, df, candidates)

        if value:
            return value

    return ""


def owner_property_summary(row, df):
    parts = [
        owner_row_first_value(row, df, [["Villa No.", "Villa No", "Villa Number"], ["No.", "No", "Unit No.", "Unit No"]]),
        owner_row_value(row, df, ["Street"]),
        owner_row_value(row, df, ["Community"]),
        owner_row_value(row, df, ["Area"]),
    ]
    return ", ".join(part for part in parts if part)


def owner_payload_from_row(row, df, matched_url, match_type):
    link_value = owner_row_value(row, df, ["Link", "Links", "propertyfinder_urls", "propertyfinder url"])
    urls = extract_urls(link_value)
    villa_number = owner_row_first_value(row, df, [["Villa No.", "Villa No", "Villa Number"], ["No.", "No", "Unit No.", "Unit No"]])

    return {
        "found": True,
        "match_type": match_type,
        "matched_url": matched_url,
        "propertyfinder_urls": urls,
        "lead": {
            "date": owner_row_value(row, df, ["Date"]),
            "status": owner_row_value(row, df, ["Status"]),
            "intent": owner_row_value(row, df, ["Sell/Rent", "Rent/Sell", "Intent"]),
            "owners": owner_row_value(row, df, ["Owners", "Owner"]),
            "numbers": owner_row_value(row, df, ["Numbers", "Phone", "Phones"]),
            "villa_number": villa_number,
            "street": owner_row_value(row, df, ["Street"]),
            "community": owner_row_value(row, df, ["Community"]),
            "area": owner_row_value(row, df, ["Area"]),
            "property": owner_property_summary(row, df),
            "beds": owner_row_value(row, df, ["Beds"]),
            "floors": owner_row_value(row, df, ["Floors"]),
            "parking": owner_row_value(row, df, ["Parking"]),
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
    owner_df = clean_owner_dataframe(owner_df)
    link_column = find_column(owner_df, ["Link", "Links", "propertyfinder_urls", "propertyfinder url"])

    if link_column is None:
        return {
            "found": False,
            "message": "Owner leads file does not have a Link column.",
        }

    normalized_lookup = normalize_url(lookup_url)
    lookup_listing_id = propertyfinder_listing_id(lookup_url)

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

    if lookup_listing_id:
        for _, row in owner_df.iterrows():
            urls = extract_urls(row.get(link_column))

            for url in urls:
                if propertyfinder_listing_id(url) == lookup_listing_id:
                    return owner_payload_from_row(row, owner_df, url, "listing_id")

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
