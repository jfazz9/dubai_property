import json
import re
import time
import traceback
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


INPUT_FILE = Path("output/property_urls.json")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

RUNS_DIR = OUTPUT_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)

MASTER_FILE = OUTPUT_DIR / "listing_details_master.csv"

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
RUN_FILE = RUNS_DIR / f"listing_details_{timestamp}.csv"


def create_driver():
    chrome_options = Options()
    chrome_options.page_load_strategy = "eager"
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-extensions")

    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(
        service=service,
        options=chrome_options
    )
    driver.set_page_load_timeout(45)

    return driver


def clean_number(value):
    if not value:
        return None

    value = str(value).replace(",", "")
    numbers = re.findall(r"\d+", value)

    if not numbers:
        return None

    return int(numbers[0])


def safe_get_text(driver, selector):
    try:
        return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
    except Exception:
        return None


def first_text(driver, selectors):
    for selector in selectors:
        value = safe_get_text(driver, selector)

        if value:
            return value

    return None


def get_field_after_label(driver, label_testid):
    try:
        label = driver.find_element(By.CSS_SELECTOR, f'[data-testid="{label_testid}"]')
        value = label.find_element(By.XPATH, "following-sibling::dd[1]")
        return value.text.strip()
    except Exception:
        return None


def get_dom_snapshot(driver):
    try:
        return driver.execute_script(
            """
            const text = (selector) => {
                const element = document.querySelector(selector);
                return element ? element.innerText.trim() : null;
            };

            const attr = (selector, name) => {
                const element = document.querySelector(selector);
                return element ? element.getAttribute(name) : null;
            };

            const regulatoryValue = (testId) => {
                const label = document.querySelector(`[data-testid="${testId}"]`);
                if (!label) return null;
                const value = label.nextElementSibling;
                return value ? value.innerText.trim() : null;
            };

            return {
                price_text: text('[data-testid="property-price-value"]'),
                bedrooms_text: text('[data-testid="property-attributes-bedrooms"]'),
                bathrooms_text: text('[data-testid="property-attributes-bathrooms"]'),
                size_text: text('[data-testid="property-attributes-size"]'),
                size_sqm_title: attr('[data-testid="property-attributes-size"] span', 'title'),
                price_per_area_text: text('[data-testid="property-attributes-price-per-area"]'),
                agent_name: text('[data-testid="property-detail-agent-name"]'),
                agency_name: regulatoryValue('regulatory_authority_name'),
                listed_age: regulatoryValue('regulatory_listed'),
                reference: regulatoryValue('regulatory_reference')
            };
            """
        )
    except Exception:
        return {}


def extract_price_from_body(text):
    match = re.search(r"AED\s*([\d,]+)", text, re.IGNORECASE)
    return clean_number(match.group(1)) if match else None


