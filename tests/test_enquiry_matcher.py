import pandas as pd

from scripts.enquiry_matcher import match_enquiry, parse_bedrooms, parse_budget, searchable_active_row
from scripts.match_enquiry import safe_filename_part


def test_parse_budget_handles_short_values():
    assert parse_budget("200k") == 200000
    assert parse_budget("200,000") == 200000
    assert parse_budget("1.5m") == 1500000
    assert parse_budget("5.5million") == 5500000
    assert parse_budget("5.5 mil") == 5500000
    assert parse_budget("220 thousand") == 220000


def test_parse_bedrooms():
    assert parse_bedrooms("3 beds") == 3
    assert parse_bedrooms("4BR") == 4
    assert parse_bedrooms("5") == 5


def test_safe_filename_part():
    assert safe_filename_part("Arabian Ranches 2 / Casa", "anywhere") == "arabian_ranches_2_casa"


def test_searchable_active_row_keeps_stale_false_without_status():
    assert searchable_active_row({"is_active": False, "active_check_status": ""})
    assert searchable_active_row({"is_active": False, "active_check_status": pd.NA})
    assert searchable_active_row({"is_active": False})
    assert not searchable_active_row({"is_active": False, "active_check_status": "removed"})


def test_match_enquiry_ranks_casa_dog_friendly_options():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/casa",
            "title": "Rent in Casa: Landscaped | Close to Pool",
            "annual_rent": 225000,
            "bedrooms": 3,
            "bathrooms": 4,
            "predicted_community": "Casa",
            "description": "Landscaped garden close to pool and park.",
        },
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/rosa",
            "title": "Rent in Rosa: Type 5",
            "annual_rent": 250000,
            "bedrooms": 6,
            "bathrooms": 7,
            "predicted_community": "Rosa",
            "description": "Large family villa.",
        },
    ])
    enquiry = {
        "purpose": "rent",
        "budget": 200000,
        "stretch_budget": 230000,
        "bedrooms": 3,
        "community": "Casa",
        "must_haves": ["dog"],
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/casa"
    assert "garden" in matches_df.iloc[0]["outdoor_matches"]
    assert matches_df.iloc[0]["budget_gap"] == -5000


def test_match_enquiry_treats_ar2_as_parent_community_and_outdoor_intent():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/palma-5",
            "title": "Rent in Palma: 5BR with garden",
            "annual_rent": 320000,
            "bedrooms": 5,
            "bathrooms": 5,
            "predicted_community": "Palma",
            "description": "Large outdoor seating area and landscaped garden.",
        },
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/palma-3",
            "title": "Rent in Palma: 3BR",
            "annual_rent": 300000,
            "bedrooms": 3,
            "bathrooms": 3,
            "predicted_community": "Palma",
            "description": "Garden.",
        },
    ])
    enquiry = {
        "purpose": "rent",
        "budget": 340000,
        "stretch_budget": 340000,
        "bedrooms": 5,
        "community": "Arabian Ranches 2",
        "must_haves": ["bbq sitting outer area"],
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/palma-5"
    assert "outdoor" in matches_df.iloc[0]["outdoor_matches"]


def test_sale_budget_prefers_villa_near_budget_over_cheap_townhouse():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/camelia-townhouse",
            "title": "Sale in Camelia: 3BR townhouse",
            "price": 3200000,
            "bedrooms": 3,
            "bathrooms": 4,
            "predicted_community": "Camelia",
            "description": "Townhouse in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/casa-villa",
            "title": "Sale in Casa: Type 1 villa",
            "price": 5500000,
            "bedrooms": 3,
            "bathrooms": 4,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "budget": 5500000,
        "stretch_budget": 5500000,
        "bedrooms": 3,
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/casa-villa"
    assert "villa stock" in matches_df.iloc[0]["match_reasons"]


def test_sale_tie_breaker_prefers_closer_to_budget():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/lower-price-villa",
            "title": "Sale in Reem: 3 bed villa",
            "price": 5000000,
            "bedrooms": 3,
            "predicted_community": "Reem",
            "description": "Villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/near-budget-villa",
            "title": "Sale in Casa: 3 bed villa",
            "price": 5500000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "budget": 5500000,
        "stretch_budget": 5500000,
        "bedrooms": 3,
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/near-budget-villa"


def test_casa_enquiry_prefers_villas_and_related_communities_over_townhouses():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/camelia",
            "title": "Rent in Camelia: 3BR townhouse vacant June",
            "annual_rent": 180000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "description_json": '{"text": "Townhouse available in June."}',
        },
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/palma",
            "title": "Rent in Palma: 3BR villa vacant June",
            "annual_rent": 220000,
            "bedrooms": 3,
            "predicted_community": "Palma",
            "description_json": '{"text": "Villa vacant in June with landscaped garden."}',
        },
    ])
    enquiry = {
        "purpose": "rent",
        "budget": 200000,
        "stretch_budget": 230000,
        "budget_floor": 160000,
        "bedrooms": 3,
        "community": "Casa",
        "must_haves": [],
        "preferred_category": "villa",
        "move_month": 6,
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/palma"
    assert "similar community" in matches_df.iloc[0]["match_reasons"]
    assert "mentions requested move month" in matches_df.iloc[0]["match_reasons"]


def test_budget_floor_filters_properties_that_are_too_cheap_for_best_value_search():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/cheap",
            "title": "Sale in Reem: cheap 3 bed",
            "price": 3900000,
            "bedrooms": 3,
            "predicted_community": "Reem",
            "description": "Villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/value",
            "title": "Sale in Casa: 3 bed Type 2",
            "price": 5500000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "budget": 5500000,
        "stretch_budget": 5940000,
        "budget_floor": 4510000,
        "bedrooms": 3,
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
    }

    matches_df = match_enquiry(master_df, enquiry, limit=5)

    assert matches_df["url"].tolist() == ["https://example.com/value"]


