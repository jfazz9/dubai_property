import json
import sys

from ai_enquiry_ranker import client_for_api_key
from ai_enquiry_ranker import merge_ai_rankings
from ai_enquiry_ranker import row_to_ai_payload
from ai_enquiry_ranker import rank_matches_with_ai as _rank_matches_with_ai

from .constants import (
    AI_DESCRIPTION_CHARS,
    DEFAULT_AI_BATCH_SIZE,
    DEFAULT_AI_FINAL_CANDIDATE_LIMIT,
    DEFAULT_AI_RESULT_LIMIT,
    DEFAULT_AI_SHORTLIST_LIMIT,
    OVER_BUDGET_LIMIT,
    SCENARIOS,
)
from .market_context import build_market_context
from .matcher import (
    build_budget_fallback_dataframe,
    build_budget_reality_primary_dataframe,
    build_matches_dataframe,
    build_over_budget_dataframe,
)
from .prompt_parser import parse_prompt
from .result_builder import result_payload


CLIENT_REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "transaction_section": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "heading": {"type": "string"},
                "transactions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "date": {"type": "string"},
                            "price": {"type": "string"},
                            "size": {"type": "string"},
                            "ppsf": {"type": "string"}
                        },
                        "required": ["date", "price", "size", "ppsf"]
                    }
                },
                "range": {"type": "string"},
                "average_price": {"type": "string"},
                "average_ppsf": {"type": "string"},
                "layout_note": {"type": "string"},
                "narrative": {"type": "string"}
            },
            "required": ["heading", "transactions", "range", "average_price", "average_ppsf", "layout_note", "narrative"]
        },
        "inventory_section": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "heading": {"type": "string"},
                "listings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "price": {"type": "string"},
                            "description_tag": {"type": "string"},
                            "stats_line": {"type": "string"},
                            "narrative": {"type": "string"}
                        },
                        "required": ["label", "price", "description_tag", "stats_line", "narrative"]
                    }
                },
                "summary_paragraph": {"type": "string"}
            },
            "required": ["heading", "listings", "summary_paragraph"]
        },
        "alternative_section": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "heading": {"type": "string"},
                "intro_paragraph": {"type": "string"},
                "listings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "price": {"type": "string"},
                            "description_tag": {"type": "string"},
                            "stats_line": {"type": "string"},
                            "narrative": {"type": "string"}
                        },
                        "required": ["label", "price", "description_tag", "stats_line", "narrative"]
                    }
                },
                "summary_paragraph": {"type": "string"}
            },
            "required": ["heading", "intro_paragraph", "listings", "summary_paragraph"]
        },
        "comparison_section": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "heading": {"type": "string"},
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "price": {"type": "string"},
                            "size": {"type": "string"},
                            "ppsf": {"type": "string"},
                            "beds_baths": {"type": "string"},
                            "availability": {"type": "string"}
                        },
                        "required": ["label", "price", "size", "ppsf", "beds_baths", "availability"]
                    }
                }
            },
            "required": ["heading", "rows"]
        },
        "strategic_assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "market_context": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "heading": {"type": "string"},
                            "body": {"type": "string"}
                        },
                        "required": ["heading", "body"]
                    }
                },
                "approach_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "number": {"type": "string"},
                            "action": {"type": "string"},
                            "detail": {"type": "string"}
                        },
                        "required": ["number", "action", "detail"]
                    }
                }
            },
            "required": ["market_context", "sections", "approach_items"]
        },
        "footer": {"type": "string"},
        "disclaimer": {"type": "string"}
    },
    "required": [
        "title", "subtitle",
        "transaction_section", "inventory_section", "alternative_section",
        "comparison_section", "strategic_assessment",
        "footer", "disclaimer"
    ]
}


def _read_master(purpose):
    """Look up read_master through the package namespace so monkeypatching works."""
    pkg = sys.modules.get("webapp_backend") or sys.modules.get("scripts.webapp_backend")
    if pkg is not None and hasattr(pkg, "read_master"):
        return pkg.read_master(purpose)
    from .data_loader import read_master
    return read_master(purpose)