def extract_beds_from_body(text):
    match = re.search(r"(\d+)\s*(?:bed|beds|bedroom|bedrooms)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_baths_from_body(text):
    match = re.search(r"(\d+)\s*(?:bath|baths|bathroom|bathrooms)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_sqft_values(text):
    matches = re.findall(r"([\d,]+)\s*sqft", text, re.IGNORECASE)
    return [clean_number(m) for m in matches if clean_number(m)]


def visible_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_header_metrics(text):
    lines = visible_lines(text)

    for index, line in enumerate(lines):
        if line.lower() != "search":
            continue

        if index + 4 >= len(lines):
            continue

        price = clean_number(lines[index + 1])
        beds = clean_number(lines[index + 2])
        baths = clean_number(lines[index + 3])
        size = clean_number(lines[index + 4])

        if price and size and "sqft" in lines[index + 4].lower():
            return {
                "price": price,
                "bedrooms": beds,
                "bathrooms": baths,
                "property_size_sqft": size,
            }

    return {}


def extract_agent_and_agency(text):
    lines = visible_lines(text)

    for index, line in enumerate(lines):
        if line.lower() != "call":
            continue

        agent_name = None
        agency_name = None

        for previous in range(index - 1, -1, -1):
            candidate = lines[previous]

            if candidate.lower() in {"sold for", "rented for"}:
                continue

            if re.search(r"\d+\s*beds?\s+\w+\s+in\s+", candidate, re.IGNORECASE):
                continue

            agent_name = candidate
            break

        for candidate in lines[index + 1:]:
            lower_candidate = candidate.lower()

            if lower_candidate in {"whatsapp", "call"}:
                continue

            if lower_candidate.startswith("usually responds"):
                continue

            if lower_candidate.startswith("own this property"):
                break

            if lower_candidate in {"no ratings"}:
                continue

            if re.match(r"^\d+(?:\.\d+)?$", candidate):
                continue

            if re.match(r"^\d+\s+ratings?$", candidate, re.IGNORECASE):
                continue

            if re.match(r"^[a-z]+(?:,\s*[a-z]+)*$", candidate, re.IGNORECASE):
                continue

            agency_name = candidate
            break

        if agent_name or agency_name:
            return agent_name, agency_name

    return None, None


def extract_agency_from_description(description):
    if not description:
        return None

    agency_patterns = [
        r"\b[A-Za-z0-9][A-Za-z0-9&.\- ]+\s+Real Estate(?: Broker| Brokers| Brokerage)?(?: LLC| L\.L\.C)?\b",
        r"\b[A-Za-z0-9][A-Za-z0-9&.\- ]+\s+Luxury Properties\b",
        r"\b[A-Za-z0-9][A-Za-z0-9&.\- ]+\s+Properties(?: LLC| L\.L\.C)?\b",
        r"\b[A-Za-z0-9][A-Za-z0-9&.\- ]+\s+Homes\b",
        r"\b[A-Za-z0-9][A-Za-z0-9&.\- ]+\s*&\s+Co\.?\b",
    ]

    for line in visible_lines(description):
        for pattern in agency_patterns:
            match = re.search(pattern, line)

            if match:
                candidate = match.group(0).strip()
                candidate = re.sub(r"^.*?\bat\s+", "", candidate, flags=re.IGNORECASE)
                candidate = re.sub(r"^.*?\band\s+", "", candidate, flags=re.IGNORECASE)

                if candidate.lower() in {"holiday homes", "deluxe & modern holiday homes"}:
                    continue

                return candidate

    return None


def extract_description(text):
    lines = visible_lines(text)

    description_markers = [
        index for index, line in enumerate(lines)
        if line == "Description"
    ]

    if description_markers:
        start = description_markers[-1] + 1
    else:
        try:
            start = lines.index("Mortgage Calculator") + 1
        except ValueError:
            return None

    end = len(lines)

    for marker in ["See full description", "Amenities", "Transactions for Similar Properties"]:
        if marker in lines[start:]:
            marker_index = lines.index(marker, start)
            end = min(end, marker_index)

    description_lines = [
        line for line in lines[start:end]
        if line.lower() not in {"logo", "logo-en"}
    ]

    description = "\n".join(description_lines).strip()
    return description or None


def build_description_json(description):
    if not description:
        return None

    lines = visible_lines(description)

    return json.dumps(
        {
            "text": description,
            "lines": lines,
        },
        ensure_ascii=False,
    )


def extract_amenities(text):
    lines = visible_lines(text)
    amenity_markers = [index for index, line in enumerate(lines) if line == "Amenities"]

    if len(amenity_markers) < 2:
        return []

    start = amenity_markers[-1] + 1
    end = len(lines)

    for index in range(start, len(lines)):
        if lines[index] in {"Transactions for Similar Properties", "Provided by"}:
            end = index
            break

        if lines[index] == "Call":
            end = max(start, index - 1)
            break

    return lines[start:end]


def extract_listed_age(text):
    patterns = [
        r"^Listed\s+(?:about\s+)?\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago$",
        r"^Listed\s+today$",
        r"^Listed\s+yesterday$",
        r"^Listed\s+new$",
        r"^New$",
    ]

    for line in visible_lines(text):
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)

            if match:
                return match.group(0)

    return None


def calculate_listed_date(listed_age, scraped_datetime):
    if not listed_age:
        return None

    value = listed_age.strip().lower()

    if value in {"new", "listed new", "listed today"}:
        return scraped_datetime.date().isoformat()

    if value == "listed yesterday":
        return (scraped_datetime.date() - timedelta(days=1)).isoformat()

    match = re.search(
        r"(?:listed\s+)?(?:about\s+)?(\d+)\s+"
        r"(minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago",
        value,
        re.IGNORECASE,
    )

    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2).lower()

    if unit.startswith("minute") or unit.startswith("hour"):
        delta = timedelta(days=0)
    elif unit.startswith("day"):
        delta = timedelta(days=amount)
    elif unit.startswith("week"):
        delta = timedelta(days=amount * 7)
    elif unit.startswith("month"):
        delta = timedelta(days=amount * 30)
    elif unit.startswith("year"):
        delta = timedelta(days=amount * 365)
    else:
        return None

    return (scraped_datetime.date() - delta).isoformat()


