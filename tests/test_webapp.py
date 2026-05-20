import pandas as pd

from scripts.webapp import (
    ai_fallback_prompt,
    ai_scenario_prompt,
    build_market_context,
    build_over_budget_dataframe,
    build_budget_fallback_dataframe,
    build_budget_reality_primary_dataframe,
    add_similar_listing_warnings,
    lookup_owner,
    lookup_owner_in_df,
    match_enquiry,
    match_prompt,
    parse_prompt,
    quick_listing_query,
    rows_payload,
)


def test_parse_prompt_understands_sale_enquiry_with_split_bedrooms():
    enquiry = parse_prompt("after a 3/4 bed in ar2 at 5.5m budget", "auto")

    assert enquiry["purpose"] == "sale"
    assert enquiry["budget"] == 5_500_000
    assert enquiry["stretch_budget"] == 5_940_000
    assert enquiry["budget_strategy"] == "8% negotiation stretch"
    assert enquiry["bedrooms_options"] == [3, 4]
    assert enquiry["bedrooms_label"] == "3/4"
    assert enquiry["community"] == "Arabian Ranches 2"
    assert enquiry["preferred_category"] == "villa"


def test_parse_prompt_understands_million_word_budget():
    enquiry = parse_prompt("after a 3/4 bed budget of 5.5million", "sale")

    assert enquiry["purpose"] == "sale"
    assert enquiry["budget"] == 5_500_000
    assert enquiry["stretch_budget"] == 5_940_000
    assert enquiry["bedrooms_options"] == [3, 4]


def test_parse_prompt_understands_rental_enquiry():
    enquiry = parse_prompt("3 bed rental in casa under 220k, have a pet dog", "auto")

    assert enquiry["purpose"] == "rent"
    assert enquiry["budget"] == 220_000
    assert enquiry["stretch_budget"] == 220_000
    assert enquiry["bedrooms_options"] == [3]
    assert enquiry["community"] == "Casa"
    assert "dog" in enquiry["must_haves"]
    assert "pet" in enquiry["must_haves"]
    assert enquiry["preferred_category"] == "villa"


def test_parse_prompt_respects_explicit_stretch_budget():
    enquiry = parse_prompt("4 bed in ar2 budget 5.5m stretch 5.8m", "auto")

    assert enquiry["budget"] == 5_500_000
    assert enquiry["stretch_budget"] == 5_800_000
    assert enquiry["budget_strategy"] == ""


def test_parse_prompt_does_not_treat_bedrooms_as_budget():
    enquiry = parse_prompt("3 bed in casa move in end of june", "rent")

    assert enquiry["budget"] is None
    assert enquiry["bedrooms_options"] == [3]
    assert enquiry["move_month"] == 6
    assert enquiry["preferred_category"] == "villa"


def test_parse_prompt_does_not_treat_arabian_ranches_2_as_bedrooms():
    enquiry = parse_prompt("nice ready to move home in Arabian Ranches 2 around 4m, sale", "auto")

    assert enquiry["purpose"] == "sale"
    assert enquiry["budget"] == 4_000_000
    assert enquiry["bedrooms_options"] == []
    assert enquiry["bedrooms"] is None
    assert enquiry["bedrooms_label"] == "Any"
    assert enquiry["community"] == "Arabian Ranches 2"


def test_parse_prompt_accepts_explicit_search_intent():
    enquiry = parse_prompt(
        "4 bed villa in Arabian Ranches 2 budget doesn't matter",
        "sale",
        "upgrade_potential",
    )

    assert enquiry["search_intent"] == "upgrade_potential"
    assert enquiry["bedrooms_options"] == [4]
    assert enquiry["preferred_category"] == "villa"


def test_parse_prompt_accepts_custom_listing_scope():
    enquiry = parse_prompt(
        "4 bed villa around 7m in Azalea",
        "sale",
        "best_value",
        listing_scope="custom",
        listing_communities=["Azalea", "Lila"],
        market_scope="custom",
        market_communities=["Azalea", "Lila"],
    )

    assert enquiry["listing_scope_mode"] == "custom"
    assert enquiry["listing_communities"] == ["Azalea", "Lila"]
    assert enquiry["market_scope_mode"] == "custom"
    assert enquiry["market_communities"] == ["Azalea", "Lila"]


