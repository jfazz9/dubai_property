import argparse
import json
import random
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from extract_listing_details import (
    create_driver,
    get_dom_snapshot,
    get_field_after_label,
    is_search_results_page,
    load_agent_section,
    load_lazy_sections,
    load_regulatory_section,
    open_full_description,
)
from notifications import attention_beep
from workflow_paths import ensure_purpose_dirs, logs_dir, master_file, prompt_for_purpose, raw_dir, timestamp, urls_file


RUN_TIMESTAMP = timestamp()


def classify_page(title, body):
    if "human verification" in title.lower() or "human verification" in body.lower():
        return "human_verification"

    if is_search_results_page(title, body):
        return "search_results_page"

    return "ok"


def save_progress(results, output_file):
    pd.DataFrame(results).to_csv(output_file, index=False)


def append_log(log_file, message):
    timestamp_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp_text}] {message}"
    print(line)

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_existing_results(output_file):
    if not output_file.exists():
        return []

    existing_df = pd.read_csv(output_file)
    return existing_df.to_dict("records")


def completed_urls_from_results(results):
    return {
        row.get("url")
        for row in results
        if row.get("url") and row.get("page_status") in {"ok", "search_results_page", "human_verification"}
    }


def latest_matching_raw_file(purpose, urls):
    current_raw_dir = raw_dir(purpose)
    raw_files = sorted(current_raw_dir.glob("listing_pages_*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    input_urls = set(urls)

    for raw_file in raw_files:
        try:
            rows = load_existing_results(raw_file)
        except Exception:
            continue

        completed_urls = completed_urls_from_results(rows)

        if not completed_urls:
            continue

        overlap = completed_urls & input_urls

        if overlap:
            return raw_file

    return None


def load_master_urls(purpose):
    current_master_file = master_file(purpose)

    if not current_master_file.exists():
        return set()

    master_df = pd.read_csv(current_master_file, usecols=["url"])
    return set(master_df["url"].dropna().astype(str))


def delay_between_listings(delay_min, delay_max, log_file):
    if delay_max <= 0:
        return

    delay_min = max(0, delay_min)
    delay_max = max(delay_min, delay_max)
    seconds = random.uniform(delay_min, delay_max)
    append_log(log_file, f"Waiting {seconds:.1f} seconds before next listing.")
    time.sleep(seconds)


def wait_for_manual_bot_check(seconds, beep=True):
    attention_beep(beep)
    print(f"Complete the bot check in Chrome. Waiting {seconds} seconds before continuing...")

    for remaining in range(seconds, 0, -10):
        print(f"{remaining} seconds remaining...")
        time.sleep(min(10, remaining))


def page_has_human_verification(driver):
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        body = ""

    return "human verification" in driver.title.lower() or "human verification" in body.lower()


def wait_for_human_verification_clear(driver, url, seconds, max_attempts, log_file, beep=True):
    for attempt in range(1, max_attempts + 1):
        if not page_has_human_verification(driver):
            return True

        append_log(
            log_file,
            f"Human Verification detected for {url}. Attempt {attempt}/{max_attempts}.",
        )
        wait_for_manual_bot_check(seconds, beep)
        driver.get(url)
        WebDriverWait(driver, 20).until(lambda current_driver: current_driver.find_element(By.TAG_NAME, "body"))
        time.sleep(3)

    return not page_has_human_verification(driver)


def scrape_listing_page(driver, url, verification_wait, verification_retries, log_file, beep=True):
    print(f"Opening listing: {url}")

    driver.get(url)
    WebDriverWait(driver, 20).until(lambda current_driver: current_driver.find_element(By.TAG_NAME, "body"))
    time.sleep(2)

    wait_for_human_verification_clear(
        driver,
        url,
        verification_wait,
        verification_retries,
        log_file,
        beep,
    )

    time.sleep(4)
    open_full_description(driver)
    time.sleep(2)
    load_lazy_sections(driver)
    agent_name = load_agent_section(driver)
    listed_age = load_regulatory_section(driver) or get_field_after_label(driver, "regulatory_listed")
    dom_snapshot = get_dom_snapshot(driver)

    body = driver.find_element(By.TAG_NAME, "body").text
    title = driver.title
    status = classify_page(title, body)

    return {
        "url": url,
        "current_url": driver.current_url,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": title,
        "page_status": status,
        "price_dom": dom_snapshot.get("price_text"),
        "bedrooms_dom": dom_snapshot.get("bedrooms_text"),
        "bathrooms_dom": dom_snapshot.get("bathrooms_text"),
        "size_dom": dom_snapshot.get("size_text"),
        "size_sqm_dom": dom_snapshot.get("size_sqm_title"),
        "price_per_area_dom": dom_snapshot.get("price_per_area_text"),
        "agent_name_dom": dom_snapshot.get("agent_name") or agent_name,
        "agent_profile_url_dom": dom_snapshot.get("agent_profile_url"),
        "agent_rating_dom": dom_snapshot.get("agent_rating"),
        "agent_review_count_dom": dom_snapshot.get("agent_review_count"),
        "agent_is_superagent_dom": dom_snapshot.get("agent_is_superagent"),
        "agent_properties_count_dom": dom_snapshot.get("agent_properties_count"),
        "agent_closed_deals_dom": dom_snapshot.get("agent_closed_deals"),
        "agent_response_time_dom": dom_snapshot.get("agent_response_time"),
        "agent_total_value_dom": dom_snapshot.get("agent_total_value"),
        "agency_name_dom": dom_snapshot.get("agency_name"),
        "listed_age_dom": dom_snapshot.get("listed_age") or listed_age,
        "reference_dom": dom_snapshot.get("reference"),
        "full_page_text": body,
        "page_text_sample": body[:1500],
    }


def main():
    parser = argparse.ArgumentParser(description="Scrape raw Property Finder listing pages.")
    parser.add_argument("--purpose", choices=["sale", "rent"], help="Listing purpose. If omitted, you will be prompted.")
    parser.add_argument("--input", help="JSON file containing listing URLs. Defaults to output/<purpose>/property_urls.json.")
    parser.add_argument("--output", help="CSV file for raw page output.")
    parser.add_argument("--fresh-output", action="store_true", help="Always create a new raw output file instead of auto-resuming the latest partial run.")
    parser.add_argument(
        "--manual-wait",
        type=int,
        default=20,
        help="Seconds to wait after opening Chrome so you can complete the manual bot check.",
    )
    parser.add_argument("--delay-min", type=float, default=5, help="Minimum seconds to wait between listing pages.")
    parser.add_argument("--delay-max", type=float, default=10, help="Maximum seconds to wait between listing pages.")
    parser.add_argument("--verification-wait", type=int, default=60, help="Seconds to wait if Human Verification appears during a listing scrape.")
    parser.add_argument("--verification-retries", type=int, default=2, help="Number of times to wait/retry a listing after Human Verification appears.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing output file and scrape every URL again.")
    parser.add_argument(
        "--scrape-mode",
        choices=["new-only", "all"],
        default="new-only",
        help="new-only scrapes URLs not already in the master DB. all refreshes every collected URL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show how many URLs would be scraped without opening Chrome.")
    parser.add_argument("--no-beep", action="store_true", help="Disable audible prompts for manual bot checks.")
    parser.add_argument("--log", help="Path to write a scraper run log.")
    args = parser.parse_args()

    purpose = args.purpose or prompt_for_purpose()
    ensure_purpose_dirs(purpose)

    input_file = Path(args.input) if args.input else urls_file(purpose)
    if not input_file.exists():
        raise FileNotFoundError(f"Missing input file: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        urls = json.load(f)

    if args.output:
        output_file = Path(args.output)
    elif args.fresh_output or args.scrape_mode == "all":
        output_file = raw_dir(purpose) / f"listing_pages_{RUN_TIMESTAMP}.csv"
    else:
        output_file = latest_matching_raw_file(purpose, urls) or raw_dir(purpose) / f"listing_pages_{RUN_TIMESTAMP}.csv"

    log_file = Path(args.log) if args.log else logs_dir(purpose) / f"scrape_listing_pages_{RUN_TIMESTAMP}.log"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    append_log(log_file, f"Loaded {len(urls)} URLs.")
    append_log(log_file, f"Raw output file: {output_file}")
    append_log(log_file, f"Delay between listings: {args.delay_min}-{args.delay_max} seconds.")
    append_log(log_file, f"Scrape mode: {args.scrape_mode}.")

    results = [] if args.no_resume else load_existing_results(output_file)
    scraped_urls = completed_urls_from_results(results)
    master_urls = load_master_urls(purpose) if args.scrape_mode == "new-only" else set()
    urls_to_scrape = [url for url in urls if url not in master_urls]
    pending_urls = [url for url in urls_to_scrape if url not in scraped_urls]

    if results:
        append_log(log_file, f"Resume mode loaded {len(results)} existing rows from output.")

    if master_urls:
        append_log(log_file, f"Master DB contains {len(master_urls)} URLs. Skipping {len(urls) - len(urls_to_scrape)} already-known URLs.")

    if args.dry_run:
        append_log(log_file, f"Dry run complete. Would scrape {len(pending_urls)} of {len(urls)} loaded URLs.")
        return

    if not pending_urls:
        append_log(log_file, "No URLs to scrape after applying scrape mode. Nothing to do.")
        append_log(log_file, f"Finished. Saved {len(results)} raw pages to {output_file}.")
        return

    driver = create_driver()

    try:
        driver.get(pending_urls[0])
        wait_for_manual_bot_check(args.manual_wait, not args.no_beep)

        for index, url in enumerate(pending_urls, start=1):
            if url in scraped_urls:
                append_log(log_file, f"[{index}/{len(pending_urls)}] Skipping already scraped URL: {url}")
                continue

            append_log(log_file, f"[{index}/{len(pending_urls)}] Scraping raw page: {url}")

            try:
                data = scrape_listing_page(
                    driver,
                    url,
                    args.verification_wait,
                    args.verification_retries,
                    log_file,
                    not args.no_beep,
                )
                results.append(data)
                scraped_urls.add(url)
                save_progress(results, output_file)

                append_log(
                    log_file,
                    f"Saved url={data['url']} status={data['page_status']} title={data['title']}",
                )

            except Exception as e:
                append_log(log_file, f"Failed on URL: {url}")
                append_log(log_file, f"{type(e).__name__}: {str(e)}")
                traceback.print_exc()

            delay_between_listings(args.delay_min, args.delay_max, log_file)

    finally:
        driver.quit()

    append_log(log_file, f"Finished. Saved {len(results)} raw pages to {output_file}.")


if __name__ == "__main__":
    main()
