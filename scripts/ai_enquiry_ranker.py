import json
import os

import pandas as pd


DEFAULT_BATCH_SIZE = 4
DEFAULT_FINAL_CANDIDATE_LIMIT = 10


AI_RANKING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "market_read": {"type": "string"},
        "client_response": {"type": "string"},
        "ranked_matches": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "ai_rank": {"type": "integer"},
                    "ai_score": {"type": "integer"},
                    "fit_summary": {"type": "string"},
                    "opportunity_angle": {"type": "string"},
                    "strengths": {"type": "array", "items": {"type": "string"}},
                    "concerns": {"type": "array", "items": {"type": "string"}},
                    "verify": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "url",
                    "ai_rank",
                    "ai_score",
                    "fit_summary",
                    "opportunity_angle",
                    "strengths",
                    "concerns",
                    "verify",
                ],
            },
        },
    },
    "required": ["market_read", "client_response", "ranked_matches"],
}


def clean_ai_value(value):
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "item"):
        value = value.item()

    return value


def row_to_ai_payload(row, description_chars=12000):
    payload = {}

    for key, value in row.items():
        cleaned_value = clean_ai_value(value)

        if cleaned_value is None:
            continue

        if key in {"description", "description_json"}:
            payload[key] = str(cleaned_value)[:description_chars]
        else:
            payload[key] = cleaned_value

    return payload


def build_ai_payload(matches_df, enquiry, description_chars=12000, market_context=None):
    return {
        "enquiry": enquiry,
        "market_context": market_context or {},
        "instructions": [
            "Rank listings for the user's property consultancy workflow using the structured row data and full listing descriptions.",
            "The user has scraped these listings already. They are using this to answer client enquiries and to identify listing/poach opportunities.",
            "Use market_context when supplied to compare asking prices against recent DXB transaction evidence and active shortlist medians.",
            "If enquiry.analysis_focus is supplied, make that the main task and structure the response around it.",
            "If enquiry.budget_reality_mode is true, preserve the requested property category as the primary analysis even when it is above budget. Treat cheaper wrong-category stock as fallback alternatives only.",
            "Treat description_json as the richest listing evidence. Use it with title and the rest of the row to judge suitability.",
            "Prioritize hard facts first: budget, bedrooms, location/community, active status, and listing purpose.",
            "Respect villa/townhouse fit. If the client asks for a villa community such as Casa, do not rank townhouse stock highly unless clearly asked for alternatives.",
            "Use availability clues such as vacant, vacant soon, vacant on transfer, ready to move, or month names when the enquiry includes a move date.",
            "For value, compare the asking price against the candidate set and flag when something is cheap because it is the wrong community/type.",
            "Use description language to judge softer requirements like BBQ area, outdoor seating, garden, pet suitability, upgrades, and family suitability.",
            "For each listing, explain both client fit and opportunity angle: value opportunity, listing/poach opportunity, owner-lead opportunity, or weak opportunity.",
            "Do not tell the user to arrange viewings or behave like the listing agent. Use verify items such as confirm vacancy, corner status, owner motivation, tenancy, price movement, and owner lead availability.",
            "Do not use first-person action language such as 'I will', 'I'll', 'do you want me to', or 'let me'.",
            "Use neutral consultant-report wording: 'Recommended next checks', 'Suggested verification', 'Opportunity angle', and 'Potential approach'.",
            "Do not invent facts. If a feature is only implied, say it is a clue and recommend confirming with the agent.",
            "Return a practical consultant response that can be adapted for WhatsApp or used internally as an enquiry report.",
        ],
        "candidate_rows": [
            row_to_ai_payload(row, description_chars=description_chars)
            for _, row in matches_df.iterrows()
        ],
    }


def call_openai_ranker(client, payload, model):
    response = client.responses.create(
        model=model,
        instructions=(
            "You are a senior Dubai property consultant assistant. "
            "Use the supplied listing rows only. Return structured JSON only."
        ),
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "property_enquiry_ranking",
                "strict": True,
                "schema": AI_RANKING_SCHEMA,
            }
        },
    )

    return json.loads(response.output_text)


def empty_ai_result():
    return {
        "market_read": "No candidate rows were supplied.",
        "client_response": "I could not find matching active listings in the current data.",
        "ranked_matches": [],
    }


