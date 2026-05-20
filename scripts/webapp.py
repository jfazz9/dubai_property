import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from workflow_paths import normalize_purpose
from webapp_backend import (
    DEFAULT_RESULT_LIMIT,
    ai_client_report_prompt,
    ai_fallback_prompt,
    ai_feedback_prompt,
    ai_scenario_rank_prompt,
    ai_scenario_report_prompt,
    ai_scenario_prompt,
    add_similar_listing_warnings,
    build_budget_fallback_dataframe,
    build_budget_reality_primary_dataframe,
    build_market_context,
    build_over_budget_dataframe,
    check_openai_key,
    clean_number,
    lookup_owner_in_df,
    lookup_owner,
    match_enquiry,
    match_prompt,
    metric_html,
    money,
    parse_prompt,
    quick_listing_query,
    rows_payload,
    valuation_estimate,
)


HOST = "127.0.0.1"
PORT = 8000

HTML = Path(__file__).parent.joinpath("webapp_template.html").read_text(encoding="utf-8")

MARKET_COMMUNITIES = ["Azalea", "Camelia", "Casa", "Lila", "Palma", "Rasha", "Reem", "Rosa", "Samara", "Yasmin"]


def page_for_result(
    result=None,
    prompt="",
    selected_purpose="auto",
    selected_intent="auto",
    selected_listing_scope="auto",
    selected_listing_communities=None,
    selected_market_scope="auto",
    selected_market_communities=None,
    error_message="",
):
    selected = {
        "auto": "",
        "sale": "",
        "rent": "",
    }
    intent_selected = {
        "auto": "",
        "best_value": "",
        "move_in_ready": "",
        "upgrade_potential": "",
        "negotiation": "",
        "listing_opportunity": "",
    }
    market_selected = {
        "auto": "",
        "exact": "",
        "similar": "",
        "custom": "",
    }
    listing_selected = {
        "auto": "",
        "exact": "",
        "similar": "",
        "custom": "",
    }
    selected_listing_communities = selected_listing_communities or []
    selected_market_communities = selected_market_communities or []
    selected[normalize_purpose(selected_purpose) if selected_purpose in {"sale", "rent"} else "auto"] = "selected"
    intent_selected[selected_intent if selected_intent in intent_selected else "auto"] = "selected"
    listing_selected[selected_listing_scope if selected_listing_scope in listing_selected else "auto"] = "selected"
    market_selected[selected_market_scope if selected_market_scope in market_selected else "auto"] = "selected"
    listing_checkboxes = "\n".join(
        f'<label><input class="listing-community" type="checkbox" name="listing_communities" value="{escape(community)}" {"checked" if community in selected_listing_communities else ""}> {escape(community)}</label>'
        for community in MARKET_COMMUNITIES
    )
    market_checkboxes = "\n".join(
        f'<label><input class="market-community" type="checkbox" name="market_communities" value="{escape(community)}" {"checked" if community in selected_market_communities else ""}> {escape(community)}</label>'
        for community in MARKET_COMMUNITIES
    )
    summary_html = ""
    response_html = ""
    results_html = ""
    above_budget_html = ""
    response_hidden = "hidden"
    above_budget_hidden = "hidden"
    error_hidden = "hidden"
    error_html = escape(error_message)

    if result:
        enquiry = result["enquiry"]
        purpose = enquiry["purpose"]
        summary_html = "".join([
            metric_html("Purpose", purpose),
            metric_html("Budget", money(enquiry.get("budget"), purpose)),
            metric_html("Search ceiling", money(enquiry.get("stretch_budget"), purpose)),
            metric_html("Beds", enquiry.get("bedrooms_label")),
            metric_html("Community", enquiry.get("community") or "Any"),
            metric_html("Intent", enquiry.get("search_intent", "auto").replace("_", " ").title()),
        ])
        response_html = escape(result["client_response"])
        response_hidden = ""

        for item in result["matches"]:
            title = escape(str(item.get("title") or "Untitled listing"))
            listing_url = escape(str(item.get("url") or "#"))
            reasons = escape(str(item.get("match_reasons") or ""))
            clues = escape(str(item.get("outdoor_matches") or ""))
            clue_html = f'<div class="reasons"><strong>Clues:</strong> {clues}</div>' if clues else ""
            results_html += f"""
        <article class="listing">
          <div>
            <h2>{title}</h2>
            <div class="facts">
              <span class="pill price">{escape(money(item.get("price"), purpose))}</span>
              <span class="pill">{escape(str(item.get("bedrooms") or "?"))} bed</span>
              <span class="pill">{escape(str(item.get("bathrooms") or "?"))} bath</span>
              <span class="pill">{escape(str(item.get("predicted_community") or "Unknown"))}</span>
              <span class="pill">{escape(str(item.get("predicted_type") or "Type unknown"))}</span>
              <span class="pill">{escape(str(item.get("property_size_sqft") or "?"))} sqft</span>
            </div>
            <div class="reasons">{reasons}</div>
            {clue_html}
            {f'<div class="exclusive-box"><strong>Exclusive listing:</strong> likely strong agent-owner relationship. Avoid owner call unless you have another clear lead.</div>' if item.get("has_exclusive_warning") else ""}
            {f'<div class="similar-box"><strong>Similar listing warning:</strong> {escape(str(item.get("similar_count")))} listings share close price/details. Check photos before treating as the same property.</div>' if clean_number(item.get("similar_count")) and clean_number(item.get("similar_count")) > 1 else ""}
            <div class="card-actions">
              <a href="{listing_url}" target="_blank" rel="noreferrer">Open listing</a>
              <button class="mini copy-link-button" type="button" data-copy="{listing_url}">Copy link</button>
            </div>
          </div>
          <div class="score"><span class="score-badge">{escape(str(item.get("match_score") or 0))}</span></div>
        </article>
"""

        over_budget_matches = result.get("over_budget_matches", [])
        above_budget_hidden = "hidden" if not over_budget_matches else ""

        for item in over_budget_matches:
            title = escape(str(item.get("title") or "Untitled listing"))
            listing_url = escape(str(item.get("url") or "#"))
            reasons = escape(str(item.get("match_reasons") or ""))
            clues = escape(str(item.get("outdoor_matches") or ""))
            clue_html = f'<div class="reasons"><strong>Clues:</strong> {clues}</div>' if clues else ""
            above_budget_html += f"""
        <article class="listing">
          <div>
            <h2>{title}</h2>
            <div class="facts">
              <span class="pill price">{escape(money(item.get("price"), purpose))}</span>
              <span class="pill">{escape(str(item.get("bedrooms") or "?"))} bed</span>
              <span class="pill">{escape(str(item.get("bathrooms") or "?"))} bath</span>
              <span class="pill">{escape(str(item.get("predicted_community") or "Unknown"))}</span>
              <span class="pill">{escape(str(item.get("predicted_type") or "Type unknown"))}</span>
              <span class="pill">{escape(str(item.get("property_size_sqft") or "?"))} sqft</span>
            </div>
            <div class="reasons">{reasons}</div>
            {clue_html}
            {f'<div class="exclusive-box"><strong>Exclusive listing:</strong> likely strong agent-owner relationship. Avoid owner call unless you have another clear lead.</div>' if item.get("has_exclusive_warning") else ""}
            <div class="card-actions">
              <a href="{listing_url}" target="_blank" rel="noreferrer">Open listing</a>
              <button class="mini copy-link-button" type="button" data-copy="{listing_url}">Copy link</button>
            </div>
          </div>
          <div class="score"><span class="score-badge">{escape(str(item.get("match_score") or 0))}</span></div>
        </article>
"""

    if error_message:
        error_hidden = ""

    return (
        HTML
        .replace("__PROMPT__", escape(prompt))
        .replace("__INTENT_AUTO_SELECTED__", intent_selected["auto"])
        .replace("__INTENT_BEST_VALUE_SELECTED__", intent_selected["best_value"])
        .replace("__INTENT_MOVE_IN_READY_SELECTED__", intent_selected["move_in_ready"])
        .replace("__INTENT_UPGRADE_POTENTIAL_SELECTED__", intent_selected["upgrade_potential"])
        .replace("__INTENT_NEGOTIATION_SELECTED__", intent_selected["negotiation"])
        .replace("__INTENT_LISTING_OPPORTUNITY_SELECTED__", intent_selected["listing_opportunity"])
        .replace("__LISTING_AUTO_SELECTED__", listing_selected["auto"])
        .replace("__LISTING_EXACT_SELECTED__", listing_selected["exact"])
        .replace("__LISTING_SIMILAR_SELECTED__", listing_selected["similar"])
        .replace("__LISTING_CUSTOM_SELECTED__", listing_selected["custom"])
        .replace("__LISTING_COMMUNITY_CHECKBOXES__", listing_checkboxes)
        .replace("__MARKET_AUTO_SELECTED__", market_selected["auto"])
        .replace("__MARKET_EXACT_SELECTED__", market_selected["exact"])
        .replace("__MARKET_SIMILAR_SELECTED__", market_selected["similar"])
        .replace("__MARKET_CUSTOM_SELECTED__", market_selected["custom"])
        .replace("__MARKET_COMMUNITY_CHECKBOXES__", market_checkboxes)
        .replace("__AUTO_SELECTED__", selected["auto"])
        .replace("__SALE_SELECTED__", selected["sale"])
        .replace("__RENT_SELECTED__", selected["rent"])
        .replace("__SUMMARY_HTML__", summary_html)
        .replace("__RESPONSE_HTML__", response_html)
        .replace("__RESPONSE_HIDDEN__", response_hidden)
        .replace("__ERROR_HTML__", error_html)
        .replace("__ERROR_HIDDEN__", error_hidden)
        .replace("__RESULTS_HTML__", results_html)
        .replace("__ABOVE_BUDGET_HTML__", above_budget_html)
        .replace("__ABOVE_BUDGET_HIDDEN__", above_budget_hidden)
    )


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path not in {"/", "/index.html", "/search"}:
            self.send_error(404)
            return

        if path == "/search":
            params = parse_qs(parsed_url.query)
            prompt = params.get("prompt", [""])[0]
            purpose = params.get("purpose", ["auto"])[0]
            intent = params.get("intent", ["auto"])[0]
            listing_scope = params.get("listing_scope", ["auto"])[0]
            listing_communities = params.get("listing_communities", [])
            market_scope = params.get("market_scope", ["auto"])[0]
            market_communities = params.get("market_communities", [])

            try:
                body_text = page_for_result(
                    match_prompt(
                        prompt,
                        selected_purpose=purpose,
                        selected_intent=intent,
                        listing_scope=listing_scope,
                        listing_communities=listing_communities,
                        market_scope=market_scope,
                        market_communities=market_communities,
                        limit=DEFAULT_RESULT_LIMIT,
                    ),
                    prompt=prompt,
                    selected_purpose=purpose,
                    selected_intent=intent,
                    selected_listing_scope=listing_scope,
                    selected_listing_communities=listing_communities,
                    selected_market_scope=market_scope,
                    selected_market_communities=market_communities,
                )
            except Exception as exc:
                body_text = page_for_result(
                    prompt=prompt,
                    selected_purpose=purpose,
                    selected_intent=intent,
                    selected_listing_scope=listing_scope,
                    selected_listing_communities=listing_communities,
                    selected_market_scope=market_scope,
                    selected_market_communities=market_communities,
                    error_message=str(exc),
                )
        else:
            body_text = page_for_result()

        body = body_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path

        if path not in {"/api/match", "/api/quick-query", "/api/ai-feedback", "/api/ai-fallback", "/api/ai-scenario", "/api/ai-scenario-rank", "/api/ai-scenario-report", "/api/client-report", "/api/check-openai", "/api/owner-lookup", "/api/estimate"}:
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/api/check-openai":
                result = check_openai_key(payload.get("api_key"))
            elif path == "/api/owner-lookup":
                result = lookup_owner(payload.get("url", ""))
            elif path == "/api/quick-query":
                result = quick_listing_query(
                    selected_purpose=payload.get("purpose", "sale"),
                    min_beds=payload.get("min_beds"),
                    max_beds=payload.get("max_beds"),
                    min_price=payload.get("min_price"),
                    max_price=payload.get("max_price"),
                    community=payload.get("community", ""),
                    category=payload.get("category", "any"),
                    limit=DEFAULT_RESULT_LIMIT,
                )
            elif path == "/api/ai-feedback":
                result = ai_feedback_prompt(
                    payload.get("prompt", ""),
                    selected_purpose=payload.get("purpose", "auto"),
                    selected_intent=payload.get("intent", "auto"),
                    listing_scope=payload.get("listing_scope", "auto"),
                    listing_communities=payload.get("listing_communities", []),
                    market_scope=payload.get("market_scope", "auto"),
                    market_communities=payload.get("market_communities", []),
                    api_key=payload.get("api_key"),
                    limit=int(payload.get("limit", 10)),
                )
            elif path == "/api/ai-fallback":
                result = ai_fallback_prompt(
                    payload.get("prompt", ""),
                    selected_purpose=payload.get("purpose", "auto"),
                    api_key=payload.get("api_key"),
                    limit=int(payload.get("limit", 10)),
                    listing_scope=payload.get("listing_scope", "auto"),
                    listing_communities=payload.get("listing_communities", []),
                    market_scope=payload.get("market_scope", "auto"),
                    market_communities=payload.get("market_communities", []),
                )
            elif path == "/api/ai-scenario":
                result = ai_scenario_prompt(
                    payload.get("prompt", ""),
                    payload.get("scenario", "best_value"),
                    selected_purpose=payload.get("purpose", "auto"),
                    api_key=payload.get("api_key"),
                    limit=int(payload.get("limit", 10)),
                    listing_scope=payload.get("listing_scope", "auto"),
                    listing_communities=payload.get("listing_communities", []),
                    market_scope=payload.get("market_scope", "auto"),
                    market_communities=payload.get("market_communities", []),
                )
            elif path == "/api/ai-scenario-rank":
                result = ai_scenario_rank_prompt(
                    payload.get("prompt", ""),
                    payload.get("scenario", "best_value"),
                    selected_purpose=payload.get("purpose", "auto"),
                    api_key=payload.get("api_key"),
                    limit=int(payload.get("limit", 10)),
                    listing_scope=payload.get("listing_scope", "auto"),
                    listing_communities=payload.get("listing_communities", []),
                    market_scope=payload.get("market_scope", "auto"),
                    market_communities=payload.get("market_communities", []),
                )
            elif path == "/api/ai-scenario-report":
                result = ai_scenario_report_prompt(
                    payload.get("prompt", ""),
                    payload.get("scenario", "best_value"),
                    ranked_urls=payload.get("ranked_urls", []),
                    selected_purpose=payload.get("purpose", "auto"),
                    api_key=payload.get("api_key"),
                    limit=int(payload.get("limit", 10)),
                    listing_scope=payload.get("listing_scope", "auto"),
                    listing_communities=payload.get("listing_communities", []),
                    market_scope=payload.get("market_scope", "auto"),
                    market_communities=payload.get("market_communities", []),
                )
            elif path == "/api/client-report":
                result = ai_client_report_prompt(
                    payload.get("prompt", ""),
                    payload.get("scenario", "best_value"),
                    ranked_urls=payload.get("ranked_urls", []),
                    selected_purpose=payload.get("purpose", "auto"),
                    api_key=payload.get("api_key"),
                    limit=int(payload.get("limit", 6)),
                    listing_scope=payload.get("listing_scope", "auto"),
                    listing_communities=payload.get("listing_communities", []),
                    market_scope=payload.get("market_scope", "auto"),
                    market_communities=payload.get("market_communities", []),
                )
            elif path == "/api/estimate":
                result = valuation_estimate(
                    payload.get("prompt", ""),
                    selected_purpose=payload.get("purpose", "sale"),
                    api_key=payload.get("api_key"),
                    extra_communities=payload.get("extra_communities", []),
                )
            else:
                result = match_prompt(
                    payload.get("prompt", ""),
                    selected_purpose=payload.get("purpose", "auto"),
                    selected_intent=payload.get("intent", "auto"),
                    listing_scope=payload.get("listing_scope", "auto"),
                    listing_communities=payload.get("listing_communities", []),
                    market_scope=payload.get("market_scope", "auto"),
                    market_communities=payload.get("market_communities", []),
                    limit=int(payload.get("limit", 10)),
                )
            self.send_json(result)
        except Exception as exc:
            traceback.print_exc()
            message = str(exc)

            if "insufficient_quota" in message or "quota" in message.lower():
                message = "OpenAI quota/billing issue. Check your OpenAI billing and usage limits."
            elif "invalid_api_key" in message or "Incorrect API key" in message:
                message = "OpenAI API key was rejected. Create a fresh key and try again."
            elif "timed out" in message.lower() or "timeout" in message.lower():
                message = "OpenAI request timed out. Try again, or reduce the number of results."

            self.send_json({"error": message}, status=400)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    server = ThreadingHTTPServer((HOST, port), AppHandler)
    print(f"Property Detector web app running at http://{HOST}:{port}/")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
