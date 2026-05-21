from scripts.webapp_backend.opportunity_scanner import _intent_signal
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