def test_quick_listing_query_filters_directly(monkeypatch, tmp_path):
    data = pd.DataFrame([
        {
            "url": "https://example.com/villa-for-sale-a",
            "title": "Sale in Lila: 5 Bed Villa",
            "price": 1_100_000,
            "bedrooms": 5,
            "bathrooms": 5,
            "property_size_sqft": 4000,
            "predicted_community": "Lila",
            "predicted_type": "Type 1",
        },
        {
            "url": "https://example.com/villa-for-sale-b",
            "title": "Sale in Lila: 4 Bed Villa",
            "price": 900_000,
            "bedrooms": 4,
            "bathrooms": 4,
            "property_size_sqft": 3000,
            "predicted_community": "Lila",
            "predicted_type": "Type 2",
        },
        {
            "url": "https://example.com/townhouse-for-sale-c",
            "title": "Sale in Lila: 5 Bed Townhouse",
            "price": 1_000_000,
            "bedrooms": 5,
            "bathrooms": 4,
            "property_size_sqft": 2500,
            "predicted_community": "Lila",
            "predicted_type": "Type 3",
        },
    ])
    fake_path = tmp_path / "listing_details_master.csv"

    monkeypatch.setattr("webapp_backend.read_master", lambda purpose: (data, fake_path))

    result = quick_listing_query(
        selected_purpose="sale",
        min_beds="5",
        max_beds="6",
        max_price="1.2m",
        community="Lila",
        category="villa",
    )

    assert result["report_title"] == "Quick Query Results"
    assert result["enquiry"]["bedrooms_label"] == "5-6"
    assert len(result["matches"]) == 1
    assert result["matches"][0]["url"] == "https://example.com/villa-for-sale-a"


def test_parse_prompt_adds_budget_floor_for_best_value_search():
    enquiry = parse_prompt("3 bed in ar2 at 5.5m budget best value", "sale")

    assert enquiry["budget_floor"] == 4_510_000


def test_parse_prompt_understands_requested_villa_types():
    enquiry = parse_prompt("3 bed in casa type 2 or type 3 around 5.5m", "sale")

    assert enquiry["preferred_villa_types"] == ["Type 2", "Type 3"]


def test_parse_prompt_marks_explicit_villa_as_strict_category():
    enquiry = parse_prompt("3 bed villa in ar2 around 5.5m", "sale")

    assert enquiry["preferred_category"] == "villa"
    assert enquiry["strict_category"] is True


def test_parse_prompt_understands_budget_reality_mode_and_no_townhouse():
    enquiry = parse_prompt(
        "3 bed villa in Arabian Ranches 2 max 210k. Client does not want a townhouse. Build a budget reality case.",
        "rent",
    )

    assert enquiry["budget"] == 210000
    assert enquiry["stretch_budget"] == 210000
    assert enquiry["preferred_category"] == "villa"
    assert enquiry["strict_category"] is True
    assert enquiry["budget_reality_mode"] is True


def test_split_bedroom_search_keeps_best_score_before_deduping():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/four-bed",
            "title": "Sale in Casa: 4 bed villa",
            "price": 5400000,
            "bedrooms": 4,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        }
    ])
    frames = []

    for bedroom in [3, 4]:
        frames.append(match_enquiry(
            master_df,
            {
                "purpose": "sale",
                "budget": 5500000,
                "stretch_budget": 5940000,
                "bedrooms": bedroom,
                "community": "Arabian Ranches 2",
                "must_haves": [],
                "preferred_category": "villa",
            },
            limit=10,
        ))

    matches_df = pd.concat(frames, ignore_index=True)
    matches_df = matches_df.sort_values(["match_score", "budget_distance"], ascending=[False, True]).drop_duplicates(subset=["url"])

    assert "4 bedrooms" in matches_df.iloc[0]["match_reasons"]