def _rank_matches_with_ai_dispatch(matches_df, enquiry, **kwargs):
    """Look up rank_matches_with_ai through the package namespace so monkeypatching works."""
    pkg = sys.modules.get("webapp_backend") or sys.modules.get("scripts.webapp_backend")
    if pkg is not None and hasattr(pkg, "rank_matches_with_ai"):
        return pkg.rank_matches_with_ai(matches_df, enquiry, **kwargs)
    return _rank_matches_with_ai(matches_df, enquiry, **kwargs)


def ai_fallback_prompt(
    text,
    selected_purpose="auto",
    api_key=None,
    limit=DEFAULT_AI_RESULT_LIMIT,
    skip_final_report=False,
    ranked_urls=None,
    listing_scope="auto",
    listing_communities=None,
    market_scope="auto",
    market_communities=None,
):
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    enquiry = parse_prompt(text, selected_purpose, "auto", market_scope, market_communities, listing_scope, listing_communities)
    master_df, path = _read_master(enquiry["purpose"])
    fallback_df = build_budget_fallback_dataframe(enquiry, master_df, limit=max(limit, DEFAULT_AI_SHORTLIST_LIMIT))

    if fallback_df.empty:
        raise RuntimeError("No fallback options were found for this brief. Run a budget-reality villa enquiry with townhouse fallback first.")

    if ranked_urls:
        order = {url: index for index, url in enumerate(ranked_urls)}
        fallback_df = fallback_df[fallback_df["url"].isin(order)].copy()

        if fallback_df.empty:
            raise RuntimeError("The previous fallback shortlist is no longer available. Run Analyse fallback again.")

        fallback_df["_ranked_order"] = fallback_df["url"].map(order)
        fallback_df = fallback_df.sort_values("_ranked_order").drop(columns=["_ranked_order"])

    fallback_enquiry = dict(enquiry)
    fallback_enquiry["preferred_category"] = "townhouse"
    fallback_enquiry["strict_category"] = True
    fallback_enquiry["analysis_focus"] = (
        "Analyse only the fallback townhouse options. Rank the strongest premium compromise first, "
        "then separate stronger premium choices from cheaper budget-saving alternatives. Compare upgrade clues, "
        "single-row/corner/end-unit position, large plot/garden, vacancy, family usability, and value against recent rental transactions. "
        "Explain whether each fallback is a real compromise for a villa client or merely a cheaper townhouse."
    )

    ai_result = _rank_matches_with_ai_dispatch(
        fallback_df,
        fallback_enquiry,
        model="gpt-5-mini",
        description_chars=AI_DESCRIPTION_CHARS,
        api_key=api_key,
        market_context=build_market_context(enquiry, fallback_df),
        batch_size=DEFAULT_AI_BATCH_SIZE,
        final_candidate_limit=DEFAULT_AI_FINAL_CANDIDATE_LIMIT,
        skip_final_report=skip_final_report,
    )
    enriched_df = merge_ai_rankings(fallback_df, ai_result).head(limit)
    result = result_payload(
        fallback_enquiry,
        enriched_df,
        master_df,
        path,
        ai_result=ai_result,
    )
    result["report_title"] = "Analysed Fallback Options"

    if skip_final_report:
        result["report_title"] = "Analysed Fallback Options Ranking"
        result["rank_context"] = {
            "scenario": "fallback",
            "ranked_urls": [
                url
                for url in enriched_df["url"].head(limit).tolist()
                if url
            ],
        }

    return result


def ai_scenario_prompt(text, scenario, selected_purpose="auto", api_key=None, limit=DEFAULT_AI_RESULT_LIMIT, listing_scope="auto", listing_communities=None, market_scope="auto", market_communities=None):
    return ai_scenario_result(
        text,
        scenario,
        selected_purpose=selected_purpose,
        api_key=api_key,
        limit=limit,
        listing_scope=listing_scope,
        listing_communities=listing_communities,
        market_scope=market_scope,
        market_communities=market_communities,
        skip_final_report=False,
    )


def ai_scenario_rank_prompt(text, scenario, selected_purpose="auto", api_key=None, limit=DEFAULT_AI_RESULT_LIMIT, listing_scope="auto", listing_communities=None, market_scope="auto", market_communities=None):
    return ai_scenario_result(
        text,
        scenario,
        selected_purpose=selected_purpose,
        api_key=api_key,
        limit=limit,
        listing_scope=listing_scope,
        listing_communities=listing_communities,
        market_scope=market_scope,
        market_communities=market_communities,
        skip_final_report=True,
    )


