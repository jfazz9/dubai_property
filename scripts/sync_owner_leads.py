import argparse
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests


DEFAULT_OUTPUT = Path("data/owner_property_leads.csv")
ENV_URL = "OWNER_LEADS_CSV_URL"


def google_sheet_csv_url(url, gid=None, sheet=None):
    text = str(url or "").strip()

    if not text:
        return ""

    parsed = urlparse(text)

    if "docs.google.com" not in parsed.netloc or "/spreadsheets/" not in parsed.path:
        return text

    sheet_match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)

    if not sheet_match:
        return text

    query = parse_qs(parsed.query)
    fragment_query = parse_qs(parsed.fragment)
    sheet_id = sheet_match.group(1)

    if sheet:
        export_path = f"/spreadsheets/d/{sheet_id}/gviz/tq"
        export_query = urlencode({
            "tqx": "out:csv",
            "sheet": sheet,
        })
        return urlunparse(("https", "docs.google.com", export_path, "", export_query, ""))

    selected_gid = gid or query.get("gid", [None])[0] or fragment_query.get("gid", [None])[0] or "0"
    export_path = f"/spreadsheets/d/{sheet_id}/export"
    export_query = urlencode({
        "format": "csv",
        "gid": selected_gid,
    })

    return urlunparse(("https", "docs.google.com", export_path, "", export_query, ""))


def download_csv(url, output_path):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    text = response.text

    if "text/html" in content_type or text.lstrip().lower().startswith("<!doctype html"):
        raise RuntimeError(
            "Google returned an HTML page instead of CSV. "
            "Check the sheet sharing/publish settings or use a valid CSV export link."
        )

    if not text.strip():
        raise RuntimeError("Downloaded CSV is empty.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8", newline="")
    return len(text.encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Sync owner_property_leads.csv from a Google Sheets CSV export.")
    parser.add_argument(
        "--url",
        default=os.getenv(ENV_URL, ""),
        help=f"Google Sheets URL or CSV export URL. Can also be set with {ENV_URL}.",
    )
    parser.add_argument("--gid", default=None, help="Google Sheets tab gid if using a normal sheet URL.")
    parser.add_argument("--sheet", default=None, help="Google Sheets tab name, for example: data.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path.")
    args = parser.parse_args()

    if not args.url:
        raise SystemExit(
            "Missing Google Sheets URL. Use --url or set OWNER_LEADS_CSV_URL."
        )

    csv_url = google_sheet_csv_url(args.url, gid=args.gid, sheet=args.sheet)
    output_path = Path(args.output)
    bytes_written = download_csv(csv_url, output_path)
    print(f"Synced owner leads to {output_path} ({bytes_written:,} bytes)")


if __name__ == "__main__":
    main()
