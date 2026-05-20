from pathlib import Path

import pandas as pd

from enquiry_matcher import clean_number
from workflow_paths import master_file

from .constants import (
    MARKET_SALES_FILE,
    MARKET_SALES_PREDICTED_FILE,
    MARKET_RENTALS_FILE,
    MARKET_RENTALS_PREDICTED_FILE,
)


def read_master(purpose):
    path = master_file(purpose)

    if not path.exists():
        raise FileNotFoundError(f"Missing master file: {path}")

    return pd.read_csv(path), path


def clean_market_number(value):
    number = clean_number(value)
    return number if number is not None else None


def load_market_sales(path=MARKET_SALES_FILE):
    # Prefer the type-predicted file when loading the default market file — it has
    # the same columns plus predicted_type/prediction_confidence added by
    # predict_market_villa_type.py. When a custom path is supplied (e.g. in tests),
    # use it as-is.
    if str(path) == MARKET_SALES_FILE:
        predicted_path = Path(MARKET_SALES_PREDICTED_FILE)
        market_path = predicted_path if predicted_path.exists() else Path(path)
    else:
        market_path = Path(path)

    if not market_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(market_path)

    for column in ["price", "price_per_sqft", "size_sqft", "beds", "prediction_confidence"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "sold_date" in df.columns:
        df["_sold_date"] = pd.to_datetime(df["sold_date"], errors="coerce", dayfirst=True)

    return df


def load_market_rentals(path=MARKET_RENTALS_FILE):
    # Prefer the type-predicted file when loading the default rental market file.
    # When a custom path is supplied (e.g. in tests), use it as-is.
    if str(path) == MARKET_RENTALS_FILE:
        predicted_path = Path(MARKET_RENTALS_PREDICTED_FILE)
        market_path = predicted_path if predicted_path.exists() else Path(path)
    else:
        market_path = Path(path)

    if not market_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(market_path)

    numeric_columns = [
        "Bedrooms",
        "Size sqft",
        "Rental AED",
        "Rental Yield %",
        "Purchase Price AED",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "Start Date" in df.columns:
        df["_start_date"] = pd.to_datetime(df["Start Date"], errors="coerce", dayfirst=True)

    return df
