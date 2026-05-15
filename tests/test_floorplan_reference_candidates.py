import pandas as pd

from scripts.build_floorplan_reference_candidates import build_candidate_rows


def test_build_candidate_rows_uses_repeated_detected_listing_types():
    master_df = pd.DataFrame([
        {
            "predicted_community": "Casa",
            "detected_type_from_description": "Type 3",
            "url": "https://example.com/casa-1",
            "bedrooms": 4,
            "bathrooms": 5,
            "property_size_sqft": 4359,
            "plot_size_sqft": 4650,
            "bua_from_description": 3538,
            "plot_from_description": 4650,
            "price": 6200000,
            "is_active": True,
        },
        {
            "predicted_community": "Casa",
            "detected_type_from_description": "type 3",
            "url": "https://example.com/casa-2",
            "bedrooms": 4,
            "bathrooms": 5,
            "property_size_sqft": 4360,
            "plot_size_sqft": 4651,
            "bua_from_description": 3539,
            "plot_from_description": 4651,
            "price": 6300000,
            "is_active": True,
        },
        {
            "predicted_community": "Casa",
            "detected_type_from_description": None,
            "url": "https://example.com/casa-no-type",
            "bedrooms": 4,
        },
    ])
    reference_df = pd.DataFrame([
        {
            "community": "Casa",
            "type": "Type 3",
            "property_category": "villa",
            "bua_reference_sqft": 3538,
            "plot_reference_sqft": 4650,
            "pf_bua": None,
            "pf_bua_upgraded": None,
            "pf_plot": None,
            "pf_plot_a": None,
            "area_reference_sqft": None,
        }
    ])

    candidates_df = build_candidate_rows(master_df, reference_df, purpose="sale", min_evidence=2)
    candidate = candidates_df.iloc[0].to_dict()

    assert len(candidates_df) == 1
    assert candidate["community"] == "Casa"
    assert candidate["type"] == "Type 3"
    assert candidate["evidence_count"] == 2
    assert candidate["bedrooms_median"] == 4
    assert candidate["property_size_median"] == 4360
    assert candidate["reference_status"] == "already_in_reference"
    assert candidate["reference_bua_values"] == "3538"
    assert "https://example.com/casa-1" in candidate["example_urls"]


def test_build_candidate_rows_flags_missing_reference_type():
    master_df = pd.DataFrame([
        {
            "predicted_community": "Samara",
            "detected_type_from_description": "Type 9",
            "url": "https://example.com/samara-1",
            "bedrooms": 5,
        },
        {
            "predicted_community": "Samara",
            "detected_type_from_description": "Type 9",
            "url": "https://example.com/samara-2",
            "bedrooms": 5,
        },
    ])
    reference_df = pd.DataFrame([
        {
            "community": "Samara",
            "type": "Type 1",
            "property_category": "villa",
        }
    ])

    candidates_df = build_candidate_rows(master_df, reference_df, purpose="sale", min_evidence=2)
    candidate = candidates_df.iloc[0].to_dict()

    assert candidate["reference_status"] == "missing_from_reference"
    assert "not in the reference" in candidate["candidate_note"]
