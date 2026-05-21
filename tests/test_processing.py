from datetime import datetime

from scripts.extract_listing_details import (
    calculate_listed_date,
    extract_agent_profile,
    extract_bua_from_description,
    extract_header_metrics,
    extract_listed_age,
)
from scripts.process_listing_data import extract_rent_frequency, process_raw_row


def test_extract_header_metrics():
    body = "\n".join([
        "Logo-En",
        "Search",
        "6,700,000",
        "4",
        "4",
        "4,359 sqft",
    ])

    assert extract_header_metrics(body) == {
        "price": 6700000,
        "bedrooms": 4,
        "bathrooms": 4,
        "property_size_sqft": 4359,
    }


def test_calculate_listed_date():
    scraped_at = datetime(2026, 5, 13, 10, 0, 0)

    assert calculate_listed_date("2 months ago", scraped_at) == "2026-03-14"
    assert calculate_listed_date("22 days ago", scraped_at) == "2026-04-21"
    assert calculate_listed_date("Listed today", scraped_at) == "2026-05-13"


def test_extract_listed_age():
    body = "\n".join([
        "Regulatory information",
        "Listed",
        "2 months ago",
    ])

    assert extract_listed_age(body) is None
    assert extract_listed_age("Listed 2 months ago") == "Listed 2 months ago"


def test_extract_bua_ignores_tiny_type_number_false_positive():
    assert extract_bua_from_description("Type 2 BUA details available on request") is None
    assert extract_bua_from_description("BUA: 4,363 sqft") == 4363


def test_extract_agent_profile_reads_pf_agent_metrics():
    body = "\n".join([
        "Anastasiia Kurochkina",
        "English, Russian, Ukrainian",
        "4.3",
        "3 Ratings",
        "See agent properties (17)",
        "12 Closed Deals",
        "5 mins Response time",
        "3M Total value",
        "SuperAgent",
        "Call",
    ])

    profile = extract_agent_profile(body)

    assert profile["agent_rating"] == 4.3
    assert profile["agent_review_count"] == 3
    assert profile["agent_properties_count"] == 17
    assert profile["agent_closed_deals"] == 12
    assert profile["agent_response_time"] == "5 mins"
    assert profile["agent_total_value"] == "3M"
    assert profile["agent_is_superagent"] is True


def test_process_raw_row_uses_dom_values():
    row = {
        "url": "https://example.com/listing",
        "scraped_at": "2026-05-13 10:00:00",
        "title": "Sale in Lila: 4BR Villa",
        "page_status": "ok",
        "price_dom": "6,700,000",
        "bedrooms_dom": "4 Beds",
        "bathrooms_dom": "4 Baths",
        "size_dom": "4,359 sqft",
        "agent_name_dom": "Harry Chen",
        "agent_profile_url_dom": "https://www.propertyfinder.ae/en/agent/harry-chen-123",
        "agent_rating_dom": "4.8",
        "agent_review_count_dom": "11 Ratings",
        "agent_is_superagent_dom": "true",
        "agent_properties_count_dom": "See agent properties (24)",
        "agent_closed_deals_dom": "16",
        "agent_response_time_dom": "5 mins",
        "agent_total_value_dom": "14M",
        "agency_name_dom": "SEENIUN PROPERTIES L.L.C",
        "listed_age_dom": "2 months ago",
        "full_page_text": "\n".join([
            "Logo-En",
            "Search",
            "6,700,000",
            "4",
            "4",
            "4,359 sqft",
            "Description",
            "4BR VILLA | LANDSCAPED GARDEN | UP FOR SALE",
            "Villa for sale in Lila, Arabian Ranches 2",
        ]),
    }

    processed = process_raw_row(row)

    assert processed["price"] == 6700000
    assert processed["bedrooms"] == 4
    assert processed["bathrooms"] == 4
    assert processed["property_size_sqft"] == 4359
    assert processed["agent_name"] == "Harry Chen"
    assert processed["agent_profile_url"] == "https://www.propertyfinder.ae/en/agent/harry-chen-123"
    assert processed["agent_rating"] == 4.8
    assert processed["agent_review_count"] == 11
    assert processed["agent_badge"] == "SuperAgent"
    assert processed["agent_is_superagent"] is True
    assert processed["agent_properties_count"] == 24
    assert processed["agent_closed_deals"] == 16
    assert processed["agent_response_time"] == "5 mins"
    assert processed["agent_total_value"] == "14M"
    assert processed["agency_name"] == "SEENIUN PROPERTIES L.L.C"
    assert processed["listed_age"] == "2 months ago"
    assert processed["listed_date"] == "2026-03-14"


