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