def test_lookup_owner_matches_property_finder_url():
    owner_df = pd.DataFrame([
        {
            "Date": "14/05/2026",
            "Sell/Rent": "Rent & Buy",
            "Owners": "Philip George, Reena Philip Gee Varghese",
            "Numbers": "971504536785, 971555655360",
            "No.": "182",
            "Street": "4 street",
            "Community": "Casa",
            "Area": "Arabian Ranches 2",
            "Beds": "3",
            "GFA": "4,359",
            "BUA": "3,248",
            "Type": "Type 1",
            "Asking": "5,500,000",
            "Rental": "",
            "Notes": "sample",
            "Link": (
                "https://www.propertyfinder.ae/en/plp/rent/villa-for-rent-dubai-arabian-ranches-2-casa-74247977.html, "
                "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-dubai-arabian-ranches-2-casa-73846619.html"
            ),
        }
    ])

    result = lookup_owner_in_df(
        owner_df,
        "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-dubai-arabian-ranches-2-casa-73846619.html",
    )

    assert result["found"] is True
    assert result["match_type"] == "exact_url"
    assert result["lead"]["owners"] == "Philip George, Reena Philip Gee Varghese"
    assert result["lead"]["property"] == "182, 4 street, Casa, Arabian Ranches 2"
    assert len(result["propertyfinder_urls"]) == 2


def test_lookup_owner_handles_missing_file(tmp_path):
    result = lookup_owner(
        "https://www.propertyfinder.ae/en/plp/buy/example.html",
        owner_file=tmp_path / "missing.csv",
    )

    assert result["found"] is False
    assert "not found" in result["message"]


def test_build_market_context_uses_relevant_dxb_rows(tmp_path):
    market_file = tmp_path / "market.csv"
    rows = [
        {
            "community": "Camelia",
            "price": 3100000 + (index * 10000),
            "price_per_sqft": 1800 + index,
            "size_sqft": 1700,
            "beds": 3,
            "sold_date": f"{index + 1:02d} Apr 2026",
            "median_price": 5915000,
            "median_price_per_sqft": 1400,
            "transactions": 124,
            "rental_yield_percent": 6,
        }
        for index in range(8)
    ]
    rows.append({
        "community": "Casa",
        "price": 5900000,
        "price_per_sqft": 1350,
        "size_sqft": 4359,
        "beds": 3,
        "sold_date": "05 Dec 2025",
        "median_price": 5915000,
        "median_price_per_sqft": 1400,
        "transactions": 124,
        "rental_yield_percent": 6,
    })
    pd.DataFrame(rows).to_csv(market_file, index=False)
    matches_df = pd.DataFrame([
        {"price": 3200000, "price_per_sqft": 1600},
        {"price": 3300000, "price_per_sqft": 1650},
    ])
    enquiry = {
        "purpose": "sale",
        "community": "Camelia",
        "bedrooms": 3,
    }

    context = build_market_context(enquiry, matches_df, market_file=market_file)

    assert context["dxb_report_summary"]["median_price"] == 5915000
    assert context["recent_transaction_stats"]["price"]["median"] == 3135000
    assert context["active_shortlist"]["asking_price"]["median"] == 3250000
    assert len(context["recent_transactions"]) == 5