def is_timeout_error(exc):
    message = str(exc).lower()
    class_name = exc.__class__.__name__.lower()
    return "timeout" in message or "timed out" in message or "timeout" in class_name


def local_ranking_result(matches_df, reason="OpenAI ranking timed out."):
    ranked_matches = []

    for index, (_, row) in enumerate(matches_df.iterrows(), start=1):
        url = row.get("url")

        if not url:
            continue

        score = clean_ai_value(row.get("match_score"))

        try:
            ai_score = int(score)
        except (TypeError, ValueError):
            ai_score = max(100 - index, 1)

        title = clean_ai_value(row.get("title")) or "Listing"
        price = clean_ai_value(row.get("price")) or clean_ai_value(row.get("annual_rent"))
        community = clean_ai_value(row.get("predicted_community")) or clean_ai_value(row.get("community")) or "the target area"
        bedrooms = clean_ai_value(row.get("bedrooms"))

        summary_bits = []

        if bedrooms:
            summary_bits.append(f"{bedrooms} bed")

        if community:
            summary_bits.append(str(community))

        if price:
            summary_bits.append(f"priced at {price}")

        fit_summary = f"{title}. " + " / ".join(summary_bits)

        ranked_matches.append({
            "url": url,
            "ai_rank": index,
            "ai_score": max(min(ai_score, 100), 1),
            "fit_summary": fit_summary.strip(),
            "opportunity_angle": "Local fallback ranking from the rule-based shortlist. Use as a practical shortlist, then retry AI for deeper commentary if needed.",
            "strengths": ["Matched by the local scoring rules", "Retains the current shortlist order"],
            "concerns": ["OpenAI did not complete this ranking batch"],
            "verify": ["Open the listing and confirm availability, condition, price, and owner/agent details"],
        })

    return {
        "market_read": f"{reason} The app kept the shortlist alive using the local ranking so the workflow does not stop.",
        "client_response": (
            "OpenAI timed out while ranking this batch, so the app returned the locally ranked shortlist instead. "
            "The cards are still usable for triage; Build report or the same scenario can be retried with fewer results."
        ),
        "ranked_matches": ranked_matches,
    }


def client_for_api_key(api_key):
    api_key = api_key or os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Set it before using --ai.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is not installed. Run: pip install -r requirements.txt") from exc

    return OpenAI(api_key=api_key, timeout=120.0, max_retries=0)


def build_batch_market_context(market_context, batch_number, batch_count):
    if not market_context:
        return {}

    return {
        "batch": {
            "number": batch_number,
            "count": batch_count,
            "note": "This is one batch of a larger shortlist. Rank only this batch locally.",
        },
        "dxb_report_summary": market_context.get("dxb_report_summary", {}),
        "recent_transaction_stats": market_context.get("recent_transaction_stats", {}),
        "active_shortlist": market_context.get("active_shortlist", {}),
    }


def combine_batch_results(batch_results):
    ranked_matches = []
    market_reads = []
    client_responses = []

    for batch_number, result in enumerate(batch_results, start=1):
        market_read = result.get("market_read")
        client_response = result.get("client_response")

        if market_read:
            market_reads.append(f"Batch {batch_number}: {market_read}")

        if client_response:
            client_responses.append(f"Batch {batch_number}: {client_response}")

        ranked_matches.extend(result.get("ranked_matches", []))

    return {
        "market_read": "\n".join(market_reads),
        "client_response": "\n\n".join(client_responses) or "Batch ranking completed. Final ranking pending.",
        "ranked_matches": ranked_matches,
    }