def test_process_raw_row_adds_rent_values():
    row = {
        "url": "https://example.com/rent-listing",
        "scraped_at": "2026-05-13 10:00:00",
        "title": "Villa for rent in Rosa",
        "page_status": "ok",
        "price_dom": "595,000",
        "bedrooms_dom": "6 Beds",
        "bathrooms_dom": "6 Baths",
        "size_dom": "7,922 sqft",
        "full_page_text": "\n".join([
            "Logo-En",
            "Search",
            "595,000 yearly",
            "6",
            "6",
            "7,922 sqft",
            "Description",
            "Type 6 villa available for rent",
        ]),
    }

    processed = process_raw_row(row, purpose="rent")

    assert extract_rent_frequency("595,000 yearly") == "yearly"
    assert processed["sale_price"] is None
    assert processed["rent_price"] == 595000
    assert processed["rent_frequency"] == "yearly"
    assert processed["annual_rent"] == 595000
    assert processed["monthly_rent_equivalent"] == 49583
    assert processed["rent_per_sqft"] == 75


def test_process_raw_row_skips_out_of_area_advertised_listing():
    row = {
        "url": "https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-business-bay-reva-residences-65948287.html",
        "scraped_at": "2026-05-13 10:00:00",
        "title": "Sale in Reva Residences: Investor Deal",
        "page_status": "ok",
        "price_dom": "1,140,000",
        "bathrooms_dom": "1 Bath",
        "size_dom": "472 sqft",
        "full_page_text": "Apartment for sale in Business Bay. Investor deal.",
    }

    assert process_raw_row(row, purpose="sale", target_area="Arabian Ranches 2") is None


def test_process_raw_row_can_disable_target_area_filter():
    row = {
        "url": "https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-business-bay-reva-residences-65948287.html",
        "scraped_at": "2026-05-13 10:00:00",
        "title": "Sale in Reva Residences: Investor Deal",
        "page_status": "ok",
        "price_dom": "1,140,000",
        "bathrooms_dom": "1 Bath",
        "size_dom": "472 sqft",
        "full_page_text": "Apartment for sale in Business Bay. Investor deal.",
    }

    assert process_raw_row(row, purpose="sale", target_area="")["price"] == 1140000


def test_process_raw_row_plot_size_sqft_is_none_when_no_plot_in_description():
    """plot_size_sqft must not fall back to property_size_sqft (BUA).

    A previous bug caused plot_size_sqft to be populated with the BUA value
    when no plot was found in the listing description. PPSF is always calculated
    on BUA (property_size_sqft) — the Dubai/Property Finder standard.
    """
    row = {
        "url": "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-lila-65948288.html",
        "scraped_at": "2026-05-13 10:00:00",
        "title": "Sale in Lila: 4BR Villa",
        "page_status": "ok",
        "price_dom": "6,700,000",
        "bedrooms_dom": "4 Beds",
        "bathrooms_dom": "4 Baths",
        "size_dom": "3,234 sqft",
        "full_page_text": "\n".join([
            "Logo-En",
            "Search",
            "6,700,000",
            "4",
            "4",
            "3,234 sqft",
            "Description",
            "Lovely 4-bedroom villa in Lila, Arabian Ranches 2.",
            "No plot size mentioned in this listing.",
        ]),
    }

    processed = process_raw_row(row, purpose="sale")

    # BUA is populated from size_dom
    assert processed["property_size_sqft"] == 3234
    # Plot must be None — no plot found in description, no fallback to BUA
    assert processed["plot_size_sqft"] is None
    # PPSF uses BUA
    assert processed["sale_price_per_sqft"] == round(6_700_000 / 3234)


def test_process_raw_row_plot_size_sqft_populated_from_description():
    """When the listing description contains a plot size, it should be captured."""
    row = {
        "url": "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-rosa-65948290.html",
        "scraped_at": "2026-05-13 10:00:00",
        "title": "Sale in Rosa: Type 3 Villa",
        "page_status": "ok",
        "price_dom": "8,500,000",
        "bedrooms_dom": "4 Beds",
        "bathrooms_dom": "6 Baths",
        "size_dom": "4,814 sqft",
        "full_page_text": "\n".join([
            "Logo-En",
            "Search",
            "8,500,000",
            "4",
            "6",
            "4,814 sqft",
            "Description",
            "Type 3 villa for sale in Rosa, Arabian Ranches 2.",
            "BUA: 4,814 sqft | Plot: 7,776 sqft",
        ]),
    }

    processed = process_raw_row(row, purpose="sale")

    assert processed["property_size_sqft"] == 4814
    assert processed["plot_size_sqft"] == 7776
    # PPSF still uses BUA, not plot
    assert processed["sale_price_per_sqft"] == round(8_500_000 / 4814)