def ai_scenario_report_prompt(text, scenario, ranked_urls=None, selected_purpose="auto", api_key=None, limit=DEFAULT_AI_RESULT_LIMIT, listing_scope="auto", listing_communities=None, market_scope="auto", market_communities=None):
    return ai_scenario_result(
        text,
        scenario,
        selected_purpose=selected_purpose,
        api_key=api_key,
        limit=min(limit, 6),
        ranked_urls=ranked_urls or [],
        listing_scope=listing_scope,
        listing_communities=listing_communities,
        market_scope=market_scope,
        market_communities=market_communities,
        skip_final_report=False,
    )


def ai_scenario_result(
    text,
    scenario,
    selected_purpose="auto",
    api_key=None,
    limit=DEFAULT_AI_RESULT_LIMIT,
    ranked_urls=None,
    listing_scope="auto",
    listing_communities=None,
    market_scope="auto",
    market_communities=None,
    skip_final_report=False,
):
    if scenario == "fallback":
        if skip_final_report:
            return ai_fallback_prompt(text, selected_purpose=selected_purpose, api_key=api_key, limit=limit, skip_final_report=True, ranked_urls=ranked_urls, listing_scope=listing_scope, listing_communities=listing_communities, market_scope=market_scope, market_communities=market_communities)
        return ai_fallback_prompt(text, selected_purpose=selected_purpose, api_key=api_key, limit=limit, ranked_urls=ranked_urls, listing_scope=listing_scope, listing_communities=listing_communities, market_scope=market_scope, market_communities=market_communities)

    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    scenario_config = SCENARIOS.get(scenario)

    if not scenario_config:
        raise RuntimeError(f"Unknown scenario: {scenario}")

    scenario_intent = scenario if scenario in {"best_value", "negotiation", "listing_opportunity", "upgrade_potential", "move_in_ready"} else "auto"
    enquiry = parse_prompt(text, selected_purpose, scenario_intent, market_scope, market_communities, listing_scope, listing_communities)

    if scenario == "budget_reality":
        enquiry["budget_reality_mode"] = True

    enquiry["analysis_focus"] = scenario_config["focus"]
    shortlist_limit = max(limit, DEFAULT_AI_SHORTLIST_LIMIT)
    matches_df, master_df, path = build_matches_dataframe(dict(enquiry), shortlist_limit)

    if scenario == "budget_reality" or enquiry.get("budget_reality_mode"):
        reality_df = build_budget_reality_primary_dataframe(enquiry, master_df, limit=shortlist_limit)

        if not reality_df.empty:
            matches_df = reality_df

    if matches_df.empty:
        raise RuntimeError("No suitable rows were found for this scenario.")

    if ranked_urls:
        order = {url: index for index, url in enumerate(ranked_urls)}
        matches_df = matches_df[matches_df["url"].isin(order)].copy()

        if matches_df.empty:
            raise RuntimeError("The previous ranked shortlist is no longer available. Run the scenario rank again.")

        matches_df["_ranked_order"] = matches_df["url"].map(order)
        matches_df = matches_df.sort_values("_ranked_order").drop(columns=["_ranked_order"])

    ai_result = _rank_matches_with_ai_dispatch(
        matches_df,
        enquiry,
        model="gpt-5-mini",
        description_chars=AI_DESCRIPTION_CHARS,
        api_key=api_key,
        market_context=build_market_context(enquiry, matches_df),
        batch_size=DEFAULT_AI_BATCH_SIZE,
        final_candidate_limit=DEFAULT_AI_FINAL_CANDIDATE_LIMIT,
        skip_final_report=skip_final_report,
    )
    enriched_df = merge_ai_rankings(matches_df, ai_result).head(limit)
    over_budget_df = build_over_budget_dataframe(enquiry, master_df, enriched_df, limit=OVER_BUDGET_LIMIT)
    fallback_df = build_budget_fallback_dataframe(enquiry, master_df, limit=OVER_BUDGET_LIMIT)
    result = result_payload(
        enquiry,
        enriched_df,
        master_df,
        path,
        ai_result=ai_result,
        over_budget_df=over_budget_df,
        fallback_df=fallback_df,
    )
    result["report_title"] = scenario_config["report_title"]

    if skip_final_report:
        result["report_title"] = f"{scenario_config['report_title']} Ranking"
        result["rank_context"] = {
            "scenario": scenario,
            "ranked_urls": [
                url
                for url in enriched_df["url"].head(limit).tolist()
                if url
            ],
        }
    else:
        # Build Report (full report) — expose the final shortlist so the
        # frontend can gate the Client Report button on this step.
        result["report_context"] = {
            "scenario": scenario,
            "ranked_urls": [
                url
                for url in enriched_df["url"].head(limit).tolist()
                if url
            ],
        }

    return result


