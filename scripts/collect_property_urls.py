import argparse
import json
import time
import traceback

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

from notifications import attention_beep
from workflow_paths import ensure_purpose_dirs, prompt_for_purpose, urls_file

START_URLS = {
    "sale": "https://www.propertyfinder.ae/en/buy/properties-for-sale.html",
    "rent": "https://www.propertyfinder.ae/en/rent/properties-for-rent.html",
}


def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-extensions")

    service = Service(ChromeDriverManager().install())

    return webdriver.Chrome(
        service=service,
        options=chrome_options
    )


def safe_click(driver, element):
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        element
    )
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", element)


def save_urls(urls, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(urls, f, indent=4)

    print(f"URLs saved to: {output_file}")


def wait_for_manual_find(seconds, beep=True):
    attention_beep(beep)
    print(f"Click Find / complete any bot check in Chrome. Waiting {seconds} seconds before scanning results...")

    for remaining in range(seconds, 0, -10):
        print(f"{remaining} seconds remaining...")
        time.sleep(min(10, remaining))


def collect_property_urls(search_location, purpose, output_file, manual_wait, beep=True):
    driver = create_driver()
    all_urls = []

    try:
        driver.get(START_URLS[purpose])
        time.sleep(5)

        inputs = driver.find_elements(By.TAG_NAME, "input")
        print(f"Inputs found: {len(inputs)}")

        search_box = None

        for i, inp in enumerate(inputs):
            try:
                print(
                    i,
                    "displayed=", inp.is_displayed(),
                    "enabled=", inp.is_enabled(),
                    "placeholder=", inp.get_attribute("placeholder"),
                    "type=", inp.get_attribute("type")
                )

                if inp.is_displayed() and inp.is_enabled():
                    search_box = inp
                    break

            except Exception:
                continue

        if search_box is None:
            raise Exception("No visible enabled input found")

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            search_box
        )

        time.sleep(1)

        driver.execute_script("arguments[0].click();", search_box)
        time.sleep(1)

        actions = ActionChains(driver)

        actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        time.sleep(0.3)

        for char in search_location:
            actions.send_keys(char).perform()
            time.sleep(0.08)

        print(f"Entered search location: {search_location}")
        time.sleep(4)

        suggestions = driver.find_elements(
            By.XPATH,
            "//button[contains(@data-testid, 'multi-selection-autocomplete-template-suggestion-button')]"
        )

        print(f"Suggestions found: {len(suggestions)}")

        found_location = False

        for suggestion in suggestions:
            text = suggestion.text.strip()
            print(f"Suggestion found: {text}")

            if search_location.lower() in text.lower() and "arabian ranches 2" in text.lower():
                safe_click(driver, suggestion)
                found_location = True
                print(f"Selected: {text}")
                break

        if not found_location:
            print(f"Could not automatically select {search_location}, Arabian Ranches 2.")
            attention_beep(beep)
            input("Select the correct location result manually, then press Enter here...")

        wait_for_manual_find(manual_wait, beep)

        time.sleep(5)

        print("Current URL:", driver.current_url)
        print("Page title:", driver.title)

        #iterate through pages and collect property URLs

        
        page = 1
        previous_url = None

        while True:
            print(f"\nScanning page {page}...")
            current_url = driver.current_url

            if page > 1 and current_url == previous_url:
                print("Page did not change. Stopping to avoid loop.")
                break

            previous_url = current_url

            time.sleep(5)

            #identify property card links and collect URLs
            links = driver.find_elements(
                By.CSS_SELECTOR,
                'a[data-testid="property-card-link"]'
            )

            print(f"Property card links found: {len(links)}")

            page_urls = []

            for link in links:
                href = link.get_attribute("href")

                if not href:
                    continue

                if href in page_urls:
                    continue

                page_urls.append(href)

            for url in page_urls:
                if url not in all_urls:
                    all_urls.append(url)

            print(f"Collected {len(page_urls)} URLs on page {page}.")
            print(f"Total unique URLs: {len(all_urls)}")

            save_urls(all_urls, output_file)

            # collected urls, now try to go to next page
            try:
                next_link = driver.find_element(
                    By.CSS_SELECTOR,
                    'a[data-testid="pagination-page-next-link"]'
                )

                next_href = next_link.get_attribute("href")

                if not next_href:
                    raise Exception("Next link has no href")

                print(f"Going to next page: {next_href}")

                driver.get(next_href)

                page += 1
                time.sleep(5)

            except Exception:
                print("No more pages found. Finished.")
                break


    except Exception as e:
        print("Main error:")
        print(type(e).__name__)
        print(str(e))
        traceback.print_exc()

    finally:
        driver.quit()

    return all_urls


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Property Finder listing URLs.")
    parser.add_argument("--purpose", choices=["sale", "rent"], help="Listing purpose. If omitted, you will be prompted.")
    parser.add_argument("--location", help="Location to search for, for example 'Arabian Ranches 2'.")
    parser.add_argument("--output", help="Output JSON file. Defaults to output/<purpose>/property_urls.json.")
    parser.add_argument(
        "--manual-wait",
        type=int,
        default=60,
        help="Seconds to wait after selecting the location so you can click Find and complete bot checks.",
    )
    parser.add_argument("--no-beep", action="store_true", help="Disable audible prompts for manual actions.")
    args = parser.parse_args()

    purpose = args.purpose or prompt_for_purpose()
    search_location = args.location or input("Enter the location to search for: ")
    ensure_purpose_dirs(purpose)
    output_file = urls_file(purpose) if not args.output else args.output

    urls = collect_property_urls(search_location, purpose, output_file, args.manual_wait, not args.no_beep)


    print(f"\nFinal URL count: {len(urls)}")


