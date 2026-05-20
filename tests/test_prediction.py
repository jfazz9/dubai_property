from unittest.mock import patch

import pandas as pd

from scripts.predict_villa_type import build_price_history_events, prepare_master_update, predict_row, score_bua_range, score_plot_range


# ── Reference data helpers ────────────────────────────────────────────────────

def lila_type_2_ref():
    """Lila Type 2 reference row in current ar2_villa_type_reference.csv format."""
    return {
        "community": "Lila",
        "property_category": "villa",
        "type": "Type 2",
        "bedrooms": 4,
        "bathrooms": 4,
        "bua_ref_sqft": 3234,
        "bua_min_sqft": 2975,
        "bua_max_sqft": 3493,
        "plot_ref_sqft": 4359,
        "plot_min_sqft": 3705,
        "plot_max_sqft": 5013,
    }


def lila_type_1_ref():
    return {
        "community": "Lila",
        "property_category": "villa",
        "type": "Type 1",
        "bedrooms": 3,
        "bathrooms": 4,
        "bua_ref_sqft": 3163,
        "bua_min_sqft": 2910,
        "bua_max_sqft": 3416,
        "plot_ref_sqft": 4898,
        "plot_min_sqft": 4163,
        "plot_max_sqft": 5633,
    }


def samara_type_2_ref():
    return {
        "community": "Samara",
        "property_category": "villa",
        "type": "Type 2",
        "bedrooms": 4,
        "bathrooms": 4,
        "bua_ref_sqft": 4038,
        "bua_min_sqft": 3128,
        "bua_max_sqft": 4361,
        "plot_ref_sqft": 4810,
        "plot_min_sqft": 3885,
        "plot_max_sqft": 5808,
    }


# ── Scoring unit tests ────────────────────────────────────────────────────────

def test_score_bua_within_range_returns_full_points():
    candidate = lila_type_2_ref()
    score, reasons = score_bua_range(3234, candidate)  # ref BUA, well within 2975–3493
    assert score == 30
    assert any("within standard range" in r for r in reasons)


def test_score_bua_just_above_max_returns_partial_points():
    """BUA slightly above the standard range — possible extension, still scores well."""
    candidate = lila_type_2_ref()
    # 3493 * 1.05 = 3668 — 5% over max
    score, reasons = score_bua_range(3668, candidate)
    assert score == 22
    assert any("possible extension" in r for r in reasons)


def test_score_bua_well_above_max_returns_low_points():
    """BUA heavily above the standard range — likely extended or wrong type."""
    candidate = lila_type_2_ref()
    # 3493 * 1.40 = 4890 — 40% over max
    score, reasons = score_bua_range(4890, candidate)
    assert score == 6
    assert any("well above range" in r for r in reasons)


def test_score_bua_well_below_min_returns_negative():
    """BUA well below the standard range — unlikely to be this type."""
    candidate = lila_type_2_ref()
    # 2975 * 0.75 = 2231 — 25% below min
    score, reasons = score_bua_range(2231, candidate)
    assert score == -12
    assert any("well below" in r for r in reasons)


def test_score_plot_within_range_returns_full_points():
    candidate = lila_type_2_ref()
    score, reasons = score_plot_range(4359, candidate)  # ref plot, within 3705–5013
    assert score == 20
    assert any("within standard range" in r for r in reasons)


def test_score_plot_missing_returns_zero():
    candidate = lila_type_2_ref()
    score, reasons = score_plot_range(None, candidate)
    assert score == 0
    assert reasons == []


# ── Explicit type bypass ──────────────────────────────────────────────────────

def test_predict_explicit_type_in_description_bypasses_scoring():
    """When a listing states its type, prediction_confidence = 100 and source = description."""
    reference_df = pd.DataFrame([lila_type_2_ref()])
    row = pd.Series({
        "title": "Sale in Lila: Type 2 with 4 Beds",
        "description": "Villa for sale in Lila, Arabian Ranches 2. Type 2.",
        "url": "https://example.com/lila",
        "bedrooms": 4,
        "bathrooms": 4,
        "property_size_sqft": 3234,
        "bua_from_description": None,
        "plot_from_description": None,
        "plot_size_sqft": None,
        "detected_type_from_description": "Type 2",
    })

    prediction = predict_row(row, reference_df)

    assert prediction["predicted_community"] == "Lila"
    assert prediction["predicted_type"] == "Type 2"
    assert prediction["prediction_confidence"] == 100
    assert prediction["prediction_source"] == "description"
    assert prediction["type_mismatch_flag"] is False


def test_predict_lila_type_2_from_reference():
    """Listing with explicit type in title → bypass → confidence 100."""
    reference_df = pd.DataFrame([lila_type_2_ref()])
    row = pd.Series({
        "title": "Sale in Lila: Great Price | Type 2",
        "description": "Villa for sale in Lila, Arabian Ranches 2. Type 2 with 3234 BUA and 4359 Plot.",
        "url": "https://example.com/lila",
        "bedrooms": 4,
        "bathrooms": 4,
        "property_size_sqft": 3234,
        "bua_from_description": 3234,
        "plot_from_description": 4359,
        "plot_size_sqft": None,
        "detected_type_from_description": "Type 2",
    })

    prediction = predict_row(row, reference_df)

    assert prediction["predicted_community"] == "Lila"
    assert prediction["predicted_type"] == "Type 2"
    assert prediction["prediction_confidence"] == 100
    assert prediction["type_mismatch_flag"] is False


