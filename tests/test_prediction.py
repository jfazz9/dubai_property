from unittest.mock import patch

import pandas as pd

from scripts.predict_villa_type import build_price_history_events, prepare_master_update, predict_row


def test_predict_lila_type_2_from_reference():
    reference_df = pd.DataFrame([
        {
            "community": "Lila",
            "property_category": "villa",
            "type": "Type 2",
            "bedrooms": 4,
            "bathrooms": 4,
            "bua_reference_sqft": 3234,
            "plot_reference_sqft": 4359,
        }
    ])
    row = pd.Series({
        "title": "Sale in Lila: Great Price | Type 2",
        "description": "Villa for sale in Lila, Arabian Ranches 2. Type 2 with 3234 BUA and 4359 Plot.",
        "url": "https://example.com/lila",
        "bedrooms": 4,
        "bathrooms": 4,
        "bua_from_description": 3234,
        "plot_size_sqft": 4359,
        "detected_type_from_description": "Type 2",
    })

    prediction = predict_row(row, reference_df)

    assert prediction["predicted_community"] == "Lila"
    assert prediction["predicted_type"] == "Type 2"
    assert prediction["prediction_confidence"] == 100
    assert prediction["type_mismatch_flag"] is False


def test_prepare_master_update_tracks_seen_and_inactive_rows_by_scope():
    master_df = pd.DataFrame([
        {
            "url": "https://example.com/rosa-old-seen",
            "listing_purpose": "rent",
            "title": "Old Rosa seen",
            "predicted_community": "Rosa",
            "first_seen_date": "2026-05-01",
            "last_seen_date": "2026-05-12",
            "times_seen": 2,
            "is_active": True,
        },
        {
            "url": "https://example.com/rosa-missing",
            "listing_purpose": "rent",
            "title": "Old Rosa missing",
            "predicted_community": "Rosa",
            "first_seen_date": "2026-05-02",
            "last_seen_date": "2026-05-12",
            "times_seen": 1,
            "is_active": True,
        },
        {
            "url": "https://example.com/lila-not-this-run",
            "listing_purpose": "rent",
            "title": "Lila untouched",
            "predicted_community": "Lila",
            "first_seen_date": "2026-05-02",
            "last_seen_date": "2026-05-12",
            "times_seen": 1,
            "is_active": True,
        },
        {
            "url": "https://example.com/out-of-area-ad",
            "listing_purpose": "rent",
            "title": "Out of area advert",
            "predicted_community": None,
            "first_seen_date": "2026-05-02",
            "last_seen_date": "2026-05-12",
            "times_seen": 1,
            "is_active": True,
        },
    ])
    predicted_df = pd.DataFrame([
        {
            "url": "https://example.com/rosa-old-seen",
            "listing_purpose": "rent",
            "title": "Old Rosa seen updated",
            "predicted_community": "Rosa",
            "scraped_at": "2026-05-13 09:00:00",
        },
        {
            "url": "https://example.com/rosa-new",
            "listing_purpose": "rent",
            "title": "New Rosa",
            "predicted_community": "Rosa",
            "scraped_at": "2026-05-13 09:00:00",
        },
    ])

    with patch("scripts.predict_villa_type.pd.Timestamp") as timestamp:
        timestamp.now.return_value.strftime.return_value = "2026-05-13"
        updated_df = prepare_master_update(master_df, predicted_df)

    rows = updated_df.set_index("url").to_dict("index")

    assert rows["https://example.com/rosa-old-seen"]["first_seen_date"] == "2026-05-01"
    assert rows["https://example.com/rosa-old-seen"]["last_seen_date"] == "2026-05-13"
    assert rows["https://example.com/rosa-old-seen"]["times_seen"] == 3
    assert rows["https://example.com/rosa-old-seen"]["is_active"] is True

    assert rows["https://example.com/rosa-new"]["first_seen_date"] == "2026-05-13"
    assert rows["https://example.com/rosa-new"]["last_seen_date"] == "2026-05-13"
    assert rows["https://example.com/rosa-new"]["times_seen"] == 1
    assert rows["https://example.com/rosa-new"]["is_active"] is True

    assert rows["https://example.com/rosa-missing"]["is_active"] is False
    assert rows["https://example.com/lila-not-this-run"]["is_active"] is True
    assert "https://example.com/out-of-area-ad" not in rows


def test_build_price_history_events_records_price_changes():
    master_df = pd.DataFrame([
        {
            "url": "https://example.com/rosa-price-change",
            "listing_purpose": "rent",
            "title": "Rosa price change",
            "price": 595000,
            "annual_rent": 595000,
            "predicted_community": "Rosa",
            "predicted_type": "Type 5",
        }
    ])
    predicted_df = pd.DataFrame([
        {
            "url": "https://example.com/rosa-price-change",
            "listing_purpose": "rent",
            "title": "Rosa price change",
            "price": 575000,
            "annual_rent": 575000,
            "predicted_community": "Rosa",
            "predicted_type": "Type 5",
            "scraped_at": "2026-05-14 09:00:00",
        }
    ])

    events_df = build_price_history_events(master_df, predicted_df)
    event = events_df.iloc[0].to_dict()

    assert len(events_df) == 1
    assert event["change_date"] == "2026-05-14"
    assert event["old_price"] == 595000
    assert event["new_price"] == 575000
    assert event["price_change"] == -20000
    assert event["price_change_pct"] == -3.36
    assert event["old_annual_rent"] == 595000
    assert event["new_annual_rent"] == 575000
    assert event["annual_rent_change"] == -20000
    assert event["annual_rent_change_pct"] == -3.36


def test_predict_uses_manual_pf_reference_sizes():
    reference_df = pd.DataFrame([
        {
            "community": "Casa",
            "property_category": "villa",
            "type": "Type 1",
            "bedrooms": 3,
            "bathrooms": 4,
            "bua_reference_sqft": None,
            "plot_reference_sqft": None,
            "pf_bua": 3252,
            "pf_plot": 4360,
        },
        {
            "community": "Casa",
            "property_category": "villa",
            "type": "Type 3",
            "bedrooms": 4,
            "bathrooms": 5,
            "bua_reference_sqft": 3538,
            "plot_reference_sqft": 4650,
        },
    ])
    row = pd.Series({
        "title": "Rent in Casa: 3BR villa",
        "description": "Villa for rent in Casa, Arabian Ranches 2.",
        "url": "https://example.com/casa",
        "bedrooms": 3,
        "bathrooms": 4,
        "bua_from_description": 3252,
        "plot_size_sqft": 4360,
        "detected_type_from_description": None,
    })

    prediction = predict_row(row, reference_df)

    assert prediction["predicted_type"] == "Type 1"
    assert prediction["prediction_confidence"] >= 70
    assert "pf_bua" in prediction["prediction_reason"]