def ai_feedback_prompt(text, selected_purpose="auto", selected_intent="auto", listing_scope="auto", listing_communities=None, market_scope="auto", market_communities=None, api_key=None, limit=DEFAULT_AI_RESULT_LIMIT):
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    enquiry = parse_prompt(text, selected_purpose, selected_intent, market_scope, market_communities, listing_scope, listing_communities)
    shortlist_limit = max(limit, DEFAULT_AI_SHORTLIST_LIMIT)
    matches_df, master_df, path = build_matches_dataframe(dict(enquiry), shortlist_limit)
    reality_df = build_budget_reality_primary_dataframe(enquiry, master_df, limit=shortlist_limit)

    if not reality_df.empty:
        matches_df = reality_df

    ai_result = _rank_matches_with_ai_dispatch(
        matches_df,
        enquiry,
        model="gpt-5-mini",
        description_chars=AI_DESCRIPTION_CHARS,
        api_key=api_key,
        market_context=build_market_context(enquiry, matches_df),
        batch_size=DEFAULT_AI_BATCH_SIZE,
        final_candidate_limit=DEFAULT_AI_FINAL_CANDIDATE_LIMIT,
    )
    enriched_df = merge_ai_rankings(matches_df, ai_result).head(limit)

    over_budget_df = build_over_budget_dataframe(enquiry, master_df, enriched_df, limit=OVER_BUDGET_LIMIT)
    fallback_df = build_budget_fallback_dataframe(enquiry, master_df, limit=OVER_BUDGET_LIMIT)

    return result_payload(
        enquiry,
        enriched_df,
        master_df,
        path,
        ai_result=ai_result,
        over_budget_df=over_budget_df,
        fallback_df=fallback_df,
    )


def _client_report_rows(matches_df):
    client_rows = []

    for index, (_, row) in enumerate(matches_df.iterrows(), start=1):
        row_payload = row_to_ai_payload(row, description_chars=5000)
        client_rows.append({
            "candidate_ref": f"option_{index}",
            "community": row_payload.get("predicted_community") or row_payload.get("community"),
            "property_category": row_payload.get("property_category") or row_payload.get("category"),
            "predicted_type": row_payload.get("predicted_type"),
            "bedrooms": row_payload.get("bedrooms"),
            "bathrooms": row_payload.get("bathrooms"),
            "price": row_payload.get("price") or row_payload.get("annual_rent"),
            "property_size_sqft": row_payload.get("property_size_sqft"),
            "plot_size_sqft": row_payload.get("plot_size_sqft"),
            "price_per_sqft": row_payload.get("price_per_sqft"),
            "match_reasons": row_payload.get("match_reasons"),
            "outdoor_matches": row_payload.get("outdoor_matches"),
            "ai_fit_summary": row_payload.get("ai_fit_summary"),
            "ai_strengths": row_payload.get("ai_strengths"),
            "ai_concerns": row_payload.get("ai_concerns"),
            "ai_verify": row_payload.get("ai_verify"),
            "internal_listing_title_do_not_copy": row_payload.get("title"),
            "internal_listing_description_do_not_copy": row_payload.get("description"),
            "internal_description_json_do_not_copy": row_payload.get("description_json"),
        })

    return client_rows