def test_search_ceiling_filters_properties_that_are_too_expensive():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/within-ceiling",
            "title": "Sale in Casa: 3 bed",
            "price": 5900000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/above-ceiling",
            "title": "Sale in Casa: 3 bed",
            "price": 6200000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "budget": 5500000,
        "stretch_budget": 5940000,
        "budget_floor": 4510000,
        "bedrooms": 3,
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
    }

    matches_df = match_enquiry(master_df, enquiry, limit=5)

    assert matches_df["url"].tolist() == ["https://example.com/within-ceiling"]


def test_requested_villa_type_can_outrank_cheaper_wrong_type():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/type-1",
            "title": "Sale in Casa: cheap Type 1",
            "price": 5500000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "predicted_type": "Type 1",
            "description": "Villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/type-2",
            "title": "Sale in Casa: Type 2 single row",
            "price": 5900000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "predicted_type": "Type 2",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "budget": 5500000,
        "stretch_budget": 5940000,
        "budget_floor": 4510000,
        "bedrooms": 3,
        "community": "Casa",
        "must_haves": [],
        "preferred_category": "villa",
        "preferred_villa_types": ["Type 2", "Type 3"],
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/type-2"
    assert "matches requested Type 2" in matches_df.iloc[0]["match_reasons"]


def test_explicit_villa_enquiry_excludes_townhouse_stock():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/camelia-townhouse",
            "title": "Sale in Camelia: 3BR townhouse",
            "price": 3100000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "description": "Townhouse in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/reem-townhouse",
            "title": "Sale in Reem: 3BR VOT",
            "price": 4900000,
            "bedrooms": 3,
            "predicted_community": "Reem",
            "description": "Arabian Ranches 2 property.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/casa-villa",
            "title": "Sale in Casa: 3BR villa",
            "price": 5500000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "budget": 5500000,
        "stretch_budget": 5940000,
        "budget_floor": None,
        "bedrooms": 3,
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
        "strict_category": True,
    }

    matches_df = match_enquiry(master_df, enquiry, limit=5)

    assert matches_df["url"].tolist() == ["https://example.com/casa-villa"]