def test_build_market_context_supports_similar_community_scope(tmp_path):
    market_file = tmp_path / "market.csv"
    pd.DataFrame([
        {
            "community": "Palma",
            "price": 6900000,
            "price_per_sqft": 1300,
            "size_sqft": 5308,
            "beds": 4,
            "sold_date": "12 Mar 2026",
            "median_price": 5915000,
            "median_price_per_sqft": 1400,
            "transactions": 124,
        },
        {
            "community": "Lila",
            "price": 6800000,
            "price_per_sqft": 1500,
            "size_sqft": 4359,
            "beds": 4,
            "sold_date": "10 Mar 2026",
            "median_price": 5915000,
            "median_price_per_sqft": 1400,
            "transactions": 124,
        },
        {
            "community": "Casa",
            "price": 7800000,
            "price_per_sqft": 1677,
            "size_sqft": 4650,
            "beds": 4,
            "sold_date": "09 Mar 2026",
            "median_price": 5915000,
            "median_price_per_sqft": 1400,
            "transactions": 124,
        },
    ]).to_csv(market_file, index=False)
    matches_df = pd.DataFrame([
        {"price": 7000000, "price_per_sqft": 1400, "predicted_community": "Palma"},
    ])
    enquiry = {
        "purpose": "sale",
        "community": "Palma",
        "bedrooms": 4,
        "market_scope_mode": "similar",
    }

    context = build_market_context(enquiry, matches_df, market_file=market_file)

    assert context["scope"]["comp_communities"] == ["Casa", "Lila", "Palma"]
    assert context["recent_transaction_stats"]["price"]["count"] == 3
    assert {row["community"] for row in context["recent_transactions"]} == {"Palma", "Lila", "Casa"}


def test_build_market_context_supports_custom_community_scope(tmp_path):
    market_file = tmp_path / "market.csv"
    pd.DataFrame([
        {
            "community": "Palma",
            "price": 6900000,
            "price_per_sqft": 1300,
            "size_sqft": 5308,
            "beds": 4,
            "sold_date": "12 Mar 2026",
            "median_price": 5915000,
            "median_price_per_sqft": 1400,
            "transactions": 124,
        },
        {
            "community": "Casa",
            "price": 7800000,
            "price_per_sqft": 1677,
            "size_sqft": 4650,
            "beds": 4,
            "sold_date": "09 Mar 2026",
            "median_price": 5915000,
            "median_price_per_sqft": 1400,
            "transactions": 124,
        },
        {
            "community": "Rasha",
            "price": 11200000,
            "price_per_sqft": 1430,
            "size_sqft": 7833,
            "beds": 4,
            "sold_date": "08 Mar 2026",
            "median_price": 5915000,
            "median_price_per_sqft": 1400,
            "transactions": 124,
        },
    ]).to_csv(market_file, index=False)
    matches_df = pd.DataFrame([
        {"price": 7000000, "price_per_sqft": 1400, "predicted_community": "Palma"},
    ])
    enquiry = {
        "purpose": "sale",
        "community": "Arabian Ranches 2",
        "bedrooms": 4,
        "market_scope_mode": "custom",
        "market_communities": ["Palma", "Casa"],
    }

    context = build_market_context(enquiry, matches_df, market_file=market_file)

    assert context["scope"]["market_scope_mode"] == "custom"
    assert context["scope"]["comp_communities"] == ["Palma", "Casa"]
    assert {row["community"] for row in context["recent_transactions"]} == {"Palma", "Casa"}


def test_build_market_context_uses_relevant_rental_rows(tmp_path):
    rental_file = tmp_path / "rentals.csv"
    pd.DataFrame([
        {
            "Location": "Casa",
            "Community": "Arabian Ranches 2",
            "Property Type": "Villa",
            "Bedrooms": 3,
            "Size sqft": 4359,
            "Rental AED": 240000,
            "Rental Yield %": 5.5,
            "Status": "New",
            "Start Date": "13 May, 2026",
        },
        {
            "Location": "Casa",
            "Community": "Arabian Ranches 2",
            "Property Type": "Villa",
            "Bedrooms": 3,
            "Size sqft": 4359,
            "Rental AED": 220000,
            "Rental Yield %": 5.1,
            "Status": "Renewed",
            "Start Date": "10 May, 2026",
        },
        {
            "Location": "Samara",
            "Community": "Arabian Ranches 2",
            "Property Type": "Villa",
            "Bedrooms": 4,
            "Size sqft": 3868,
            "Rental AED": 300000,
            "Rental Yield %": 5.8,
            "Status": "New",
            "Start Date": "09 May, 2026",
        },
    ]).to_csv(rental_file, index=False)
    matches_df = pd.DataFrame([
        {"annual_rent": 230000, "rent_per_sqft": 52},
        {"annual_rent": 250000, "rent_per_sqft": 57},
    ])
    enquiry = {
        "purpose": "rent",
        "community": "Casa",
        "bedrooms": 3,
    }

    context = build_market_context(enquiry, matches_df, market_file=rental_file)

    assert context["scope"]["purpose"] == "rent"
    assert context["recent_rental_stats"]["annual_rent"]["median"] == 230000
    assert context["active_shortlist"]["asking_price"]["median"] == 240000
    assert len(context["recent_rental_transactions"]) == 2