def ai_client_report_prompt(
    text,
    scenario="best_value",
    ranked_urls=None,
    selected_purpose="auto",
    api_key=None,
    limit=6,
    listing_scope="auto",
    listing_communities=None,
    market_scope="auto",
    market_communities=None,
):
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    scenario_config = SCENARIOS.get(scenario) or SCENARIOS.get("best_value")
    scenario_intent = scenario if scenario in {"best_value", "negotiation", "listing_opportunity", "upgrade_potential", "move_in_ready"} else "auto"
    enquiry = parse_prompt(text, selected_purpose, scenario_intent, market_scope, market_communities, listing_scope, listing_communities)
    enquiry["analysis_focus"] = scenario_config["focus"]

    matches_df, master_df, path = build_matches_dataframe(dict(enquiry), max(limit, DEFAULT_AI_SHORTLIST_LIMIT))

    if matches_df.empty:
        raise RuntimeError("No suitable rows were found for this client report.")

    if ranked_urls:
        order = {url: index for index, url in enumerate(ranked_urls)}
        ranked_df = matches_df[matches_df["url"].isin(order)].copy()

        if not ranked_df.empty:
            ranked_df["_ranked_order"] = ranked_df["url"].map(order)
            matches_df = ranked_df.sort_values("_ranked_order").drop(columns=["_ranked_order"])

    matches_df = matches_df.head(max(1, min(int(limit or 6), 8)))
    market_context = build_market_context(enquiry, matches_df)
    payload = {
        "client_brief": enquiry,
        "scenario": scenario,
        "market_context": market_context,
        "style_reference": {
            "structure": [
                "01 — RECENT TRANSACTION DATA: recent sold transactions table with summary stats and a narrative paragraph",
                "02 — CURRENT INVENTORY: listing cards for primary community options, each with label, price, description tag, stats line, and narrative; followed by a community summary paragraph",
                "03 — STRONGEST CURRENT ALTERNATIVE: intro paragraph, then listing cards in the same format for the best alternative community/type, followed by a summary paragraph",
                "04 — INVENTORY COMPARISON: comparison table with rows for each metric (Asking Price, Size, AED/sqft, Beds/Baths, Availability, Active Listings) and columns per option",
                "05 — STRATEGIC ASSESSMENT: market context callout, named advisory sections per option (ALL-CAPS heading + paragraph), then numbered approach items (number, action heading, detail paragraph)",
            ],
            "tone": "clean professional estate-agent acquisition brief for a client, concise but authoritative",
            "listing_card_format": {
                "label": "COMMUNITY — TYPE — POSITIONING STATEMENT (all caps, e.g. CASA — TYPE 1 — STRONGEST VALUE IN CASA)",
                "price": "AED amount as string, e.g. AED 5,500,000",
                "description_tag": "short status tag, e.g. Ready To Move | Stand Alone Villa",
                "stats_line": "N Beds · N Baths · N sqft · N AED/sqft",
                "narrative": "one short paragraph of agent commentary on this listing",
            },
        },
        "strict_client_safety_rules": [
            "Do not include URLs, source names, agent names, owner lookup language, permit numbers, broker instructions, or poach/listing-opportunity language.",
            "Do not copy exact listing titles or uncommon searchable phrases from the source rows.",
            "Use approximate language for price and size: around, approx., guide price, near-immediate, large plot style, single-row style.",
            "Write as the agent's client-facing acquisition brief. It should protect the source while giving enough confidence to proceed.",
            "listing label must follow the format: COMMUNITY — TYPE — POSITIONING (all caps, using em-dash separators).",
            "stats_line must follow the format: N Beds · N Baths · N sqft · N AED/sqft (using middle-dot separators).",
            "approach_items must be numbered as 01, 02, 03 etc. and phrased as the agent taking action.",
        ],
        "candidate_rows": _client_report_rows(matches_df),
    }

    client = client_for_api_key(api_key)
    response = client.responses.create(
        model="gpt-5-mini",
        instructions=(
            "You are preparing a client-safe Dubai property shortlist report for an estate agent. "
            "Use only the supplied structured data. Return JSON only. "
            "Protect the agent's sourcing: no listing URLs, exact listing titles, agent names, permit numbers, or poach language."
        ),
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "client_property_report",
                "strict": True,
                "schema": CLIENT_REPORT_SCHEMA,
            }
        },
    )

    return {
        "client_report": json.loads(response.output_text),
        "enquiry": enquiry,
        "source_path": str(path),
        "candidate_count": int(len(matches_df)),
    }


def check_openai_key(api_key):
    if not api_key:
        raise RuntimeError("Missing OpenAI API key.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is not installed. Run: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=api_key, timeout=20.0, max_retries=0)
    response = client.responses.create(
        model="gpt-5-mini",
        instructions="You are checking whether this OpenAI API key can make a basic response.",
        input="Reply with OK only.",
        max_output_tokens=16,
    )

    return {
        "ok": True,
        "message": "OpenAI connection is ready. You can now use AI feedback.",
    }
