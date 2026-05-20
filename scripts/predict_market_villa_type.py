"""Predict villa types for market transaction data.

Supports both sales and rental market files:

  Sales  (data/dxb_market_sales.csv)   → data/dxb_market_sales_predicted.csv
  Rental (data/dxb_market_rentals.csv) → data/dxb_market_rentals_predicted.csv

Each file has community and size_sqft (BUA) but no villa type. This script
predicts the type for each transaction using the same range-based scoring logic
as predict_villa_type.py, then saves the result.

Inputs available per row:
    Sales:  community, size_sqft, beds
    Rental: Location (sub-community), Size sqft, Bedrooms

Plot and bathrooms are not available in market data, so scoring relies on
BUA range matching and bed count alone. Confidence will generally be lower
than for full listing data where plot and bathrooms are also known.

Usage:
    python scripts/predict_market_villa_type.py              # sales (default)
    python scripts/predict_market_villa_type.py --purpose rent

Output adds three columns to the original file:
    predicted_type          e.g. "Type 3", "Likely Type 2", "Possible Type 1E"
    prediction_confidence   0-100 score
    prediction_reason       short explanation

The script is incremental: rows that already have a predicted_type are skipped.
Only new rows (appended to the raw file) or rows with a blank prediction are
processed. Re-run whenever the source file is updated with new transactions.
"""
import argparse
from pathlib import Path

import pandas as pd

from predict_villa_type import clean_number, predict_row

MARKET_SALES_FILE = Path("data/dxb_market_sales.csv")
MARKET_SALES_PREDICTED_FILE = Path("data/dxb_market_sales_predicted.csv")
MARKET_RENTALS_FILE = Path("data/dxb_market_rentals.csv")
MARKET_RENTALS_PREDICTED_FILE = Path("data/dxb_market_rentals_predicted.csv")
REFERENCE_FILE = Path("data/ar2_villa_type_reference.csv")


def sales_row_to_synthetic(row):
    """Convert a market sales row into the Series format expected by predict_row().

    Sales data columns: community, size_sqft (BUA), beds (optional).
    """
    community = str(row.get("community") or "").strip()
    description = f"Villa for sale in {community}, Arabian Ranches 2."
    title = f"Sale in {community}: Villa"

    return pd.Series({
        "title": title,
        "description": description,
        "url": "",
        "bedrooms": clean_number(row.get("beds")),
        "bathrooms": None,
        "property_size_sqft": clean_number(row.get("size_sqft")),
        "bua_from_description": None,
        "plot_from_description": None,
        "plot_size_sqft": None,
        "detected_type_from_description": None,
    })


def rental_row_to_synthetic(row):
    """Convert a market rental row into the Series format expected by predict_row().

    Rental data columns: Location (sub-community), Size sqft (BUA), Bedrooms (optional).
    """
    community = str(row.get("Location") or "").strip()
    description = f"Villa for rent in {community}, Arabian Ranches 2."
    title = f"Rent in {community}: Villa"

    return pd.Series({
        "title": title,
        "description": description,
        "url": "",
        "bedrooms": clean_number(row.get("Bedrooms")),
        "bathrooms": None,
        "property_size_sqft": clean_number(row.get("Size sqft")),
        "bua_from_description": None,
        "plot_from_description": None,
        "plot_size_sqft": None,
        "detected_type_from_description": None,
    })


