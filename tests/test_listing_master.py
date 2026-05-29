from unittest.mock import patch

import pandas as pd
import pytest

from scripts.listing_master import build_price_history_events, prepare_master_update, validate_master_update_input


def master_tracking_df():
    return pd.DataFrame([
        {
            "url": "https://example.com/rosa-old-seen",
            "listing_purpose": "rent",
            "title": "Old Rosa seen",
            "price": 595000,
            "annual_rent": 595000,
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
            "price": 525000,
            "annual_rent": 525000,
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
            "price": 450000,
            "annual_rent": 450000,
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


def predicted_tracking_df():
    return pd.DataFrame([
        {
            "url": "https://example.com/rosa-old-seen",
            "listing_purpose": "rent",
            "title": "Old Rosa seen updated",
            "price": 575000,
            "annual_rent": 575000,
            "predicted_community": "Rosa",
            "predicted_type": "Type 5",
            "scraped_at": "2026-05-13 09:00:00",
        },
        {
            "url": "https://example.com/rosa-new",
            "listing_purpose": "rent",
            "title": "New Rosa",
            "price": 625000,
            "annual_rent": 625000,
            "predicted_community": "Rosa",
            "predicted_type": "Type 5",
            "scraped_at": "2026-05-13 09:00:00",
        },
    ])


def test_validate_master_update_input_accepts_valid_rows():
    validate_master_update_input(predicted_tracking_df(), "rent")


def test_validate_master_update_input_rejects_missing_required_columns():
    predicted_df = predicted_tracking_df().drop(columns=["url"])

    with pytest.raises(ValueError, match="Missing required columns"):
        validate_master_update_input(predicted_df, "rent")


def test_validate_master_update_input_rejects_blank_urls():
    predicted_df = predicted_tracking_df()
    predicted_df.loc[0, "url"] = " "

    with pytest.raises(ValueError, match="missing URL values"):
        validate_master_update_input(predicted_df, "rent")


def test_validate_master_update_input_rejects_duplicate_urls():
    predicted_df = predicted_tracking_df()
    predicted_df.loc[1, "url"] = predicted_df.loc[0, "url"]

    with pytest.raises(ValueError, match="duplicate incoming URL"):
        validate_master_update_input(predicted_df, "rent")

def test_validate_master_update_input_rejects_blank_community_invalid():
    predicted_df = predicted_tracking_df()
    predicted_df.loc[0, "predicted_community"] = ""
 
    with pytest.raises(ValueError, match= "predicted_community cannot be blank"):
        validate_master_update_input(predicted_df, "rent")

def test_validate_master_update_input_rejects_wrong_purpose():
    predicted_df = predicted_tracking_df()
    predicted_df.loc[0, "listing_purpose"] = "sale"

    with pytest.raises(ValueError, match="Cannot update rent master"):
        validate_master_update_input(predicted_df, "rent")


def test_prepare_master_update_full_refresh_tracks_seen_and_inactive_rows_by_scope():
    with patch("scripts.listing_master.pd.Timestamp") as timestamp:
        timestamp.now.return_value.strftime.return_value = "2026-05-13"
        updated_df = prepare_master_update(master_tracking_df(), predicted_tracking_df())

    rows = updated_df.set_index("url").to_dict("index")

    assert rows["https://example.com/rosa-old-seen"]["first_seen_date"] == "2026-05-01"
    assert rows["https://example.com/rosa-old-seen"]["last_seen_date"] == "2026-05-13"
    assert rows["https://example.com/rosa-old-seen"]["times_seen"] == 3
    assert rows["https://example.com/rosa-old-seen"]["is_active"] is True
    assert rows["https://example.com/rosa-old-seen"]["price"] == 575000

    assert rows["https://example.com/rosa-new"]["first_seen_date"] == "2026-05-13"
    assert rows["https://example.com/rosa-new"]["last_seen_date"] == "2026-05-13"
    assert rows["https://example.com/rosa-new"]["times_seen"] == 1
    assert rows["https://example.com/rosa-new"]["is_active"] is True

    assert rows["https://example.com/rosa-missing"]["is_active"] is False
    assert rows["https://example.com/lila-not-this-run"]["is_active"] is True
    assert "https://example.com/out-of-area-ad" not in rows


def test_prepare_master_update_partial_refresh_keeps_seen_tracking_and_missing_rows_active():
    with patch("scripts.listing_master.pd.Timestamp") as timestamp:
        timestamp.now.return_value.strftime.return_value = "2026-05-13"
        updated_df = prepare_master_update(
            master_tracking_df(),
            predicted_tracking_df(),
            refresh_seen=False,
        )

    rows = updated_df.set_index("url").to_dict("index")

    assert rows["https://example.com/rosa-old-seen"]["first_seen_date"] == "2026-05-01"
    assert rows["https://example.com/rosa-old-seen"]["last_seen_date"] == "2026-05-12"
    assert rows["https://example.com/rosa-old-seen"]["times_seen"] == 2
    assert rows["https://example.com/rosa-old-seen"]["is_active"] is True
    assert rows["https://example.com/rosa-old-seen"]["price"] == 575000

    assert rows["https://example.com/rosa-new"]["first_seen_date"] == "2026-05-13"
    assert rows["https://example.com/rosa-new"]["last_seen_date"] == "2026-05-13"
    assert rows["https://example.com/rosa-new"]["times_seen"] == 1
    assert rows["https://example.com/rosa-new"]["is_active"] is True

    assert rows["https://example.com/rosa-missing"]["is_active"] is True
    assert rows["https://example.com/lila-not-this-run"]["is_active"] is True


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
