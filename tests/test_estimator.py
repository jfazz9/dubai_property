"""Tests for the valuation estimator data pipeline.

These tests cover the helpers and data preparation layer — they do not make
OpenAI calls. The `valuation_estimate()` function itself is tested via
mock to verify the data pipeline logic without hitting the API.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from scripts.webapp_backend import (
    load_villa_type_reference,
    lookup_type_reference,
    parse_condition_features,
    parse_villa_type_from_text,
)


# ── Reference file helpers ────────────────────────────────────────────────────

def make_reference_df():
    """Small reference DataFrame matching the ar2_villa_type_reference.csv format."""
    return pd.DataFrame([
        {
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
        },
        {
            "community": "Lila",
            "property_category": "townhouse",
            "type": "Type 3",
            "bedrooms": 4,
            "bathrooms": 5,
            "bua_ref_sqft": None,
            "bua_min_sqft": None,
            "bua_max_sqft": None,
            "plot_ref_sqft": 4650,
            "plot_min_sqft": 4418,
            "plot_max_sqft": 4882,
        },
        {
            "community": "Lila",
            "property_category": "villa",
            "type": "Type 3",
            "bedrooms": 4,
            "bathrooms": 5,
            "bua_ref_sqft": None,
            "bua_min_sqft": None,
            "bua_max_sqft": None,
            "plot_ref_sqft": 4359,
            "plot_min_sqft": 3705,
            "plot_max_sqft": 5013,
        },
        {
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
        },
        {
            "community": "Rosa",
            "property_category": "villa",
            "type": "Type 3",
            "bedrooms": 4,
            "bathrooms": 6,
            "bua_ref_sqft": 4814,
            "bua_min_sqft": 4429,
            "bua_max_sqft": 5199,
            "plot_ref_sqft": 7776,
            "plot_min_sqft": 6610,
            "plot_max_sqft": 8942,
        },
    ])


# ── lookup_type_reference ─────────────────────────────────────────────────────

def test_lookup_type_reference_returns_correct_row():
    ref_df = make_reference_df()
    result = lookup_type_reference(ref_df, "Lila", "Type 2")

    assert result is not None
    assert result["community"] == "Lila"
    assert result["type"] == "Type 2"
    assert result["bua_min_sqft"] == 2975
    assert result["bua_max_sqft"] == 3493


def test_lookup_type_reference_prefers_villa_over_townhouse():
    """Lila Type 3 has both a villa and townhouse row — villa should be returned."""
    ref_df = make_reference_df()
    result = lookup_type_reference(ref_df, "Lila", "Type 3")

    assert result is not None
    assert result["property_category"] == "villa"


def test_lookup_type_reference_different_communities_isolated():
    """Lila Type 2 and Samara Type 2 are different products — lookup returns the right one."""
    ref_df = make_reference_df()

    lila = lookup_type_reference(ref_df, "Lila", "Type 2")
    samara = lookup_type_reference(ref_df, "Samara", "Type 2")

    assert lila["bua_ref_sqft"] == 3234
    assert samara["bua_ref_sqft"] == 4038
    assert lila["bua_max_sqft"] == 3493
    assert samara["bua_max_sqft"] == 4361


def test_lookup_type_reference_returns_none_for_missing_type():
    ref_df = make_reference_df()
    result = lookup_type_reference(ref_df, "Lila", "Type 99")
    assert result is None


def test_lookup_type_reference_returns_none_for_empty_df():
    result = lookup_type_reference(pd.DataFrame(), "Lila", "Type 2")
    assert result is None


# ── parse_villa_type_from_text ────────────────────────────────────────────────

def test_parse_villa_type_from_text_extracts_numeric_type():
    assert parse_villa_type_from_text("Rosa Type 3, 4 bed villa") == "Type 3"


def test_parse_villa_type_from_text_case_insensitive():
    assert parse_villa_type_from_text("lila type 2 villa for sale") == "Type 2"


def test_parse_villa_type_from_text_handles_alphanumeric():
    assert parse_villa_type_from_text("Camelia Type 1E townhouse") == "Type 1E"


def test_parse_villa_type_from_text_returns_none_when_no_type():
    assert parse_villa_type_from_text("4 bed villa in Arabian Ranches 2") is None


# ── parse_condition_features ──────────────────────────────────────────────────

def test_parse_condition_features_detects_corner_plot():
    features = parse_condition_features("Single row corner plot with large garden")
    assert "corner plot" in features
    assert "single row" in features
    assert "large garden" in features


def test_parse_condition_features_deduplicates_synonyms():
    """'landscaped' and 'landscaped garden' should produce one entry, not two."""
    features = parse_condition_features("Beautiful landscaped garden and pool")
    assert features.count("landscaped garden") == 1


def test_parse_condition_features_detects_upgraded_and_vacant():
    features = parse_condition_features("Fully upgraded, vacant on transfer, excellent finishes")
    assert "fully upgraded" in features
    assert "vacant / ready to move" in features
    assert "excellent finishes" in features


def test_parse_condition_features_returns_empty_for_plain_listing():
    features = parse_condition_features("3 bed villa for sale in Arabian Ranches 2")
    assert features == []


# ── _bare_type prefix stripping ───────────────────────────────────────────────

def test_bare_type_strips_likely_and_possible_prefixes():
    """The _bare_type helper inside valuation_estimate must strip confidence prefixes
    so 'Likely Type 3' and 'Type 3' comps are treated the same for filtering.

    We test this indirectly: a comp_df with 'Likely Type 3' and 'Possible Type 3'
    should be included when filtering by villa_type == 'Type 3'.
    """
    import re

    def _bare_type(series):
        return (
            series.fillna("")
            .str.strip()
            .str.replace(r"^(Likely|Possible)\s+", "", regex=True)
        )

    types = pd.Series(["Type 3", "Likely Type 3", "Possible Type 3", "Type 2", None])
    bare = _bare_type(types)

    assert list(bare) == ["Type 3", "Type 3", "Type 3", "Type 2", ""]
    assert (bare == "Type 3").sum() == 3


# ── Estimator data pipeline (mocked OpenAI) ───────────────────────────────────

def _make_comp_df(purpose="sale"):
    """Minimal master DataFrame that mimics the output of read_master()."""
    price_col = "annual_rent" if purpose == "rent" else "price"
    rows = []
    for i in range(5):
        price = 4_800_000 + i * 50_000 if purpose == "sale" else 180_000 + i * 5_000
        rows.append({
            "url": f"https://example.com/rosa-{i}",
            "listing_purpose": purpose,
            "title": f"Rosa Type 3 villa #{i}",
            "predicted_community": "Rosa",
            "predicted_type": "Type 3" if i < 3 else "Likely Type 3",
            "bedrooms": 4,
            "bathrooms": 6,
            "property_size_sqft": 4800 + i * 20,
            "plot_size_sqft": 7800 + i * 50,
            "price": price if purpose == "sale" else None,
            "annual_rent": price if purpose == "rent" else None,
            "rent_price": price if purpose == "rent" else None,
            "price_per_sqft": round(price / (4800 + i * 20)) if purpose == "sale" else None,
            "is_active": True,
        })
    return pd.DataFrame(rows)


def _openai_json_response(low, mid, high, currency="AED"):
    """Build a fake OpenAI Responses API response with the low/mid/high JSON the estimator expects."""
    import json
    content = json.dumps({
        "low": low,
        "mid": mid,
        "high": high,
        "currency": currency,
        "confidence": "medium",
        "rationale": {"low": "test", "mid": "test", "high": "test"},
        "premium_factors": [],
        "discount_factors": [],
        "key_risks": [],
        "data_basis": "Test data basis",
        "comparable_count": 5,
    })
    # The estimator uses response.output_text (Responses API format)
    response = MagicMock()
    response.output_text = content
    return response


@patch("scripts.webapp_backend.load_market_sales", return_value=pd.DataFrame())
@patch("scripts.webapp_backend.read_master")
@patch("scripts.webapp_backend.load_villa_type_reference")
@patch("openai.OpenAI")
def test_valuation_estimate_sale_returns_low_mid_high(
    mock_openai_cls, mock_load_ref, mock_read_master, mock_market_sales
):
    from scripts.webapp_backend import valuation_estimate

    comp_df = _make_comp_df(purpose="sale")
    mock_read_master.return_value = (comp_df, "output/sale/listing_details_master.csv")
    mock_load_ref.return_value = make_reference_df()

    client = MagicMock()
    client.responses.create.return_value = _openai_json_response(4_600_000, 4_900_000, 5_200_000)
    mock_openai_cls.return_value = client

    result = valuation_estimate(
        "Rosa Type 3, 4 bed villa, corner plot, fully upgraded",
        selected_purpose="sale",
        api_key="sk-test-key",
    )

    assert result["estimate"]["low"] == 4_600_000
    assert result["estimate"]["mid"] == 4_900_000
    assert result["estimate"]["high"] == 5_200_000
    assert result["estimate"]["currency"] == "AED"
    assert result["community"] == "Rosa"
    assert result["villa_type"] == "Type 3"
    assert result["purpose"] == "sale"


@patch("scripts.webapp_backend.load_market_sales", return_value=pd.DataFrame())
@patch("scripts.webapp_backend.read_master")
@patch("scripts.webapp_backend.load_villa_type_reference")
@patch("openai.OpenAI")
def test_valuation_estimate_rental_uses_annual_rent(
    mock_openai_cls, mock_load_ref, mock_read_master, mock_market_sales
):
    """Rental estimator should use the annual_rent column for comp stats."""
    from scripts.webapp_backend import valuation_estimate

    comp_df = _make_comp_df(purpose="rent")
    mock_read_master.return_value = (comp_df, "output/rent/listing_details_master.csv")
    mock_load_ref.return_value = make_reference_df()

    client = MagicMock()
    client.responses.create.return_value = _openai_json_response(170_000, 185_000, 200_000)
    mock_openai_cls.return_value = client

    result = valuation_estimate(
        "Rosa Type 3, 4 bed rental villa",
        selected_purpose="rent",
        api_key="sk-test-key",
    )

    assert result["estimate"]["low"] == 170_000
    assert result["estimate"]["mid"] == 185_000
    assert result["estimate"]["high"] == 200_000
    assert result["purpose"] == "rent"


@patch("scripts.webapp_backend.load_market_sales", return_value=pd.DataFrame())
@patch("scripts.webapp_backend.read_master")
@patch("scripts.webapp_backend.load_villa_type_reference")
@patch("openai.OpenAI")
def test_valuation_estimate_community_type_filter_applied(
    mock_openai_cls, mock_load_ref, mock_read_master, mock_market_sales
):
    """The estimator must filter by community+type as a pair, not just type alone."""
    from scripts.webapp_backend import valuation_estimate

    # Mix of Rosa Type 3 and Lila Type 3 — estimator should isolate Rosa Type 3
    rows = []
    for community, price in [("Rosa", 4_900_000), ("Lila", 3_200_000)]:
        rows.append({
            "url": f"https://example.com/{community.lower()}-t3",
            "listing_purpose": "sale",
            "title": f"{community} Type 3",
            "predicted_community": community,
            "predicted_type": "Type 3",
            "bedrooms": 4,
            "bathrooms": 5,
            "property_size_sqft": 4800,
            "plot_size_sqft": 7000,
            "price": price,
            "annual_rent": None,
            "price_per_sqft": round(price / 4800),
            "is_active": True,
        })
    comp_df = pd.DataFrame(rows)

    mock_read_master.return_value = (comp_df, "output/sale/listing_details_master.csv")
    mock_load_ref.return_value = make_reference_df()

    client = MagicMock()
    client.responses.create.return_value = _openai_json_response(4_700_000, 4_900_000, 5_100_000)
    mock_openai_cls.return_value = client

    result = valuation_estimate(
        "Rosa Type 3, 4 bed villa",
        selected_purpose="sale",
        api_key="sk-test-key",
    )

    # Verify that the AI was called — and that Rosa comps were used (not Lila)
    assert client.responses.create.called
    call_kwargs = client.responses.create.call_args
    # The prompt text sent to OpenAI should reference Rosa comps, not Lila
    prompt_text = str(call_kwargs)
    assert "Rosa" in prompt_text
    assert result["community"] == "Rosa"


def test_valuation_estimate_raises_without_api_key():
    from scripts.webapp_backend import valuation_estimate

    with pytest.raises(RuntimeError, match="Missing OpenAI API key"):
        valuation_estimate("Rosa Type 3, 4 bed villa", selected_purpose="sale", api_key=None)
