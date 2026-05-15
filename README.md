# Dubai Property Detector

Tools for collecting Property Finder listing data, cleaning it into database-ready CSV files, and predicting Arabian Ranches 2 villa types using local floorplan reference data.

## Project Structure

```text
data/
  ar2_bayut_floorplan_reference.csv   Local AR2 floorplan reference table
  ar2_type_enrichment.csv             Manual knowledge notes by community/type

output/
  sale/
    property_urls.json                Sale listing URLs
    raw/                              Sale raw page scrape CSVs
    processed/                        Sale clean processed CSVs
    predicted/                        Sale predicted CSVs
    listing_details_master.csv        Sale final master file
    price_history.csv                 Sale price-change history
  rent/
    property_urls.json                Rental listing URLs
    raw/                              Rental raw page scrape CSVs
    processed/                        Rental clean processed CSVs
    predicted/                        Rental predicted CSVs
    listing_details_master.csv        Rental final master file
    price_history.csv                 Rental price-change history

scripts/
  collect_property_urls.py            Collects Property Finder listing URLs
  scrape_listing_pages.py             Scrapes raw listing pages
  process_listing_data.py             Converts raw pages into clean listing rows
  predict_villa_type.py               Predicts AR2 villa type from processed rows
  check_active_listings.py            Checks active master URLs without rescraping full details
  match_enquiry.py                    Matches an enquiry against the master database
  webapp.py                           Local browser app for prompt-based matching
  build_floorplan_reference_candidates.py
                                      Builds review candidates from live listing evidence
  build_bayut_floorplan_reference.py  Validates/builds local Bayut floorplan reference
  extract_listing_details.py          Shared Selenium/parsing helpers

tests/
  test_processing.py                   Processing/parser tests
  test_prediction.py                   Villa-type prediction tests
```

## Setup

From the project root:

```powershell
cd C:\Users\fazz0\Documents\python_projects\dubai\property_detector
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Workflow

All main workflow scripts accept:

```powershell
--purpose sale
--purpose rent
```

If `--purpose` is omitted, the script prompts:

```text
Listing purpose [sale/rent] (default: sale):
```

### Suggested Weekly Operating Flow

Use this as a practical rhythm rather than a strict rule. The goal is to keep the master database useful without constantly triggering Property Finder verification.

#### Monday Evening: Fresh Market Scan

Run a fresh scan after the start-of-week listing activity has settled. This catches new instructions, refreshed stock, and price changes that agents push after the weekend.

For a full Arabian Ranches 2 sale scan:

```powershell
python scripts\collect_property_urls.py --purpose sale --location "Arabian Ranches 2" --manual-wait 20
python scripts\scrape_listing_pages.py --purpose sale --manual-wait 20
python scripts\process_listing_data.py --purpose sale
python scripts\predict_villa_type.py --purpose sale
```

For rentals:

```powershell
python scripts\collect_property_urls.py --purpose rent --location "Arabian Ranches 2" --manual-wait 20
python scripts\scrape_listing_pages.py --purpose rent --manual-wait 20
python scripts\process_listing_data.py --purpose rent
python scripts\predict_villa_type.py --purpose rent
```

This updates the master file with new listings, latest prices, predicted villa types, and price history.

#### Wednesday Evening: Midweek Listing Update

Run the normal scrape flow again for the main area or the stock type you care about most. This catches midweek new listings and price adjustments before Thursday/Friday buyer and tenant activity.

If time is tight, prioritize whichever side is more active that week:

```powershell
python scripts\collect_property_urls.py --purpose sale --location "Arabian Ranches 2" --manual-wait 20
python scripts\scrape_listing_pages.py --purpose sale --manual-wait 20
python scripts\process_listing_data.py --purpose sale
python scripts\predict_villa_type.py --purpose sale
```

or:

```powershell
python scripts\collect_property_urls.py --purpose rent --location "Arabian Ranches 2" --manual-wait 20
python scripts\scrape_listing_pages.py --purpose rent --manual-wait 20
python scripts\process_listing_data.py --purpose rent
python scripts\predict_villa_type.py --purpose rent
```

#### Friday Before Weekend: Fresh Scan And Active Status Check

Friday late morning or early afternoon is the most important update window. You want fresh data before weekend enquiries and viewings.

Run a fresh scan first, then run the active checker.

For the active checker, start with a dry run:

Run a conservative active-link check. Start with a dry run:

```powershell
python scripts\check_active_listings.py --purpose sale --dry-run --limit 30
python scripts\check_active_listings.py --purpose rent --dry-run --limit 30
```

If the output looks sensible, run without `--dry-run`:

```powershell
python scripts\check_active_listings.py --purpose sale
python scripts\check_active_listings.py --purpose rent
```

This is best used to catch obvious inactive redirects or unavailable pages. `unknown_*` statuses are kept active.

#### Before Client Calls: Enquiry And Client Matching

Use the local matcher or web app when speaking to clients.

Command line:

```powershell
python scripts\match_enquiry.py --purpose sale --budget 5.5m --bedrooms "3 beds" --community "Arabian Ranches 2"
python scripts\match_enquiry.py --purpose rent --budget 340k --bedrooms "5 beds" --community "Arabian Ranches 2" --must-have "bbq sitting area"
```

Local web app:

```powershell
python scripts\webapp.py
```

Then open:

```text
http://127.0.0.1:8000/
```

Use the OpenAI key check and AI feedback only when you want deeper wording or richer analysis from the shortlisted rows.

#### Sunday: Reference Intelligence

Rebuild the floorplan reference candidate file from the latest master data:

```powershell
python scripts\build_floorplan_reference_candidates.py --purpose sale
python scripts\build_floorplan_reference_candidates.py --purpose rent
```

Review the candidate CSVs manually. Only promote strong repeated evidence into:

```text
data/ar2_bayut_floorplan_reference.csv
```

#### Monthly: Manual Clean-Up

Once a month, review:

```text
output/sale/listing_details_master.csv
output/rent/listing_details_master.csv
output/<purpose>/price_history.csv
data/ar2_floorplan_reference_candidates_*.csv
```

Good monthly checks:

- Remove or archive old temporary output files if the folder is getting noisy.
- Review repeated villa type evidence and update the reference file manually.
- Check whether active status looks sensible.
- Run tests after any code changes:

```powershell
python -m pytest
```

Best default rhythm:

- Sales: scan Monday evening, Wednesday evening, and Friday before the weekend if possible.
- Rentals: scan Monday evening and Friday before the weekend; add Wednesday evening when rental stock is moving quickly.
- Active checker: Friday before the weekend, or before a serious client matching session.
- Reference candidates: weekly build, monthly manual update.

### Quick Rental Collection Cycle

For Arabian Ranches 2 rentals, scrape one sub-community at a time and complete the full cycle before moving to the next one. This keeps the URL file simple because `output/rent/property_urls.json` is replaced each time.

Example for Rosa rentals:

```powershell
python scripts\collect_property_urls.py --purpose rent --location "Rosa" --manual-wait 20
python scripts\scrape_listing_pages.py --purpose rent --manual-wait 20
python scripts\process_listing_data.py --purpose rent
python scripts\predict_villa_type.py --purpose rent
```

By default, `scrape_listing_pages.py` runs in `new-only` mode. It checks `output/rent/listing_details_master.csv` and only scrapes URLs that are not already in the master database.

It also auto-resumes interrupted listing scrapes. If the latest raw scrape file already contains some of the current URLs, the script continues from that file and only opens URLs that are not already saved there.

For a full refresh, for example every couple of weeks, use:

```powershell
python scripts\scrape_listing_pages.py --purpose rent --manual-wait 20 --scrape-mode all
```

`--scrape-mode all` creates a fresh raw output file by default. If you specifically want to force a fresh output file during normal `new-only` mode, use:

```powershell
python scripts\scrape_listing_pages.py --purpose rent --fresh-output
```

To check what would be scraped before opening Chrome:

```powershell
python scripts\scrape_listing_pages.py --purpose rent --dry-run
```

Then repeat the same commands with the next sub-community name, for example `Lila`, `Palma`, `Rasha`, `Casa`, `Samara`, `Yasmin`, `Azalea`, or `Camelia`.

The final rent database is:

```text
output/rent/listing_details_master.csv
```

Price changes are tracked in:

```text
output/rent/price_history.csv
```

### Match An Enquiry

Use `match_enquiry.py` to scan the master database for the best active listings.

Example:

```powershell
python scripts\match_enquiry.py --purpose rent --budget 200k --stretch-budget 230k --bedrooms "3 beds" --community "Casa" --must-have dog
```

The script returns ranked matches, saves a CSV in `output/<purpose>/enquiries/`, and prints a suggested client response.

For description-aware AI ranking, set `OPENAI_API_KEY` and add `--ai`:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
python scripts\match_enquiry.py --purpose rent --budget 340k --bedrooms "5 beds" --community "Arabian Ranches 2" --must-have "bbq sitting outer area" --ai
```

