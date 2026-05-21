from scripts.webapp_backend.opportunity_scanner import _intent_signal
from scripts.webapp_backend.opportunity_scanner import _agent_strength_score
from scripts.webapp_backend.opportunity_scanner import _agent_weakness_score
from scripts.webapp_backend.opportunity_scanner import _premium_justification_score
from scripts.webapp_backend.opportunity_scanner import _rule_score


def test_opportunity_scanner_reuses_negotiation_intent_signal():
    row = {
        "title": "Vacant | Motivated Seller | Price Reduced",
        "description": "Owner is motivated and the villa is vacant.",
    }

    assert _intent_signal(row, "negotiation") > 0


def test_premium_justification_reduces_overpriced_rule_score():
    median = {"Yasmin": 10_000_000}
    plain_row = {
        "predicted_community": "Yasmin",
        "price": 12_000_000,
        "description": "Standard villa.",
        "_days_on_market": 0,
        "_premium_justification_score": 0,
    }
    premium_row = {
        **plain_row,
        "description": "Fully upgraded villa with private pool on a corner plot.",
        "_premium_justification_score": _premium_justification_score({
            "title": "Fully Upgraded | Private Pool | Corner Plot",
            "description": "Luxury renovated villa with private pool.",
        }),
    }

    assert _rule_score(plain_row, median, "sale") > _rule_score(premium_row, median, "sale")


def test_agent_strength_reduces_stale_rule_score():
    median = {"Rosa": 10_000_000}
    weak_agent_row = {
        "predicted_community": "Rosa",
        "price": 10_000_000,
        "description": "Short listing.",
        "_days_on_market": 90,
        "_premium_justification_score": 0,
        "_agent_strength_score": _agent_strength_score({}),
        "_agent_weakness_score": _agent_weakness_score({}),
    }
    strong_agent = {
        "agent_rating": 4.9,
        "agent_review_count": 20,
        "agent_closed_deals": 12,
        "agent_is_superagent": True,
        "agent_response_time": "5 mins",
    }
    strong_agent_row = {
        **weak_agent_row,
        "_agent_strength_score": _agent_strength_score(strong_agent),
        "_agent_weakness_score": _agent_weakness_score(strong_agent),
    }

    assert _rule_score(weak_agent_row, median, "sale") > _rule_score(strong_agent_row, median, "sale")