def rank_matches_with_ai(
    matches_df,
    enquiry,
    model="gpt-5-mini",
    description_chars=12000,
    api_key=None,
    market_context=None,
    batch_size=DEFAULT_BATCH_SIZE,
    final_candidate_limit=DEFAULT_FINAL_CANDIDATE_LIMIT,
    skip_final_report=False,
):
    if matches_df.empty:
        return empty_ai_result()

    client = client_for_api_key(api_key)

    if len(matches_df) <= batch_size:
        payload = build_ai_payload(
            matches_df,
            enquiry,
            description_chars=description_chars,
            market_context=market_context,
        )

        try:
            return call_openai_ranker(client, payload, model)
        except Exception as exc:
            if not is_timeout_error(exc):
                raise

            return local_ranking_result(matches_df, "OpenAI timed out while ranking the shortlist.")

    batch_results = []
    timed_out_batches = []
    batch_count = (len(matches_df) + batch_size - 1) // batch_size

    for batch_index, start in enumerate(range(0, len(matches_df), batch_size), start=1):
        batch_df = matches_df.iloc[start:start + batch_size]
        payload = build_ai_payload(
            batch_df,
            enquiry,
            description_chars=description_chars,
            market_context=build_batch_market_context(market_context, batch_index, batch_count),
        )

        try:
            batch_results.append(call_openai_ranker(client, payload, model))
        except Exception as exc:
            if not is_timeout_error(exc):
                raise

            timed_out_batches.append(batch_index)
            batch_results.append(local_ranking_result(
                batch_df,
                f"OpenAI timed out while ranking batch {batch_index} of {batch_count}.",
            ))

    combined_result = combine_batch_results(batch_results)

    if skip_final_report:
        combined_result["client_response"] = (
            "OpenAI ranked the shortlist in batches. Use Build report for the deeper market-backed write-up."
        )

        if timed_out_batches:
            combined_result["client_response"] = (
                "One or more OpenAI ranking batches timed out, so those cards used the local rule-based ranking. "
                "The shortlist is still usable; retry the scenario or Build report with fewer results for deeper AI commentary."
            )

        combined_result["market_read"] = (
            f"{combined_result.get('market_read', '')}\n\n"
            "Ranking-only mode: final report step was skipped to reduce timeout risk."
        ).strip()
        return combined_result

    finalists_df = merge_ai_rankings(matches_df, combined_result)

    if "ai_score" in finalists_df.columns:
        finalists_df = finalists_df.sort_values(
            ["ai_score", "match_score"],
            ascending=[False, False],
            na_position="last",
        )

    finalists_df = finalists_df.head(final_candidate_limit)
    final_market_context = dict(market_context or {})
    final_market_context["batching"] = {
        "batch_size": batch_size,
        "batch_count": batch_count,
        "final_candidate_count": int(len(finalists_df)),
        "note": "Initial candidates were ranked in batches. This final request compares the batch winners and produces the final report.",
    }
    payload = build_ai_payload(
        finalists_df,
        enquiry,
        description_chars=description_chars,
        market_context=final_market_context,
    )

    try:
        return call_openai_ranker(client, payload, model)
    except Exception as exc:
        if not is_timeout_error(exc):
            raise

        fallback = combine_batch_results(batch_results)
        fallback["market_read"] = (
            f"{fallback.get('market_read', '')}\n\n"
            "Final report call timed out, so these results are the merged batch rankings."
        ).strip()
        fallback["client_response"] = (
            "OpenAI ranked the listings in batches, but the final report step timed out. "
            "Use the ranked cards below as the shortlist, then try AI feedback again with a narrower prompt if needed."
        )
        return fallback


def merge_ai_rankings(matches_df, ai_result):
    ranked_by_url = {
        item["url"]: item
        for item in ai_result.get("ranked_matches", [])
        if item.get("url")
    }

    enriched_rows = []

    for _, row in matches_df.iterrows():
        row_data = row.to_dict()
        ai_row = ranked_by_url.get(row_data.get("url"), {})
        row_data["ai_rank"] = ai_row.get("ai_rank")
        row_data["ai_score"] = ai_row.get("ai_score")
        row_data["ai_fit_summary"] = ai_row.get("fit_summary")
        row_data["ai_opportunity_angle"] = ai_row.get("opportunity_angle")
        row_data["ai_strengths"] = "; ".join(ai_row.get("strengths", []))
        row_data["ai_concerns"] = "; ".join(ai_row.get("concerns", []))
        row_data["ai_verify"] = "; ".join(ai_row.get("verify", []))
        enriched_rows.append(row_data)

    enriched_df = pd.DataFrame(enriched_rows)

    if "ai_rank" in enriched_df.columns:
        enriched_df = enriched_df.sort_values(["ai_rank", "match_score"], ascending=[True, False], na_position="last")

    return enriched_df
