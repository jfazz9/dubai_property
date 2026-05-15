import pandas as pd
import pytest

from scripts.ai_enquiry_ranker import (
    build_ai_payload,
    combine_batch_results,
    merge_ai_rankings,
    rank_matches_with_ai,
)


def test_build_ai_payload_includes_description_and_enquiry():
    matches_df = pd.DataFrame([
        {
            "url": "https://example.com/listing",
            "title": "5 bed with garden",
            "description": "Outdoor BBQ seating area and landscaped garden.",
            "description_json": '{"text": "Vacant in June with BBQ area."}',
            "annual_rent": 330000,
        }
    ])
    enquiry = {
        "purpose": "rent",
        "budget": 340000,
        "bedrooms": 5,
        "community": "Arabian Ranches 2",
        "must_haves": ["bbq sitting outer area"],
    }

    payload = build_ai_payload(
        matches_df,
        enquiry,
        market_context={"recent_transaction_stats": {"price": {"median": 330000}}},
    )

    assert payload["enquiry"]["budget"] == 340000
    assert payload["market_context"]["recent_transaction_stats"]["price"]["median"] == 330000
    assert payload["candidate_rows"][0]["description"] == "Outdoor BBQ seating area and landscaped garden."
    assert "Vacant in June" in payload["candidate_rows"][0]["description_json"]
    assert any("Do not use first-person action language" in instruction for instruction in payload["instructions"])


def test_merge_ai_rankings_adds_ai_columns():
    matches_df = pd.DataFrame([
        {
            "url": "https://example.com/a",
            "match_score": 70,
        }
    ])
    ai_result = {
        "ranked_matches": [
            {
                "url": "https://example.com/a",
                "ai_rank": 1,
                "ai_score": 92,
                "fit_summary": "Strong outdoor fit.",
                "opportunity_angle": "Good client fit and possible owner lead angle.",
                "strengths": ["BBQ clue", "within budget"],
                "concerns": ["Confirm outdoor seating"],
                "verify": ["Confirm outdoor seating"],
            }
        ]
    }

    enriched_df = merge_ai_rankings(matches_df, ai_result)
    row = enriched_df.iloc[0]

    assert row["ai_rank"] == 1
    assert row["ai_score"] == 92
    assert row["ai_fit_summary"] == "Strong outdoor fit."
    assert row["ai_opportunity_angle"] == "Good client fit and possible owner lead angle."
    assert "BBQ clue" in row["ai_strengths"]
    assert "Confirm outdoor seating" in row["ai_verify"]


def test_combine_batch_results_keeps_ranked_matches():
    result = combine_batch_results([
        {
            "market_read": "First batch read.",
            "client_response": "First batch response.",
            "ranked_matches": [{"url": "https://example.com/a"}],
        },
        {
            "market_read": "Second batch read.",
            "client_response": "Second batch response.",
            "ranked_matches": [{"url": "https://example.com/b"}],
        },
    ])

    assert len(result["ranked_matches"]) == 2
    assert "Batch 1" in result["market_read"]
    assert "First batch response" in result["client_response"]


def test_rank_matches_with_ai_batches_then_finalizes(monkeypatch):
    calls = []

    class FakeClient:
        pass

    def fake_client_for_api_key(api_key):
        return FakeClient()

    def fake_call_openai_ranker(client, payload, model):
        calls.append(payload)
        ranked_matches = [
            {
                "url": row["url"],
                "ai_rank": index,
                "ai_score": 100 - index,
                "fit_summary": "fit",
                "opportunity_angle": "opportunity",
                "strengths": [],
                "concerns": [],
                "verify": [],
            }
            for index, row in enumerate(payload["candidate_rows"], start=1)
        ]
        return {
            "market_read": "read",
            "client_response": "response",
            "ranked_matches": ranked_matches,
        }

    monkeypatch.setattr("scripts.ai_enquiry_ranker.client_for_api_key", fake_client_for_api_key)
    monkeypatch.setattr("scripts.ai_enquiry_ranker.call_openai_ranker", fake_call_openai_ranker)
    matches_df = pd.DataFrame([
        {"url": f"https://example.com/{index}", "match_score": index}
        for index in range(12)
    ])

    result = rank_matches_with_ai(
        matches_df,
        {"purpose": "sale"},
        api_key="test",
        batch_size=5,
        final_candidate_limit=4,
    )

    assert len(calls) == 4
    assert [len(call["candidate_rows"]) for call in calls] == [5, 5, 2, 4]
    assert calls[-1]["market_context"]["batching"]["batch_count"] == 3
    assert len(result["ranked_matches"]) == 4