def is_search_results_page(title, text):
    lower_title = title.lower()
    lower_text = text.lower()

    return (
        "villas for sale in" in lower_title
        and "create alert" in lower_text
        and "filters" in lower_text
        and "map" in lower_text
    )


def extract_villa_type(text):
    patterns = [
        r"\btype\s*([0-9]+[a-zA-Z]?)\b",
        r"\btype\s*(i{1,3}|iv|v|vi)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return f"Type {match.group(1).upper()}"

    return None


def extract_bua_from_description(text):
    patterns = [
        r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft\.?\s*)?BUA",
        r"BUA\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"built\s*up\s*area\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            value = clean_number(match.group(1))

            if value and value >= 1000:
                return value

    return None


def extract_plot_from_description(text):
    patterns = [
        r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft\.?\s*)?Plot",
        r"Plot\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"Plot\s*Size\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            value = clean_number(match.group(1))

            if value and value >= 1000:
                return value

    return None


def open_full_description(driver):
    try:
        button = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//button[contains(., 'See full description')]"
            ))
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            button
        )

        time.sleep(1.5)

        driver.execute_script(
            "arguments[0].click();",
            button
        )

        print("Opened full description.")
        time.sleep(2)

    except Exception:
        print("No full description button found.")


def load_lazy_sections(driver):
    try:
        for _ in range(5):
            driver.execute_script("window.scrollBy(0, 900);")
            time.sleep(0.7)

        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

    except Exception:
        pass


def load_agent_section(driver):
    selectors = [
        '[data-testid="property-detail-agent-name"]',
        '[data-testid="agent-link-with-name"]',
        '[data-testid="agent-link-with-image"]',
    ]

    try:
        provided_by = driver.find_elements(By.XPATH, "//*[normalize-space()='Provided by']")

        if provided_by:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                provided_by[-1],
            )
            time.sleep(1)

        for _ in range(8):
            for selector in selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)

                for element in elements:
                    text = element.text.strip()

                    if text:
                        return text

                    alt_text = element.get_attribute("alt")

                    if alt_text:
                        return alt_text.replace("Agent ", "").strip()

            driver.execute_script("window.scrollBy(0, 700);")
            time.sleep(1)

    except Exception:
        pass

    return None


def load_regulatory_section(driver):
    try:
        for _ in range(12):
            labels = driver.find_elements(By.CSS_SELECTOR, '[data-testid="regulatory_listed"]')

            if labels:
                value = get_field_after_label(driver, "regulatory_listed")

                if value:
                    return value

            driver.execute_script("window.scrollBy(0, 900);")
            time.sleep(0.8)

    except Exception:
        pass

    return None


def save_progress(results):
    run_df = pd.DataFrame(results)

    # Always save current run snapshot
    run_df.to_csv(RUN_FILE, index=False)

    # Update master by URL, preserving old rows from previous runs
    if MASTER_FILE.exists():
        master_df = pd.read_csv(MASTER_FILE)

        combined_df = pd.concat([master_df, run_df], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=["url"], keep="last")
    else:
        combined_df = run_df

    combined_df.to_csv(MASTER_FILE, index=False)