def test_soft_intent_scoring_boosts_description_matches_after_price_filter():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/basic",
            "title": "Sale in Camelia: 3BR townhouse",
            "price": 3900000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "description": "Townhouse in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/ready",
            "title": "Sale in Camelia: Ready to Move | Upgraded",
            "price": 4000000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "description": "Well maintained modern townhouse with landscaped garden.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/too-high",
            "title": "Sale in Camelia: Ready to Move | Upgraded",
            "price": 5000000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "description": "Well maintained modern townhouse.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "raw_prompt": "nice ready to move home around 4m",
        "budget": 4000000,
        "stretch_budget": 4320000,
        "budget_floor": 3280000,
        "bedrooms": 3,
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": None,
    }

    matches_df = match_enquiry(master_df, enquiry, limit=5)

    assert matches_df["url"].tolist() == [
        "https://example.com/ready",
        "https://example.com/basic",
    ]
    assert "soft match clues" in matches_df.iloc[0]["match_reasons"]


def test_soft_intent_scoring_uses_real_listing_language():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/plain",
            "title": "Sale in Camelia: Standard home",
            "price": 4000000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "description": "Townhouse in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/listing-language",
            "title": "Sale in Camelia: Bright Family Home",
            "price": 4000000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "description": "Spacious open-plan living with natural light, private landscaped garden, and pool and park access.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "raw_prompt": "nice spacious family home around 4m with garden",
        "budget": 4000000,
        "stretch_budget": 4320000,
        "budget_floor": 3280000,
        "bedrooms": 3,
        "community": "Arabian Ranches 2",
        "must_haves": ["garden"],
        "preferred_category": None,
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/listing-language"
    assert "natural light" in matches_df.iloc[0]["match_reasons"]
    assert "private landscaped garden" in matches_df.iloc[0]["match_reasons"]


def test_soft_intent_scoring_does_not_match_inside_words():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/unfurnished",
            "title": "Sale in Camelia: Unfurnished Home",
            "price": 4000000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "description": "Unfurnished townhouse in Arabian Ranches 2 with modern layout.",
        }
    ])
    enquiry = {
        "purpose": "sale",
        "raw_prompt": "nice furnished ready home around 4m",
        "budget": 4000000,
        "stretch_budget": 4320000,
        "budget_floor": 3280000,
        "bedrooms": 3,
        "community": "Arabian Ranches 2",
        "must_haves": ["furnished"],
        "preferred_category": None,
    }

    matches_df = match_enquiry(master_df, enquiry, limit=1)

    assert "furnished" not in matches_df.iloc[0]["match_reasons"]


def test_upgrade_potential_intent_penalizes_already_finished_stock():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/finished",
            "title": "Sale in Palma: Extended | Corner Plot | Upgraded",
            "price": 8200000,
            "bedrooms": 4,
            "predicted_community": "Palma",
            "description": "Fully upgraded and extended luxury villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/blank-canvas",
            "title": "Sale in Casa: Vacant 4 bedroom + Maid's Room + Study Room",
            "price": 7800000,
            "bedrooms": 4,
            "predicted_community": "Casa",
            "description": "Blank canvas villa with large plot and renovation opportunity.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "raw_prompt": "4 bed villa in Arabian Ranches 2",
        "search_intent": "upgrade_potential",
        "budget": None,
        "stretch_budget": None,
        "budget_floor": None,
        "bedrooms": 4,
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/blank-canvas"
    assert "blank canvas" in matches_df.iloc[0]["match_reasons"]
    assert "fully upgraded" in matches_df.iloc[1]["match_reasons"]


def test_move_in_ready_intent_rewards_finished_stock():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/project",
            "title": "Sale in Casa: Blank Canvas",
            "price": 7800000,
            "bedrooms": 4,
            "predicted_community": "Casa",
            "description": "Original condition villa and renovation opportunity.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/ready",
            "title": "Sale in Palma: Fully Upgraded | Ready To Move",
            "price": 8200000,
            "bedrooms": 4,
            "predicted_community": "Palma",
            "description": "Fully upgraded, renovated, turnkey family home.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "raw_prompt": "4 bed villa in Arabian Ranches 2",
        "search_intent": "move_in_ready",
        "budget": None,
        "stretch_budget": None,
        "budget_floor": None,
        "bedrooms": 4,
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
    }

    matches_df = match_enquiry(master_df, enquiry, limit=2)

    assert matches_df.iloc[0]["url"] == "https://example.com/ready"
    assert "ready to move" in matches_df.iloc[0]["match_reasons"]
