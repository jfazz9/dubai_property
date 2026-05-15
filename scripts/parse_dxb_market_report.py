import argparse
import csv
import re
from pathlib import Path

from pypdf import PdfReader


DEFAULT_PDF = Path("data/DXB Interact Market Report.pdf")
DEFAULT_OUTPUT = Path("data/dxb_market_sales.csv")
DATE_PATTERN = re.compile(r"\d{2},\s+[A-Za-z]{3}\s+\d{4}")
LOCATION_PATTERN = re.compile(r"^(.+?),\s+Arabian Ranches 2,\s+Wadi Al Safa", re.IGNORECASE)


def clean_int(value):
    if value is None:
        return ""

    match = re.search(r"\d[\d,]*", str(value))
    return int(match.group(0).replace(",", "")) if match else ""


def clean_gain(value):
    if not value:
        return ""

    match = re.search(r"\(([+-]?\d+)%\)", str(value))
    return int(match.group(1)) if match else ""


def normalize_location(value):
    return re.sub(r"\s+", " ", str(value or "").replace("…", "")).strip()


def page_texts(pdf_path):
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def parse_summary(text):
    summary = {}
    patterns = {
        "median_price_per_sqft": r"Median price / sqft\s+([\d,]+)",
        "median_price": r"Median price\s+([\d,]+)",
        "transactions": r"Transactions\s+([\d,]+)",
        "rental_yield_percent": r"Rental Yield\s+(\d+)%",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        summary[key] = clean_int(match.group(1)) if match else ""

    return summary


def parse_sales_rows(text):
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]
    rows = []
    index = 0

    while index < len(lines):
        location_match = LOCATION_PATTERN.match(lines[index])

        if not location_match:
            index += 1
            continue

        location = normalize_location(location_match.group(1))
        row = {
            "community": location,
            "area": "Arabian Ranches 2",
            "status": "",
            "property_type": "",
            "price": "",
            "capital_gain_percent": "",
            "price_per_sqft": "",
            "size_sqft": "",
            "beds": "",
            "sold_date": "",
            "sold_by": "",
        }
        index += 1

        if index < len(lines) and "Ready" in lines[index]:
            row["status"] = "Ready"
            row["property_type"] = "Villa"
            index += 1

        if index < len(lines):
            row["price"] = clean_int(lines[index])
            row["capital_gain_percent"] = clean_gain(lines[index])
            index += 1

        if index < len(lines):
            row["price_per_sqft"] = clean_int(lines[index])
            index += 1

        if index < len(lines):
            size_line = lines[index]
            date_match = DATE_PATTERN.search(size_line)
            row["size_sqft"] = clean_int(size_line)

            if date_match:
                row["sold_date"] = date_match.group(0).replace(",", "")

            index += 1

        if index < len(lines) and re.search(r"\bBeds?\b", lines[index], flags=re.IGNORECASE):
            row["beds"] = clean_int(lines[index])
            index += 1

        if not row["sold_date"] and index < len(lines) and DATE_PATTERN.match(lines[index]):
            row["sold_date"] = lines[index].replace(",", "")
            index += 1

        if index < len(lines) and lines[index].lower().startswith("individual"):
            row["sold_by"] = lines[index]
            index += 1

        rows.append(row)

    return rows


def parse_report(pdf_path):
    texts = page_texts(pdf_path)
    summary = parse_summary(texts[0] if texts else "")
    rows = []

    for text in texts[1:]:
        for row in parse_sales_rows(text):
            row.update(summary)
            rows.append(row)

    return rows


def write_csv(rows, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "community",
        "area",
        "status",
        "property_type",
        "price",
        "capital_gain_percent",
        "price_per_sqft",
        "size_sqft",
        "beds",
        "sold_date",
        "sold_by",
        "median_price_per_sqft",
        "median_price",
        "transactions",
        "rental_yield_percent",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Parse DXB Interact AR2 market report PDF into CSV.")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="Path to DXB Interact PDF")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    output_path = Path(args.output)

    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing PDF: {pdf_path}")

    rows = parse_report(pdf_path)
    write_csv(rows, output_path)
    print(f"Wrote {len(rows)} market rows to {output_path}")


if __name__ == "__main__":
    main()