def extract_listing_details(driver, url):
    print(f"Opening listing: {url}")

    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    time.sleep(4)

    open_full_description(driver)

    time.sleep(2)
    load_lazy_sections(driver)
    loaded_agent_name = load_agent_section(driver)

    body = driver.find_element(By.TAG_NAME, "body").text
    title = driver.title

    if "human verification" in title.lower() or "human verification" in body.lower():
        raise Exception("Property Finder returned Human Verification instead of listing details")

    if is_search_results_page(title, body):
        raise Exception("Property Finder returned a search results page instead of the listing details page")

    header_metrics = extract_header_metrics(body)

    price_text = first_text(driver, [
        '[data-testid="property-price-value"]',
        '[data-testid="price"]',
    ])
    beds_text = first_text(driver, [
        '[data-testid="property-attributes-bedrooms"]',
        '[data-testid="property-bedrooms"]',
    ])
    baths_text = first_text(driver, [
        '[data-testid="property-attributes-bathrooms"]',
        '[data-testid="property-bathrooms"]',
    ])
    size_text = first_text(driver, [
        '[data-testid="property-attributes-size"] span',
        '[data-testid="property-attributes-size"]',
        '[data-testid="property-size"]',
    ])

    price = clean_number(price_text) if price_text else None
    price = price or header_metrics.get("price") or extract_price_from_body(body)

    beds = clean_number(beds_text) if beds_text else None
    beds = beds or header_metrics.get("bedrooms") or extract_beds_from_body(body)

    baths = clean_number(baths_text) if baths_text else None
    baths = baths or header_metrics.get("bathrooms") or extract_baths_from_body(body)

    property_size = clean_number(size_text) if size_text else None
    property_size = property_size or header_metrics.get("property_size_sqft")

    detected_type_from_description = extract_villa_type(body)
    bua_from_description = extract_bua_from_description(body)
    plot_from_description = extract_plot_from_description(body)

    sqft_values = extract_sqft_values(body)

    fallback_sqft_1 = sqft_values[0] if len(sqft_values) >= 1 else None
    fallback_sqft_2 = sqft_values[1] if len(sqft_values) >= 2 else None

    agent_name = first_text(driver, [
        '[data-testid="property-detail-agent-name"]',
        '[data-testid="agent-name"]',
        '[data-testid="property-agent-name"]',
    ])
    agent_name = agent_name or loaded_agent_name
    agency_name = get_field_after_label(driver, "regulatory_authority_name")
    listed_age = get_field_after_label(driver, "regulatory_listed")

    fallback_agent_name, fallback_agency_name = extract_agent_and_agency(body)
    agent_name = agent_name or fallback_agent_name
    agency_name = agency_name or fallback_agency_name
    listed_age = listed_age or extract_listed_age(body)

    description = extract_description(body)
    description_json = build_description_json(description)
    amenities = extract_amenities(body)
    agency_name = agency_name or extract_agency_from_description(description)

    scraped_datetime = datetime.now()
    scraped_at = scraped_datetime.strftime("%Y-%m-%d %H:%M:%S")
    listed_date = calculate_listed_date(listed_age, scraped_datetime)

    time.sleep(7)

    return {
        "url": url,
        "scraped_at": scraped_at,
        "title": title,
        "price": price,
        "bedrooms": beds,
        "bathrooms": baths,
        "property_size_sqft": property_size,
        "detected_type_from_description": detected_type_from_description,
        "bua_from_description": bua_from_description,
        "plot_from_description": plot_from_description,
        "agent_name": agent_name,
        "agency_name": agency_name,
        "listed_age": listed_age,
        "listed_date": listed_date,
        "description": description,
        "description_json": description_json,
        "amenities": amenities,
        "fallback_sqft_1": fallback_sqft_1,
        "fallback_sqft_2": fallback_sqft_2,
        "raw_sqft_values": sqft_values,
        "full_page_text": body,
        "page_text_sample": body[:1500],
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        urls = json.load(f)

    print(f"Loaded {len(urls)} URLs.")

    driver = create_driver()
    results = []

    driver.get(urls[0])
    input("Complete the bot check in Chrome, then press Enter here to continue...")

    try:
        for index, url in enumerate(urls, start=1):
            print(f"\n[{index}/{len(urls)}] Extracting: {url}")

            try:
                data = extract_listing_details(driver, url)
                results.append(data)

                save_progress(results)

                print("Saved progress.")
                print({
                    "url": data["url"],
                    "price": data["price"],
                    "bedrooms": data["bedrooms"],
                    "bathrooms": data["bathrooms"],
                    "property_size_sqft": data["property_size_sqft"],
                    "detected_type": data["detected_type_from_description"],
                    "bua": data["bua_from_description"],
                    "plot": data["plot_from_description"],
                    "agent": data["agent_name"],
                    "agency": data["agency_name"],
                    "listed": data["listed_age"],
                })

            except Exception as e:
                print(f"Failed on URL: {url}")
                print(type(e).__name__)
                print(str(e))

    except Exception:
        traceback.print_exc()

    finally:
        driver.quit()

    print(f"\nFinished. Saved {len(results)} listings to {RUN_FILE} and updated master file {MASTER_FILE}.")


if __name__ == "__main__":
    main()
