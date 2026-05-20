import argparse
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

from workflow_paths import master_file, normalize_purpose, prompt_for_purpose


CHECK_COLUMNS = [
    "active_checked_at",
    "active_check_status",
    "active_check_reason",
]
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
HUMAN_VERIFICATION_MARKERS = [
    "human verification",
    "verify you are human",
    "captcha",
    "cf-challenge",
    "access denied",
]
INACTIVE_TEXT_MARKERS = [
    "property is no longer available",
    "listing is no longer available",
    "page not found",
    "property not found",
    "we can't find the page",
    "this property has been removed",
]
SEARCH_PAGE_MARKERS = [
    "properties-for-sale",
    "properties-for-rent",
    "/en/buy/properties-for-sale",
    "/en/rent/properties-for-rent",
]

_LISTING_ID_RE = re.compile(r"-(\d{6,12})(?:\.html)?(?:\?|$|/)", re.IGNORECASE)


def extract_listing_id(url):
    """Extract the numeric listing ID from a Property Finder URL, or None."""
    match = _LISTING_ID_RE.search(url or "")
    return match.group(1) if match else None


@dataclass
class ActiveCheckResult:
    is_active: bool
    status: str
    reason: str


def is_active_value(value):
    if value is None or pd.isna(value):
        return True

    return str(value).strip().lower() in {"true", "1", "yes", "active"}


def clean_text(value):
    if value is None or pd.isna(value):
        return ""

    return str(value)


def looks_like_human_verification(text):
    normalized = text.lower()
    return any(marker in normalized for marker in HUMAN_VERIFICATION_MARKERS)


def looks_inactive_from_text(text):
    normalized = text.lower()
    return any(marker in normalized for marker in INACTIVE_TEXT_MARKERS)


def looks_like_search_page(url):
    normalized = url.lower()
    return any(marker in normalized for marker in SEARCH_PAGE_MARKERS)


def classify_response(original_url, response):
    final_url = response.url or original_url
    text = response.text or ""
    status_code = response.status_code
    was_redirected = bool(getattr(response, "history", []))

    if looks_like_human_verification(text):
        return ActiveCheckResult(True, "unknown_human_verification", "human verification or bot challenge page")

    if status_code in {404, 410}:
        return ActiveCheckResult(False, "inactive_http_status", f"HTTP {status_code}")

    if status_code >= 500:
        return ActiveCheckResult(True, "unknown_http_status", f"HTTP {status_code}")

    if status_code >= 400:
        return ActiveCheckResult(True, "unknown_http_status", f"HTTP {status_code}")

    if looks_inactive_from_text(text):
        return ActiveCheckResult(False, "inactive_not_found_text", "page text says listing is unavailable")

    if looks_like_search_page(final_url):
        return ActiveCheckResult(False, "inactive_redirected_to_search", f"redirected to search page: {final_url}")

    # Check if the listing ID in the final URL still matches the original.
    # Property Finder sometimes silently redirects removed listings to a
    # similar listing — same /plp/ path but a different numeric ID.
    original_id = extract_listing_id(original_url)
    final_id = extract_listing_id(final_url)
    if original_id and final_id and original_id != final_id:
        return ActiveCheckResult(False, "inactive_redirected_to_similar", f"redirected from ID {original_id} to {final_id}")

    # If there were redirects but we can't identify the IDs, flag as unknown
    # rather than assuming active.
    if was_redirected and "/plp/" not in final_url.lower():
        return ActiveCheckResult(False, "inactive_redirected_unknown", f"redirected away from listing page: {final_url}")

    if "/plp/" in final_url.lower() and status_code == 200:
        return ActiveCheckResult(True, "active", "listing page returned successfully")

    return ActiveCheckResult(True, "unknown_unclear_page", f"could not confidently classify {final_url}")


def check_url(url, timeout=15):
    try:
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            allow_redirects=True,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return ActiveCheckResult(True, "unknown_request_error", str(exc))

    return classify_response(url, response)


def ensure_check_columns(master_df):
    for column in CHECK_COLUMNS:
        if column not in master_df.columns:
            master_df[column] = ""
        elif master_df[column].dtype != object:
            master_df[column] = master_df[column].astype(object)

    if "is_active" not in master_df.columns:
        master_df["is_active"] = True

    return master_df


def active_row_indexes(master_df):
    return master_df[master_df["is_active"].apply(is_active_value)].index.tolist()


def apply_check_result(master_df, index, result, checked_at):
    master_df.at[index, "is_active"] = bool(result.is_active)
    master_df.at[index, "active_checked_at"] = checked_at
    master_df.at[index, "active_check_status"] = result.status
    master_df.at[index, "active_check_reason"] = result.reason


def run_active_checks(master_df, checker=check_url, limit=None, delay=0.0, checked_at=None):
    checked_at = checked_at or pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    master_df = ensure_check_columns(master_df.copy())
    indexes = active_row_indexes(master_df)

    if limit is not None:
        indexes = indexes[:limit]

    results = []

    for position, index in enumerate(indexes, start=1):
        url = clean_text(master_df.at[index, "url"])

        if not url:
            result = ActiveCheckResult(True, "unknown_missing_url", "missing URL")
        else:
            result = checker(url)

        apply_check_result(master_df, index, result, checked_at)
        results.append({
            "index": index,
            "url": url,
            "is_active": result.is_active,
            "active_check_status": result.status,
            "active_check_reason": result.reason,
        })

        if delay and position < len(indexes):
            time.sleep(delay)

    return master_df, pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description="Check active listing URLs and update master active status conservatively.")
    parser.add_argument("--purpose", choices=["sale", "rent"], help="Listing purpose. If omitted, you will be prompted.")
    parser.add_argument("--input", help="Master CSV to check. Defaults to output/<purpose>/listing_details_master.csv.")
    parser.add_argument("--output", help="Output CSV. Defaults to overwriting the input master CSV.")
    parser.add_argument("--limit", type=int, help="Only check the first N active listings.")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between URL checks.")
    parser.add_argument("--timeout", type=int, default=15, help="Request timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Check URLs and print a summary without writing the master file.")
    args = parser.parse_args()

    purpose = normalize_purpose(args.purpose) if args.purpose else prompt_for_purpose()
    input_file = Path(args.input) if args.input else master_file(purpose)
    output_file = Path(args.output) if args.output else input_file

    if not input_file.exists():
        raise FileNotFoundError(f"Missing master file: {input_file}")

    master_df = pd.read_csv(input_file)

    def checker(url):
        return check_url(url, timeout=args.timeout)

    updated_df, results_df = run_active_checks(
        master_df,
        checker=checker,
        limit=args.limit,
        delay=args.delay,
    )

    print(f"Master file: {input_file}")
    print(f"Active rows checked: {len(results_df)}")

    if not results_df.empty:
        print()
        print(results_df["active_check_status"].value_counts().to_string())
        print()
        print(results_df[["is_active", "active_check_status", "url"]].head(20).to_string(index=False, max_colwidth=100))

    if args.dry_run:
        print()
        print("Dry run: master file was not updated.")
        return

    updated_df.to_csv(output_file, index=False)
    print()
    print(f"Updated master file: {output_file}")


if __name__ == "__main__":
    main()
