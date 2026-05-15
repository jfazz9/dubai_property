import argparse
import re
from pathlib import Path

import pandas as pd
from workflow_paths import ensure_purpose_dirs, master_file, prompt_for_purpose, timestamp


REFERENCE_FILE = Path("data/ar2_bayut_floorplan_reference.csv")
CANDIDATE_COLUMNS = [
    "purpose",
    "community",
    "type",
    "property_category",
    "evidence_count",
    "active_evidence_count",
    "bedrooms_median",
    "bathrooms_median",
    "property_size_median",
    "property_size_min",
    "property_size_max",
    "bua_description_median",
    "bua_description_min",
    "bua_description_max",
    "plot_size_median",
    "plot_size_min",
    "plot_size_max",
    "plot_description_median",
    "plot_description_min",
    "plot_description_max",
    "price_median",
    "reference_status",
    "reference_bua_values",
    "reference_plot_values",
    "candidate_note",
    "example_urls",
]


def clean_text(value):
    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def normalize_type(value):
    text = clean_text(value)

    if not text:
        return None

    match = re.search(r"\btype\s*([0-9]+[a-zA-Z]?)\b", text, re.IGNORECASE)

    if match:
        return f"Type {match.group(1).upper()}"

    return text


def numeric_series(series):
    return pd.to_numeric(series, errors="coerce")


def rounded_median(series):
    values = numeric_series(series).dropna()

    if values.empty:
        return None

    return int(round(values.median()))


def rounded_min(series):
    values = numeric_series(series).dropna()

    if values.empty:
        return None

    return int(round(values.min()))


def rounded_max(series):
    values = numeric_series(series).dropna()

    if values.empty:
        return None

    return int(round(values.max()))


def compact_number_list(values):
    clean_values = []

    for value in values:
        if value is None or pd.isna(value):
            continue

        try:
            clean_values.append(str(int(float(value))))
        except (TypeError, ValueError):
            continue

    return "; ".join(sorted(set(clean_values), key=lambda item: int(item)))


def reference_lookup(reference_df, community, villa_type):
    if reference_df.empty:
        return None

    matches = reference_df[
        (reference_df["community"].astype(str).str.casefold() == str(community).casefold())
        & (reference_df["type"].astype(str).str.casefold() == str(villa_type).casefold())
    ]

    if matches.empty:
        return None

    return matches.iloc[0]