def test_over_budget_watchlist_is_separate_from_main_matches():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/within",
            "title": "Sale in Casa: within budget",
            "price": 4300000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/watch",
            "title": "Sale in Casa: above budget",
            "price": 5500000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/too-high",
            "title": "Sale in Casa: too high",
            "price": 7000000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])
    enquiry = {
        "purpose": "sale",
        "budget": 4000000,
        "stretch_budget": 4320000,
        "budget_floor": 3280000,
        "bedrooms": 3,
        "bedrooms_options": [3],
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
    }
    matches_df = match_enquiry(master_df, enquiry, limit=10)

    watchlist_df = build_over_budget_dataframe(enquiry, master_df, matches_df, limit=5)

    assert matches_df["url"].tolist() == ["https://example.com/within"]
    assert watchlist_df["url"].tolist() == ["https://example.com/watch"]


def test_match_prompt_custom_listing_scope_filters_communities(monkeypatch):
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/azalea",
            "title": "Sale in Azalea: 4 bed villa",
            "price": 7000000,
            "bedrooms": 4,
            "predicted_community": "Azalea",
            "description": "Villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/lila",
            "title": "Sale in Lila: 4 bed villa",
            "price": 6800000,
            "bedrooms": 4,
            "predicted_community": "Lila",
            "description": "Villa in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/casa",
            "title": "Sale in Casa: 4 bed villa",
            "price": 6900000,
            "bedrooms": 4,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])

    monkeypatch.setattr("webapp_backend.read_master", lambda purpose: (master_df, "memory.csv"))

    result = match_prompt(
        "4 bed villa around 7m in Azalea",
        selected_purpose="sale",
        selected_intent="best_value",
        listing_scope="custom",
        listing_communities=["Azalea", "Lila"],
        market_scope="custom",
        market_communities=["Azalea", "Lila"],
        limit=10,
    )

    urls = [item["url"] for item in result["matches"]]

    assert urls == ["https://example.com/azalea", "https://example.com/lila"]
    assert "https://example.com/casa" not in urls


def test_budget_reality_mode_uses_above_budget_villas_as_primary_and_townhouses_as_fallback():
    master_df = pd.DataFrame([
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/budget-townhouse",
            "title": "Rent in Camelia: 3BR budget townhouse",
            "annual_rent": 170000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "property_size_sqft": 1507,
            "plot_size_sqft": 1507,
            "description": "Townhouse in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/basic-near-budget-townhouse",
            "title": "Rent in Camelia: 3BR townhouse",
            "annual_rent": 195000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "property_size_sqft": 1507,
            "plot_size_sqft": 1507,
            "description": "Townhouse in Arabian Ranches 2.",
        },
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/premium-townhouse",
            "title": "Rent in Camelia: 3BR premium townhouse",
            "annual_rent": 220000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "property_size_sqft": 1980,
            "plot_size_sqft": 1980,
            "description": "Townhouse in Arabian Ranches 2. Single row, upgraded, large plot.",
        },
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/villa",
            "title": "Rent in Casa: 3BR villa",
            "annual_rent": 250000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])
    enquiry = {
        "purpose": "rent",
        "budget": 210000,
        "stretch_budget": 210000,
        "budget_floor": 168000,
        "bedrooms": 3,
        "bedrooms_options": [3],
        "community": "Arabian Ranches 2",
        "must_haves": [],
        "preferred_category": "villa",
        "strict_category": True,
        "budget_reality_mode": True,
    }

    reality_df = build_budget_reality_primary_dataframe(enquiry, master_df, limit=5)
    fallback_df = build_budget_fallback_dataframe(enquiry, master_df, limit=5)

    assert reality_df["url"].tolist() == ["https://example.com/villa"]
    assert fallback_df["url"].tolist() == [
        "https://example.com/premium-townhouse",
        "https://example.com/basic-near-budget-townhouse",
        "https://example.com/budget-townhouse",
    ]


