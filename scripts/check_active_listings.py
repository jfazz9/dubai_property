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
    "cf-challenge",
    "access denied",
]
INACTIVE_TEXT_MARKERS = [
    "property is no longer available",
    "sorry, this villa for sale",
    "sorry, this villa for rent",
    "sorry, this apartment for sale",
    "sorry, this apartment for rent",
    "is no longer available",
    "listing is no longer available",
    "page not found",
    "property not found",
    "we can't find the page",
    "this property has been removed",
    "however we have hundreds of similar properties for you",
    "view similar properties",
    "property-gone-image",
    "property gone",
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


def browser_render_snapshot(driver):
    try:
        return driver.execute_script(
            """
            return {
                text: document.body ? document.body.innerText : "",
                html: document.documentElement ? document.documentElement.outerHTML : "",
                hasPrice: Boolean(document.querySelector('[data-testid="property-price-value"]')),
                hasAttributes: Boolean(document.querySelector('[data-testid="property-attributes-bedrooms"], [data-testid="property-attributes-size"]')),
                hasRegulatory: Boolean(document.querySelector('[data-testid="regulatory_reference"], [data-testid="regulatory_listed"]')),
                hasGoneCard: Boolean(document.querySelector('img[src*="property-gone-image"], a[href*="/en/search?"]'))
            };
            """
        ) or {}
    except Exception:
        return {}


def wait_for_rendered_state(driver, seconds=12):
    deadline = time.time() + max(0, seconds)
    last_snapshot = {}

    while True:
        snapshot = browser_render_snapshot(driver)
        last_snapshot = snapshot
        body_text = snapshot.get("text") or ""
        text = f"{body_text}\n{snapshot.get('html') or ''}"

        if looks_inactive_from_text(text) or snapshot.get("hasGoneCard"):
            return "inactive", snapshot

        if snapshot.get("hasPrice") and (snapshot.get("hasAttributes") or snapshot.get("hasRegulatory")):
            return "active", snapshot

        if looks_like_human_verification(body_text):
            return "human_verification", snapshot

        if time.time() >= deadline:
            break

        time.sleep(1)

    return "unknown", last_snapshot


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

    if status_code == 202 and not text.strip():
        return ActiveCheckResult(True, "unknown_empty_202", "HTTP 202 with empty body; likely client-rendered page")

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


def browser_check_url(driver, url, human_verification_wait=0, render_wait=12, debug_dir=None):
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        driver.get(url)
        WebDriverWait(driver, 20).until(lambda current_driver: current_driver.find_element(By.TAG_NAME, "body"))
        final_url = driver.current_url or url
        state, snapshot = wait_for_rendered_state(driver, seconds=render_wait)

        if human_verification_wait and state == "human_verification":
            print(f"Human Verification detected. You have {human_verification_wait} seconds to complete it in Chrome...")
            time.sleep(human_verification_wait)
            final_url = driver.current_url or url
            state, snapshot = wait_for_rendered_state(driver, seconds=render_wait)
    except Exception as exc:
        return ActiveCheckResult(True, "unknown_browser_error", str(exc))

    text = f"{snapshot.get('text') or ''}\n{snapshot.get('html') or ''}"

    if debug_dir:
        path = Path(debug_dir)
        path.mkdir(parents=True, exist_ok=True)
        listing_id = extract_listing_id(url) or re.sub(r"\W+", "_", url)[-60:]
        (path / f"{listing_id}_body.txt").write_text(snapshot.get("text") or "", encoding="utf-8")
        (path / f"{listing_id}_source.html").write_text(snapshot.get("html") or "", encoding="utf-8")
        (path / f"{listing_id}_meta.txt").write_text(
            f"state={state}\nfinal_url={final_url}\nkeys={sorted(snapshot.keys())}\n",
            encoding="utf-8",
        )

    if state == "human_verification" or looks_like_human_verification(text):
        return ActiveCheckResult(True, "unknown_human_verification", "human verification or bot challenge page")

    if state == "inactive" or looks_inactive_from_text(text):
        return ActiveCheckResult(False, "inactive_not_found_text", "rendered page says listing is unavailable")

    if looks_like_search_page(final_url):
        return ActiveCheckResult(False, "inactive_redirected_to_search", f"browser redirected to search page: {final_url}")

    original_id = extract_listing_id(url)
    final_id = extract_listing_id(final_url)
    if original_id and final_id and original_id != final_id:
        return ActiveCheckResult(False, "inactive_redirected_to_similar", f"browser redirected from ID {original_id} to {final_id}")

    if state == "active":
        return ActiveCheckResult(True, "active", "rendered listing page returned successfully")

    return ActiveCheckResult(True, "unknown_browser_unclear_page", f"browser could not find active or inactive rendered markers at {final_url}")


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


def should_confirm_with_browser(result):
    """Return True when the lightweight request is too risky to trust alone."""
    if result.status.startswith("unknown_"):
        return True

    # Property Finder pages are heavily client-rendered. The lightweight HTML can
    # contain a stale/placeholder "no longer available" block even when the
    # rendered browser page later hydrates into a live listing.
    return result.status == "inactive_not_found_text"


def run_active_checks_with_browser_fallback(master_df, limit=None, delay=0.0, checked_at=None, timeout=15, human_verification_wait=0, render_wait=12, debug_dir=None):
    try:
        from extract_listing_details import create_driver
    except ImportError as exc:
        raise RuntimeError("Browser fallback requires Selenium scraper dependencies.") from exc

    driver = create_driver()

    try:
        def checker(url):
            result = check_url(url, timeout=timeout)

            if should_confirm_with_browser(result):
                return browser_check_url(
                    driver,
                    url,
                    human_verification_wait=human_verification_wait,
                    render_wait=render_wait,
                    debug_dir=debug_dir,
                )

            return result

        return run_active_checks(master_df, checker=checker, limit=limit, delay=delay, checked_at=checked_at)
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Check active listing URLs and update master active status conservatively.")
    parser.add_argument("--purpose", choices=["sale", "rent"], help="Listing purpose. If omitted, you will be prompted.")
    parser.add_argument("--input", help="Master CSV to check. Defaults to output/<purpose>/listing_details_master.csv.")
    parser.add_argument("--output", help="Output CSV. Defaults to overwriting the input master CSV.")
    parser.add_argument("--limit", type=int, help="Only check the first N active listings.")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between URL checks.")
    parser.add_argument("--timeout", type=int, default=15, help="Request timeout in seconds.")
    parser.add_argument("--deep-unclear", action="store_true", help="Use a browser/Selenium fallback only for unclear lightweight checks.")
    parser.add_argument("--verification-wait", type=int, default=0, help="Seconds to wait for manual Human Verification during browser fallback.")
    parser.add_argument("--render-wait", type=int, default=12, help="Seconds to wait for rendered listing/gone markers during browser fallback.")
    parser.add_argument("--debug-dir", help="Directory to save rendered browser body/source snapshots for unclear pages.")
    parser.add_argument("--dry-run", action="store_true", help="Check URLs and print a summary without writing the master file.")
    args = parser.parse_args()

    purpose = normalize_purpose(args.purpose) if args.purpose else prompt_for_purpose()
    input_file = Path(args.input) if args.input else master_file(purpose)
    output_file = Path(args.output) if args.output else input_file

    if not input_file.exists():
        raise FileNotFoundError(f"Missing master file: {input_file}")

    master_df = pd.read_csv(input_file)

    if args.deep_unclear:
        updated_df, results_df = run_active_checks_with_browser_fallback(
            master_df,
            limit=args.limit,
            delay=args.delay,
            timeout=args.timeout,
            human_verification_wait=args.verification_wait,
            render_wait=args.render_wait,
            debug_dir=args.debug_dir,
        )
    else:
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