def load_reference():
    if not REFERENCE_FILE.exists():
        raise FileNotFoundError(f"Reference file not found: {REFERENCE_FILE}")

    df = pd.read_csv(REFERENCE_FILE)

    for col in ["bua_ref_sqft", "bua_min_sqft", "bua_max_sqft",
                "plot_ref_sqft", "plot_min_sqft", "plot_max_sqft",
                "bedrooms", "bathrooms"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def run_prediction(input_path, output_path, row_to_synthetic, numeric_cols):
    """Load, predict only missing rows, and save. Returns the result DataFrame."""
    if not input_path.exists():
        raise FileNotFoundError(f"Market file not found: {input_path}")

    reference_df = load_reference()
    raw_df = pd.read_csv(input_path)

    for col in numeric_cols:
        if col in raw_df.columns:
            raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce")

    # Load existing predictions if the output file already exists
    if output_path.exists():
        result_df = pd.read_csv(output_path)
        existing_count = len(result_df)

        if len(raw_df) > existing_count:
            new_rows = raw_df.iloc[existing_count:].reset_index(drop=True)
            for col in ["predicted_type", "prediction_confidence", "prediction_reason"]:
                new_rows[col] = None
            result_df = pd.concat([result_df, new_rows], ignore_index=True)
            print(f"New rows detected: {len(raw_df) - existing_count}")
        else:
            print(f"No new rows in {input_path}.")
    else:
        result_df = raw_df.copy()
        for col in ["predicted_type", "prediction_confidence", "prediction_reason"]:
            result_df[col] = None

    # Only predict rows that do not already have a predicted_type
    needs_prediction = result_df["predicted_type"].isna()
    to_predict_count = needs_prediction.sum()

    if to_predict_count == 0:
        print("All rows already predicted. Nothing to do.")
    else:
        print(f"Predicting {to_predict_count} row(s)...")
        for idx in result_df[needs_prediction].index:
            row = result_df.loc[idx]
            synthetic = row_to_synthetic(row)
            prediction = predict_row(synthetic, reference_df)
            result_df.at[idx, "predicted_type"] = prediction.get("predicted_type")
            result_df.at[idx, "prediction_confidence"] = prediction.get("prediction_confidence")
            result_df.at[idx, "prediction_reason"] = prediction.get("prediction_reason")

    result_df.to_csv(output_path, index=False)
    return result_df


def print_summary(result_df, input_path, output_path, community_col):
    total = len(result_df)
    confident = (result_df["prediction_confidence"] >= 70).sum()
    likely = ((result_df["prediction_confidence"] >= 45) & (result_df["prediction_confidence"] < 70)).sum()
    possible = ((result_df["prediction_confidence"] >= 25) & (result_df["prediction_confidence"] < 45)).sum()
    unknown = (result_df["prediction_confidence"] < 25).sum()

    print(f"Input:  {input_path}  ({total} rows)")
    print(f"Output: {output_path}")
    print()
    print(f"  Confident  (>=70):  {confident:>4}  direct type label")
    print(f"  Likely   (45-69):   {likely:>4}  'Likely Type X'")
    print(f"  Possible (25-44):   {possible:>4}  'Possible Type X'")
    print(f"  Unknown   (<25):    {unknown:>4}  not enough signal")

    if unknown > 0 and community_col in result_df.columns:
        low_conf = result_df[result_df["prediction_confidence"] < 25][community_col].value_counts()
        print()
        print("  Low-confidence breakdown by community:")
        for community, count in low_conf.items():
            print(f"    {community}: {count}")
        print()
        print("  These are usually rows where size_sqft is missing or far outside all reference ranges.")

    print()
    print("Re-run this script whenever the source file is updated with new transactions.")
    print("The webapp will automatically use the predicted file if it exists.")


def main():
    parser = argparse.ArgumentParser(
        description="Predict villa types for market transaction data (sales or rentals)."
    )
    parser.add_argument(
        "--purpose",
        choices=["sale", "rent"],
        default="sale",
        help="Which market file to process: 'sale' (default) or 'rent'.",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Override the default input CSV path.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override the default output CSV path.",
    )
    args = parser.parse_args()

    if args.purpose == "rent":
        input_path = Path(args.input) if args.input else MARKET_RENTALS_FILE
        output_path = Path(args.output) if args.output else MARKET_RENTALS_PREDICTED_FILE
        row_to_synthetic = rental_row_to_synthetic
        numeric_cols = ["Bedrooms", "Size sqft", "Rental AED"]
        community_col = "Location"
    else:
        input_path = Path(args.input) if args.input else MARKET_SALES_FILE
        output_path = Path(args.output) if args.output else MARKET_SALES_PREDICTED_FILE
        row_to_synthetic = sales_row_to_synthetic
        numeric_cols = ["beds"]
        community_col = "community"

    result_df = run_prediction(input_path, output_path, row_to_synthetic, numeric_cols)
    print_summary(result_df, input_path, output_path, community_col)


if __name__ == "__main__":
    main()