def test_add_similar_listing_warnings_keeps_items_separate():
    items = [
        {
            "url": "https://example.com/a",
            "title": "Sale in Casa: Single Row | Vacant Soon | Large Layout",
            "price": 5900000,
            "bedrooms": 3,
            "bathrooms": 3,
            "property_size_sqft": 3135,
            "predicted_community": "Casa",
            "predicted_type": "Likely Type 1",
            "match_score": 65,
            "ai_score": 85,
        },
        {
            "url": "https://example.com/b",
            "title": "Sale in Casa: Type 2 | Single row location | Vacant Soon",
            "price": 5900000,
            "bedrooms": 3,
            "bathrooms": 4,
            "property_size_sqft": 3143,
            "predicted_community": "Casa",
            "predicted_type": "Type 2",
            "match_score": 65,
            "ai_score": 70,
        },
    ]

    warned = add_similar_listing_warnings(items)

    assert len(warned) == 2
    assert warned[0]["similar_count"] == 2
    assert warned[0]["url"] == "https://example.com/a"
    assert "https://example.com/b" in warned[0]["similar_urls"]


def test_rows_payload_flags_exclusive_listings_without_leaking_description():
    df = pd.DataFrame([
        {
            "title": "Rent in Samara: Single Row | Exclusive | Vacant",
            "description_json": "Full description text that should not be sent to the browser payload",
            "annual_rent": 255000,
            "bedrooms": 3,
            "url": "https://example.com/exclusive",
            "match_score": 66,
        }
    ])

    payload = rows_payload(df, "annual_rent")

    assert payload[0]["has_exclusive_warning"] is True
    assert payload[0]["price"] == 255000
    assert "description_json" not in payload[0]


def test_ai_fallback_prompt_ranks_only_fallback_options(monkeypatch):
    master_df = pd.DataFrame([
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/fallback",
            "title": "Rent in Camelia: Premium townhouse",
            "annual_rent": 210000,
            "bedrooms": 3,
            "predicted_community": "Camelia",
            "property_size_sqft": 2355,
            "plot_size_sqft": 2355,
            "description": "Townhouse in Arabian Ranches 2. Single row, corner plot.",
        },
        {
            "listing_purpose": "rent",
            "is_active": True,
            "url": "https://example.com/villa",
            "title": "Rent in Casa: Villa",
            "annual_rent": 250000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        },
    ])

    monkeypatch.setattr("webapp_backend.read_master", lambda purpose: (master_df, "memory.csv"))

    def fake_ranker(matches_df, enquiry, **kwargs):
        assert matches_df["url"].tolist() == ["https://example.com/fallback"]
        assert enquiry["preferred_category"] == "townhouse"
        assert "Analyse only the fallback townhouse options" in enquiry["analysis_focus"]
        return {
            "market_read": "Fallback market read.",
            "client_response": "Fallback conclusion.",
            "ranked_matches": [
                {
                    "url": "https://example.com/fallback",
                    "ai_rank": 1,
                    "ai_score": 90,
                    "fit_summary": "Strong premium fallback.",
                    "opportunity_angle": "Premium compromise.",
                    "strengths": ["single row"],
                    "concerns": ["not a villa"],
                    "verify": ["confirm corner"],
                }
            ],
        }

    monkeypatch.setattr("webapp_backend.rank_matches_with_ai", fake_ranker)

    result = ai_fallback_prompt(
        "3 bed villa in Arabian Ranches 2 max 200k. Client does not want a townhouse. Build a budget reality case.",
        api_key="test-key",
    )

    assert result["report_title"] == "Analysed Fallback Options"
    assert result["matches"][0]["url"] == "https://example.com/fallback"
    assert result["ai"]["client_response"] == "Fallback conclusion."