def test_rank_matches_with_ai_returns_batch_fallback_when_final_times_out(monkeypatch):
    calls = []

    class FakeClient:
        pass

    def fake_client_for_api_key(api_key):
        return FakeClient()

    def fake_call_openai_ranker(client, payload, model):
        calls.append(payload)

        if len(calls) == 3:
            raise TimeoutError("request timed out")

        ranked_matches = [
            {
                "url": row["url"],
                "ai_rank": index,
                "ai_score": 100 - index,
                "fit_summary": "fit",
                "opportunity_angle": "opportunity",
                "strengths": [],
                "concerns": [],
                "verify": [],
            }
            for index, row in enumerate(payload["candidate_rows"], start=1)
        ]
        return {
            "market_read": "batch read",
            "client_response": "batch response",
            "ranked_matches": ranked_matches,
        }

    monkeypatch.setattr("scripts.ai_enquiry_ranker.client_for_api_key", fake_client_for_api_key)
    monkeypatch.setattr("scripts.ai_enquiry_ranker.call_openai_ranker", fake_call_openai_ranker)
    matches_df = pd.DataFrame([
        {"url": f"https://example.com/{index}", "match_score": index}
        for index in range(8)
    ])

    result = rank_matches_with_ai(
        matches_df,
        {"purpose": "sale"},
        api_key="test",
        batch_size=5,
        final_candidate_limit=4,
    )

    assert len(calls) == 3
    assert "final report step timed out" in result["client_response"].lower()
    assert len(result["ranked_matches"]) == 8


def test_rank_matches_with_ai_uses_local_fallback_when_ranking_batch_times_out(monkeypatch):
    calls = []

    class FakeClient:
        pass

    def fake_client_for_api_key(api_key):
        return FakeClient()

    def fake_call_openai_ranker(client, payload, model):
        calls.append(payload)

        if len(calls) == 2:
            raise TimeoutError("request timed out")

        ranked_matches = [
            {
                "url": row["url"],
                "ai_rank": index,
                "ai_score": 100 - index,
                "fit_summary": "fit",
                "opportunity_angle": "opportunity",
                "strengths": [],
                "concerns": [],
                "verify": [],
            }
            for index, row in enumerate(payload["candidate_rows"], start=1)
        ]
        return {
            "market_read": "batch read",
            "client_response": "batch response",
            "ranked_matches": ranked_matches,
        }

    monkeypatch.setattr("scripts.ai_enquiry_ranker.client_for_api_key", fake_client_for_api_key)
    monkeypatch.setattr("scripts.ai_enquiry_ranker.call_openai_ranker", fake_call_openai_ranker)
    matches_df = pd.DataFrame([
        {"url": f"https://example.com/{index}", "match_score": 80 - index, "title": f"Listing {index}"}
        for index in range(9)
    ])

    result = rank_matches_with_ai(
        matches_df,
        {"purpose": "sale"},
        api_key="test",
        batch_size=4,
        skip_final_report=True,
    )

    assert len(calls) == 3
    assert "timed out" in result["client_response"].lower()
    assert len(result["ranked_matches"]) == 9
    assert any(item["url"] == "https://example.com/4" for item in result["ranked_matches"])


def test_rank_matches_with_ai_uses_local_fallback_when_single_request_times_out(monkeypatch):
    class FakeClient:
        pass

    def fake_client_for_api_key(api_key):
        return FakeClient()

    def fake_call_openai_ranker(client, payload, model):
        raise TimeoutError("request timed out")

    monkeypatch.setattr("scripts.ai_enquiry_ranker.client_for_api_key", fake_client_for_api_key)
    monkeypatch.setattr("scripts.ai_enquiry_ranker.call_openai_ranker", fake_call_openai_ranker)
    matches_df = pd.DataFrame([
        {"url": "https://example.com/a", "match_score": 88, "title": "Ready to move"}
    ])

    result = rank_matches_with_ai(
        matches_df,
        {"purpose": "sale"},
        api_key="test",
        batch_size=4,
        skip_final_report=True,
    )

    assert "timed out" in result["client_response"].lower()
    assert result["ranked_matches"][0]["url"] == "https://example.com/a"
    assert result["ranked_matches"][0]["ai_score"] == 88