# ── Scoring-based prediction tests ───────────────────────────────────────────

def test_predict_lila_type_2_from_bua_and_beds_no_explicit_type():
    """When no type is stated, BUA within range + correct bed count → high confidence Type 2."""
    reference_df = pd.DataFrame([lila_type_1_ref(), lila_type_2_ref()])
    row = pd.Series({
        "title": "Sale in Lila: Great Price",
        "description": "Villa for sale in Lila, Arabian Ranches 2.",
        "url": "https://example.com/lila",
        "bedrooms": 4,
        "bathrooms": 4,
        "property_size_sqft": 3234,
        "bua_from_description": None,
        "plot_from_description": 4359,
        "plot_size_sqft": None,
        "detected_type_from_description": None,
    })

    prediction = predict_row(row, reference_df)

    assert prediction["predicted_community"] == "Lila"
    assert "Type 2" in prediction["predicted_type"]  # may be "Type 2" or "Likely Type 2"
    assert prediction["prediction_confidence"] >= 45


def test_predict_bedroom_mismatch_lowers_confidence():
    """3-bed listing vs 4-bed reference type → bedroom mismatch reduces score significantly."""
    reference_df = pd.DataFrame([lila_type_2_ref()])  # Type 2 is 4-bed
    row = pd.Series({
        "title": "Sale in Lila: 3 Bed Villa",
        "description": "Villa for sale in Lila, Arabian Ranches 2.",
        "url": "https://example.com/lila",
        "bedrooms": 3,
        "bathrooms": 4,
        "property_size_sqft": 3234,
        "bua_from_description": None,
        "plot_from_description": None,
        "plot_size_sqft": None,
        "detected_type_from_description": None,
    })

    prediction = predict_row(row, reference_df)

    # Bed mismatch applies -12; BUA within range gives +30 → net 18.
    # Should be "Possible" or lower, not a confident direct label.
    assert prediction["prediction_confidence"] < 70
    assert "bedrooms differ" in prediction["prediction_reason"]


def test_predict_extended_bua_still_predicts_same_type():
    """A listing with BUA above bua_max is still the same type — just extended."""
    reference_df = pd.DataFrame([lila_type_2_ref()])  # bua_max = 3493
    extended_bua = 3700  # 6% over max → "possible extension"

    row = pd.Series({
        "title": "Sale in Lila: Extended Villa",
        "description": "Villa for sale in Lila, Arabian Ranches 2. Extended.",
        "url": "https://example.com/lila",
        "bedrooms": 4,
        "bathrooms": 4,
        "property_size_sqft": extended_bua,
        "bua_from_description": None,
        "plot_from_description": 4359,
        "plot_size_sqft": None,
        "detected_type_from_description": None,
    })

    prediction = predict_row(row, reference_df)

    # Type 2 should still win — beds match (+20), BUA slightly over max (+22), plot in range (+20)
    assert "Type 2" in prediction["predicted_type"]
    assert prediction["prediction_confidence"] >= 45


def test_predict_community_type_isolation():
    """Samara Type 2 and Lila Type 2 are different villas — community determines which reference is used."""
    reference_df = pd.DataFrame([lila_type_2_ref(), samara_type_2_ref()])

    lila_row = pd.Series({
        "title": "Sale in Lila: Type 2 Villa",
        "description": "Villa for sale in Lila, Arabian Ranches 2.",
        "url": "https://example.com/lila",
        "bedrooms": 4,
        "bathrooms": 4,
        "property_size_sqft": 3234,
        "bua_from_description": None,
        "plot_from_description": None,
        "plot_size_sqft": None,
        "detected_type_from_description": "Type 2",
    })

    samara_row = pd.Series({
        "title": "Sale in Samara: Type 2 Villa",
        "description": "Villa for sale in Samara, Arabian Ranches 2.",
        "url": "https://example.com/samara",
        "bedrooms": 4,
        "bathrooms": 4,
        "property_size_sqft": 4038,
        "bua_from_description": None,
        "plot_from_description": None,
        "plot_size_sqft": None,
        "detected_type_from_description": "Type 2",
    })

    lila_prediction = predict_row(lila_row, reference_df)
    samara_prediction = predict_row(samara_row, reference_df)

    assert lila_prediction["predicted_community"] == "Lila"
    assert samara_prediction["predicted_community"] == "Samara"
    assert lila_prediction["predicted_type"] == "Type 2"
    assert samara_prediction["predicted_type"] == "Type 2"


def test_predict_no_community_returns_none():
    """Listing with no AR2 community mention → predicted_community is None."""
    reference_df = pd.DataFrame([lila_type_2_ref()])
    row = pd.Series({
        "title": "Sale in Business Bay: 4BR Apartment",
        "description": "Great investment in Business Bay.",
        "url": "https://example.com/business-bay",
        "bedrooms": 4,
        "bathrooms": 4,
        "property_size_sqft": 3000,
        "bua_from_description": None,
        "plot_from_description": None,
        "plot_size_sqft": None,
        "detected_type_from_description": None,
    })

    prediction = predict_row(row, reference_df)

    assert prediction["predicted_community"] is None
    assert prediction["prediction_confidence"] == 0


# ── Master tracking tests ─────────────────────────────────────────────────────

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