def test_ai_scenario_prompt_applies_scenario_focus(monkeypatch):
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/value",
            "title": "Sale in Casa: Good value",
            "price": 5500000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "description": "Villa in Arabian Ranches 2.",
        }
    ])

    monkeypatch.setattr("webapp_backend.read_master", lambda purpose: (master_df, "memory.csv"))

    def fake_ranker(matches_df, enquiry, **kwargs):
        assert enquiry["analysis_focus"].startswith("Rank the best value options")
        return {
            "market_read": "Value market read.",
            "client_response": "Value conclusion.",
            "ranked_matches": [
                {
                    "url": "https://example.com/value",
                    "ai_rank": 1,
                    "ai_score": 88,
                    "fit_summary": "Strong value.",
                    "opportunity_angle": "Value opportunity.",
                    "strengths": ["priced well"],
                    "concerns": ["verify"],
                    "verify": ["confirm"],
                }
            ],
        }

    monkeypatch.setattr("webapp_backend.rank_matches_with_ai", fake_ranker)

    result = ai_scenario_prompt(
        "3 bed villa in ar2 5.5m best value",
        "best_value",
        selected_purpose="sale",
        api_key="test-key",
    )

    assert result["report_title"] == "Best Value Report"
    assert result["matches"][0]["url"] == "https://example.com/value"


def test_ai_scenario_prompt_supports_upgrade_and_move_in_ready(monkeypatch):
    master_df = pd.DataFrame([
        {
            "listing_purpose": "sale",
            "is_active": True,
            "url": "https://example.com/upgrade",
            "title": "Sale in Casa: Large Plot | Upgrade Potential",
            "price": 5500000,
            "bedrooms": 3,
            "predicted_community": "Casa",
            "predicted_type": "Type 1",
            "detected_type_from_description": "",
            "property_size_sqft": 3250,
            "plot_size_sqft": 5000,
            "description": "Large plot and renovation opportunity in Arabian Ranches 2 villa.",
        }
    ])

    monkeypatch.setattr("webapp_backend.read_master", lambda purpose: (master_df, "memory.csv"))
    seen_focus = []

    def fake_ranker(matches_df, enquiry, **kwargs):
        seen_focus.append(enquiry["analysis_focus"])
        return {
            "market_read": "Scenario market read.",
            "client_response": "Scenario conclusion.",
            "ranked_matches": [
                {
                    "url": "https://example.com/upgrade",
                    "ai_rank": 1,
                    "ai_score": 88,
                    "fit_summary": "Scenario fit.",
                    "opportunity_angle": "Scenario angle.",
                    "strengths": ["data clue"],
                    "concerns": ["verify"],
                    "verify": ["confirm"],
                }
            ],
        }

    monkeypatch.setattr("webapp_backend.rank_matches_with_ai", fake_ranker)

    upgrade_result = ai_scenario_prompt(
        "3 bed villa in ar2 5.5m upgrade potential",
        "upgrade_potential",
        selected_purpose="sale",
        api_key="test-key",
    )
    ready_result = ai_scenario_prompt(
        "3 bed villa in ar2 5.5m move in ready",
        "move_in_ready",
        selected_purpose="sale",
        api_key="test-key",
    )

    assert upgrade_result["report_title"] == "Upgrade Potential Report"
    assert ready_result["report_title"] == "Move-in Ready Report"
    assert any("Only compare BUA" in focus for focus in seen_focus)
    assert any("otherwise use predicted_type" in focus for focus in seen_focus)
    assert any("Do not compare a Casa Type 1 directly with a Casa Type 2" in focus for focus in seen_focus)
    assert any("lowest-hassle" in focus for focus in seen_focus)