def build_candidate_rows(master_df, reference_df, purpose, min_evidence=2, active_only=False):
    required_columns = {"predicted_community", "detected_type_from_description", "url"}
    missing_columns = required_columns - set(master_df.columns)

    if missing_columns:
        raise ValueError(f"Master file is missing required columns: {', '.join(sorted(missing_columns))}")

    listings_df = master_df.copy()
    listings_df["community_for_candidate"] = listings_df["predicted_community"].map(clean_text)
    listings_df["type_for_candidate"] = listings_df["detected_type_from_description"].map(normalize_type)

    listings_df = listings_df[
        (listings_df["community_for_candidate"] != "")
        & listings_df["type_for_candidate"].notna()
        & (listings_df["type_for_candidate"] != "")
    ]

    if active_only and "is_active" in listings_df.columns:
        listings_df = listings_df[listings_df["is_active"].fillna(True).astype(bool)]

    candidate_rows = []
    grouped = listings_df.groupby(["community_for_candidate", "type_for_candidate"], dropna=False)

    for (community, villa_type), group in grouped:
        evidence_count = len(group)

        if evidence_count < min_evidence:
            continue

        active_count = evidence_count

        if "is_active" in group.columns:
            active_count = int(group["is_active"].fillna(True).astype(bool).sum())

        reference_row = reference_lookup(reference_df, community, villa_type)
        reference_status = "missing_from_reference" if reference_row is None else "already_in_reference"
        property_category = ""
        reference_bua_values = ""
        reference_plot_values = ""

        if reference_row is not None:
            property_category = clean_text(reference_row.get("property_category"))
            reference_bua_values = compact_number_list([
                reference_row.get("bua_reference_sqft"),
                reference_row.get("pf_bua"),
                reference_row.get("pf_bua_upgraded"),
                reference_row.get("area_reference_sqft"),
            ])
            reference_plot_values = compact_number_list([
                reference_row.get("plot_reference_sqft"),
                reference_row.get("pf_plot"),
                reference_row.get("pf_plot_a"),
                reference_row.get("area_reference_sqft"),
            ])

        if not property_category:
            property_category = "townhouse" if community.casefold() == "camelia" else "villa"

        example_urls = " | ".join(group["url"].dropna().astype(str).head(3))
        size_spread = rounded_max(group.get("property_size_sqft", pd.Series(dtype=float))) or 0
        size_floor = rounded_min(group.get("property_size_sqft", pd.Series(dtype=float))) or 0
        spread = size_spread - size_floor

        if reference_status == "missing_from_reference":
            note = "Review: listing descriptions repeatedly mention this community/type but it is not in the reference."
        elif spread > 1000:
            note = "Review sizes before promoting: listing size spread is wide, likely upgraded/extended/plot-driven evidence."
        else:
            note = "Useful evidence: compare medians against existing reference values."

        candidate_rows.append({
            "purpose": purpose,
            "community": community,
            "type": villa_type,
            "property_category": property_category,
            "evidence_count": evidence_count,
            "active_evidence_count": active_count,
            "bedrooms_median": rounded_median(group.get("bedrooms", pd.Series(dtype=float))),
            "bathrooms_median": rounded_median(group.get("bathrooms", pd.Series(dtype=float))),
            "property_size_median": rounded_median(group.get("property_size_sqft", pd.Series(dtype=float))),
            "property_size_min": rounded_min(group.get("property_size_sqft", pd.Series(dtype=float))),
            "property_size_max": rounded_max(group.get("property_size_sqft", pd.Series(dtype=float))),
            "bua_description_median": rounded_median(group.get("bua_from_description", pd.Series(dtype=float))),
            "bua_description_min": rounded_min(group.get("bua_from_description", pd.Series(dtype=float))),
            "bua_description_max": rounded_max(group.get("bua_from_description", pd.Series(dtype=float))),
            "plot_size_median": rounded_median(group.get("plot_size_sqft", pd.Series(dtype=float))),
            "plot_size_min": rounded_min(group.get("plot_size_sqft", pd.Series(dtype=float))),
            "plot_size_max": rounded_max(group.get("plot_size_sqft", pd.Series(dtype=float))),
            "plot_description_median": rounded_median(group.get("plot_from_description", pd.Series(dtype=float))),
            "plot_description_min": rounded_min(group.get("plot_from_description", pd.Series(dtype=float))),
            "plot_description_max": rounded_max(group.get("plot_from_description", pd.Series(dtype=float))),
            "price_median": rounded_median(group.get("price", pd.Series(dtype=float))),
            "reference_status": reference_status,
            "reference_bua_values": reference_bua_values,
            "reference_plot_values": reference_plot_values,
            "candidate_note": note,
            "example_urls": example_urls,
        })

    return pd.DataFrame(candidate_rows, columns=CANDIDATE_COLUMNS).sort_values(
        ["reference_status", "community", "type"],
        ascending=[False, True, True],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Build review candidates for improving the AR2 floorplan reference from trusted listing descriptions."
    )
    parser.add_argument("--purpose", choices=["sale", "rent"], help="Listing purpose. If omitted, you will be prompted.")
    parser.add_argument("--master", help="Master listing CSV. Defaults to output/<purpose>/listing_details_master.csv.")
    parser.add_argument("--reference", default=str(REFERENCE_FILE), help="Existing AR2 floorplan reference CSV.")
    parser.add_argument("--output", help="Candidate output CSV.")
    parser.add_argument("--min-evidence", type=int, default=2, help="Minimum repeated listings for a candidate.")
    parser.add_argument("--active-only", action="store_true", help="Only use rows currently marked active.")
    args = parser.parse_args()

    purpose = args.purpose or prompt_for_purpose()
    ensure_purpose_dirs(purpose)

    master_path = Path(args.master) if args.master else master_file(purpose)
    reference_path = Path(args.reference)
    output_path = Path(args.output) if args.output else Path(
        f"data/ar2_floorplan_reference_candidates_{purpose}_{timestamp()}.csv"
    )

    master_df = pd.read_csv(master_path)
    reference_df = pd.read_csv(reference_path)
    candidates_df = build_candidate_rows(
        master_df,
        reference_df,
        purpose=purpose,
        min_evidence=args.min_evidence,
        active_only=args.active_only,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_df.to_csv(output_path, index=False)

    print(f"Master rows read: {len(master_df)}")
    print(f"Candidate rows written: {len(candidates_df)}")
    print(f"Output: {output_path}")

    if not candidates_df.empty:
        print("\nTop candidates:")
        print(candidates_df[["community", "type", "evidence_count", "reference_status"]].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
