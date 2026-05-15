import re
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.bayut.com"
START_URL = f"{BASE_URL}/floorplans/dubai/arabian-ranches-2/"
OUTPUT_FILE = Path("data/ar2_bayut_floorplan_reference.csv")


def clean_number(value):
    if not value:
        return None

    match = re.search(r"[\d,]+", str(value))
    return int(match.group(0).replace(",", "")) if match else None


def fetch_soup(url):
    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            )
        },
        timeout=30,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def visible_lines(soup):
    text = soup.get_text("\n", strip=True)
    return [line.strip() for line in text.splitlines() if line.strip()]


def mode_or_first(values):
    values = [value for value in values if value]

    if not values:
        return None

    counts = Counter(values)
    return counts.most_common(1)[0][0]


def discover_community_urls():
    soup = fetch_soup(START_URL)
    community_urls = {}

    for link in soup.find_all("a", href=True):
        absolute_url = urljoin(BASE_URL, link["href"])
        path = urlparse(absolute_url).path

        if not path.startswith("/floorplans/dubai/arabian-ranches-2/"):
            continue

        parts = [part for part in path.split("/") if part]

        if len(parts) != 4:
            continue

        community_slug = parts[-1]
        community_name = link.get_text(" ", strip=True)

        if not community_name or community_name.lower() == "arabian ranches 2":
            continue

        community_urls[community_name] = absolute_url

    return community_urls


def discover_floorplan_links(community, community_url):
    soup = fetch_soup(community_url)
    floorplans = []

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "/floorplans/details-" not in href:
            continue

        text = link.get_text(" ", strip=True)
        match = re.search(
            r"(Type\s+[0-9A-Z]+)\s+(\d+)\s+bedrooms?,\s+(\d+)\s+bathrooms?",
            text,
            re.IGNORECASE,
        )

        if not match:
            continue

        floorplans.append({
            "community": community,
            "type": match.group(1).title().replace("M", "M").replace("E", "E"),
            "bedrooms": int(match.group(2)),
            "bathrooms": int(match.group(3)),
            "bayut_floorplan_url": urljoin(BASE_URL, href),
        })

    return floorplans


def infer_category(lines):
    for line in lines:
        lower_line = line.lower()

        if lower_line in {"villa", "townhouse"}:
            return lower_line

    return None


def extract_reference_sizes(lines):
    bua_values = []
    plot_values = []
    area_values = []

    for index, line in enumerate(lines):
        lower_line = line.lower()

        if lower_line in {"built-up:", "built up:", "bua:"}:
            for candidate in lines[index + 1:index + 4]:
                if "sqft" in candidate.lower():
                    bua_values.append(clean_number(candidate))
                    break

        if lower_line == "plot:":
            for candidate in lines[index + 1:index + 4]:
                if "sqft" in candidate.lower():
                    plot_values.append(clean_number(candidate))
                    break

        if lower_line == "area:":
            for candidate in lines[index + 1:index + 4]:
                if "sqft" in candidate.lower():
                    area_values.append(clean_number(candidate))
                    break

    return {
        "bua_reference_sqft": mode_or_first(bua_values),
        "plot_reference_sqft": mode_or_first(plot_values),
        "area_reference_sqft": mode_or_first(area_values),
    }


def enrich_floorplan(floorplan):
    soup = fetch_soup(floorplan["bayut_floorplan_url"])
    lines = visible_lines(soup)
    sizes = extract_reference_sizes(lines)

    floorplan["property_category"] = infer_category(lines)
    floorplan.update(sizes)
    floorplan["source"] = "Bayut floorplans"

    return floorplan


def main():
    community_urls = discover_community_urls()
    print(f"Discovered {len(community_urls)} communities.")

    if not community_urls and OUTPUT_FILE.exists():
        df = pd.read_csv(OUTPUT_FILE)
        print(
            "Bayut did not allow direct requests in this session. "
            f"Validated existing local reference file: {OUTPUT_FILE}"
        )
        print(f"Rows: {len(df)}")
        print(df.groupby(["community", "property_category"]).size().to_string())
        return

    rows = []

    for community, community_url in sorted(community_urls.items()):
        print(f"Fetching {community}: {community_url}")
        floorplans = discover_floorplan_links(community, community_url)
        print(f"  Found {len(floorplans)} floorplans.")

        for floorplan in floorplans:
            print(f"    {floorplan['type']} -> {floorplan['bayut_floorplan_url']}")
            rows.append(enrich_floorplan(floorplan))

    if not rows:
        raise RuntimeError(
            "No Bayut floorplan rows were collected and no existing local "
            f"reference file was found at {OUTPUT_FILE}."
        )

    df = pd.DataFrame(rows)
    df = df.sort_values(["community", "bedrooms", "bathrooms", "type"])
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"\nSaved {len(df)} floorplan reference rows to {OUTPUT_FILE}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