The local Python matcher first narrows the database to the strongest candidates. Then the AI step sends those shortlisted rows, including the listing descriptions, to OpenAI for richer ranking. It saves:

```text
output/<purpose>/enquiries/enquiry_...csv
output/<purpose>/enquiries/enquiry_..._ai.json
output/<purpose>/enquiries/enquiry_..._ai_response.txt
```

Useful AI options:

```powershell
--ai-model gpt-5-mini
--candidate-limit 15
--ai-description-chars 12000
```

### Local Web App Preview

Run a private local web app from this project:

```powershell
python scripts\webapp.py
```

Then open:

```text
http://127.0.0.1:8000/
```

This is local to your laptop. It reads the existing master files:

```text
output/sale/listing_details_master.csv
output/rent/listing_details_master.csv
```

Example prompts:

```text
after a 3/4 bed in ar2 at 5.5m budget
3 bed rental in casa under 220k, have a pet dog
5 bed ar2 rent max 340k with bbq sitting area
```

The web app does not scrape live websites. It only searches the data you have already collected.

The top bar has an optional OpenAI API key field for richer AI feedback. The key is sent only to the local app request and is not saved to disk. Use `Check key` first to confirm the key, billing/quota, model access, and connection work. Then use `AI feedback` after entering a prompt if you want a more agent-style market read, ranking summary, and client response.

The web app also has an owner lookup bar. Export your Google Sheets owner database to:

```text
data/owner_property_leads.csv
```

Then paste a Property Finder URL into the owner lookup bar. The app searches the owner CSV `Link` column and returns owner names, numbers, property details, notes, and all matching Property Finder URLs. The owner file stays separate from the listing master.

To sync the owner leads CSV from Google Sheets, use a shared/published Google Sheets CSV export link:

```powershell
python scripts\sync_owner_leads.py --url "YOUR_GOOGLE_SHEET_URL"
```

You can use either the normal Google Sheets edit URL or the direct CSV export URL. If the owner leads are on a specific tab, pass its `gid`:

```powershell
python scripts\sync_owner_leads.py --url "YOUR_GOOGLE_SHEET_URL" --gid "123456789"
```

The script overwrites `data/owner_property_leads.csv`, so run it whenever you want the local web app to pick up your latest Google Sheets owner updates.

### Area Scope

The collection and processing scripts can scrape Property Finder listings for other Dubai areas, for example:

```powershell
python scripts\collect_property_urls.py --purpose rent --location "Dubai Hills Estate" --manual-wait 20
python scripts\scrape_listing_pages.py --purpose rent --manual-wait 20
python scripts\process_listing_data.py --purpose rent
```

The villa-type prediction step is currently Arabian Ranches 2 specific because it uses:

```text
data/ar2_bayut_floorplan_reference.csv
```

For non-AR2 areas, the scrape and cleaned listing data can still work, but `predict_villa_type.py` will only produce useful type predictions after a matching reference file and prediction rules are added for that area.

### 1. Collect Listing URLs

```powershell
python scripts\collect_property_urls.py
```

For rentals:

```powershell
python scripts\collect_property_urls.py --purpose rent --location "Arabian Ranches 2"
```

This opens Property Finder in Chrome, lets you search/select a community, and saves listing URLs to:

```text
output/<purpose>/property_urls.json
```

You must manually complete any Property Finder bot checks.

On Windows, the script plays a short sound when it needs manual attention. To disable the sound:

```powershell
python scripts\collect_property_urls.py --purpose rent --location "Casa" --no-beep
```

### 2. Scrape Raw Listing Pages

```powershell
python scripts\scrape_listing_pages.py
```

For rentals:

```powershell
python scripts\scrape_listing_pages.py --purpose rent
```

This opens each URL, waits for your manual bot-check window, expands the description, scrolls to agent/regulatory sections, and saves raw page evidence to:

```text
output/<purpose>/raw/listing_pages_YYYY-MM-DD_HH-MM.csv
```

On Windows, the script plays a short sound before manual verification waits and when Human Verification appears during a listing scrape. To disable the sound:

```powershell
python scripts\scrape_listing_pages.py --purpose rent --no-beep
```

Raw files intentionally keep noisy page text so old scrapes can be reprocessed later.

Optional manual wait:

```powershell
python scripts\scrape_listing_pages.py --manual-wait 120
```

Optional slower scraping with jitter:

```powershell
python scripts\scrape_listing_pages.py --delay-min 5 --delay-max 10
```

Resume is enabled by default when the output file already exists. To force scraping every URL again:

```powershell
python scripts\scrape_listing_pages.py --scrape-mode all
```

Scraper logs are written to:

```text
output/<purpose>/logs/
```

### 3. Process Raw Data

```powershell
python scripts\process_listing_data.py
```

For rentals:

```powershell
python scripts\process_listing_data.py --purpose rent
```

By default, this uses the latest raw scrape file and creates a clean CSV in:

```text
output/<purpose>/processed/listing_details_YYYY-MM-DD_HH-MM.csv
```

It also updates:

```text
output/<purpose>/listing_details_master.csv
```

Note: the normal final master update happens after villa-type prediction. Use `--update-master` only if you specifically want a processed-only master.

To process a specific raw file:

```powershell
python scripts\process_listing_data.py --input output\sale\raw\listing_pages_2026-05-12_21-07.csv
```

To update the master from processed data only:

```powershell
python scripts\process_listing_data.py --input output\sale\raw\listing_pages_2026-05-12_21-07.csv --update-master
```

### 4. Predict Villa Type

```powershell
python scripts\predict_villa_type.py
```

For rentals:

```powershell
python scripts\predict_villa_type.py --purpose rent
```

By default, this uses the latest processed listing file and compares it with:

```text
data/ar2_bayut_floorplan_reference.csv
```

It outputs a predicted CSV in:

```text
output/<purpose>/predicted/
```

The predicted file adds:

```text
predicted_community
predicted_type
predicted_type_candidate
prediction_confidence
prediction_reason
prediction_source
type_mismatch_flag
```

This prediction step updates the final master file:

```text
output/<purpose>/listing_details_master.csv
```

The master file tracks listing history:

```text
first_seen_date
last_seen_date
times_seen
is_active
```

When you scrape a sub-community again, matching URLs are updated, new URLs are added, and older URLs from the same detected community are marked `is_active = False` if they were not seen in the latest run. Other communities are left alone.

If an existing listing URL is seen again with a changed price, the latest price stays on the master row and the change is appended to:

```text
output/<purpose>/price_history.csv
```

Price history rows include:

```text
change_date
old_price
new_price
price_change
price_change_pct
old_annual_rent
new_annual_rent
annual_rent_change
annual_rent_change_pct
```

To avoid updating the master:

```powershell
python scripts\predict_villa_type.py --no-master
```

To run against a specific processed file:

```powershell
python scripts\predict_villa_type.py --purpose sale --input output\sale\processed\listing_details_2026-05-12_21-07_processed_v2.csv
```

### 5. Check Active Listings

Use `check_active_listings.py` to check whether master-file URLs still look active without rescraping every listing detail page.

```powershell
python scripts\check_active_listings.py --purpose sale --dry-run --limit 20
python scripts\check_active_listings.py --purpose sale
```

For rentals:

```powershell
python scripts\check_active_listings.py --purpose rent --dry-run --limit 20
python scripts\check_active_listings.py --purpose rent
```

The script reads:

```text
output/<purpose>/listing_details_master.csv
```

It updates:

```text
is_active
active_checked_at
active_check_status
active_check_reason
```

It only marks a listing inactive when the evidence is clear, such as a redirect to a search page, a not-found response, or obvious unavailable text. Human verification, request errors, and unclear pages are kept active but flagged as `unknown_*`.

This is safest as a weekly check, or before serious enquiry matching. It avoids the risk of marking Casa/Samara/Lila inactive just because you only scraped Rosa.

## Clean Processed Columns

Processed listing files keep the database-useful fields:

```text
url
listing_purpose
scraped_at
title
price
sale_price
rent_price
rent_frequency
annual_rent
monthly_rent_equivalent
bedrooms
bathrooms
property_size_sqft
plot_size_sqft
price_per_sqft
sale_price_per_sqft
rent_per_sqft
detected_type_from_description
bua_from_description
plot_from_description
agent_name
agency_name
listed_age
listed_date
description
description_json
```

Notes:

- `property_size_sqft` is the size shown by Property Finder.
- `plot_size_sqft` uses description plot size when available, otherwise falls back to Property Finder size.
- Sale rows fill `sale_price` and `sale_price_per_sqft`.
- Rent rows fill `rent_price`, `rent_frequency`, `annual_rent`, `monthly_rent_equivalent`, and `rent_per_sqft`.
- `price_per_sqft` is purpose-aware: sale price per sqft for sales, annualized rent per sqft for rentals.
- `bua_from_description` is only filled when the listing text explicitly says BUA or built-up area.
- `description` is the full expanded listing description for later AI analysis.
- `description_json` stores the same description as JSON with `text` and `lines`.

## Reference Data

`data/ar2_bayut_floorplan_reference.csv` is the local floorplan reference used for prediction. It includes community, type, bedroom/bathroom counts, and reference BUA/plot where known.

`data/ar2_type_enrichment.csv` is for manual notes and market knowledge. Add your own findings here over time, such as extension potential, common upgrades, buyer profile, and value notes.

### Improve Floorplan Reference From Live Listings

Property Finder listing descriptions often include the correct villa type, for example `Type 1`, `Type 2`, `Type 1E`, or `Type 1M`. Use that as evidence to improve your reference data over time.

Build a review file from the current master database:

```powershell
python scripts\build_floorplan_reference_candidates.py --purpose sale
```

For rentals:

```powershell
python scripts\build_floorplan_reference_candidates.py --purpose rent
```

The script reads:

```text
output/<purpose>/listing_details_master.csv
data/ar2_bayut_floorplan_reference.csv
```

It writes a timestamped candidate file in:

```text
data/ar2_floorplan_reference_candidates_<purpose>_YYYY-MM-DD_HH-MM.csv
```

This file is for review only. It does not overwrite `data/ar2_bayut_floorplan_reference.csv`.

The safest update rhythm is:

- Update the master database whenever you scrape new listings.
- Rebuild the candidate reference file weekly.
- Manually promote good evidence into `data/ar2_bayut_floorplan_reference.csv` monthly, or whenever you are confident.

Use the `evidence_count`, size medians, reference status, and example URLs to decide what should be promoted. Trust `detected_type_from_description` more than `predicted_type`, because `predicted_type` already depends on the reference file.

## Manual Bot Checks

The scripts do not bypass Property Finder bot checks. The expected workflow is:

1. Chrome opens.
2. You manually complete the bot check.
3. The script continues after the configured wait time.

## Known Limitations

- Property Finder can redirect old listing URLs to search results; these are marked and skipped during processing.
- Some BUA/plot/type values are unavailable if agents do not include them in descriptions.
- Bayut blocks direct `requests` crawling in some sessions, so the floorplan reference is kept locally.
- Villa type prediction is confidence-scored and should be treated as a guide, not guaranteed truth.

## Tests

Run non-browser processing and prediction tests with:

```powershell
python -m pytest
```

These tests do not open Chrome or scrape Property Finder.
