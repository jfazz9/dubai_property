from datetime import datetime

from scripts.extract_listing_details import (
    calculate_listed_date,
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
