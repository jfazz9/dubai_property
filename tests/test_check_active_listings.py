import pandas as pd

from scripts.check_active_listings import (
    ActiveCheckResult,
    classify_response,
    run_active_checks,
)


class FakeResponse:
    def __init__(self, url, status_code=200, text=""):
        self.url = url
        self.status_code = status_code
        self.text = text


def test_classify_response_marks_listing_page_active():
    result = classify_response(
        "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-dubai-arabian-ranches-2-casa-123.html",
        FakeResponse(
            "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-dubai-arabian-ranches-2-casa-123.html",
            200,
            "Villa for sale in Casa",
        ),
    )

    assert result.is_active is True
    assert result.status == "active"


def test_classify_response_marks_search_redirect_inactive():
    result = classify_response(
        "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-dubai-arabian-ranches-2-casa-123.html",
        FakeResponse(
            "https://www.propertyfinder.ae/en/buy/properties-for-sale.html",
            200,
            "Properties for sale",
        ),
    )

    assert result.is_active is False
    assert result.status == "inactive_redirected_to_search"


def test_classify_response_keeps_human_verification_unknown_active():
    result = classify_response(
        "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-dubai-arabian-ranches-2-casa-123.html",
        FakeResponse(
            "https://www.propertyfinder.ae/en/plp/buy/villa-for-sale-dubai-arabian-ranches-2-casa-123.html",
            200,
            "Human Verification",
        ),
    )

    assert result.is_active is True
    assert result.status == "unknown_human_verification"


def test_run_active_checks_only_checks_currently_active_rows():
    master_df = pd.DataFrame([
        {
            "url": "https://example.com/active",
            "is_active": True,
        },
        {
            "url": "https://example.com/inactive",
            "is_active": False,
        },
    ])
    checked_urls = []

    def checker(url):
        checked_urls.append(url)
        return ActiveCheckResult(False, "inactive_not_found_text", "removed")

    updated_df, results_df = run_active_checks(
        master_df,
        checker=checker,
        checked_at="2026-05-14 10:00:00",
    )

    assert checked_urls == ["https://example.com/active"]
    assert len(results_df) == 1
    assert updated_df.loc[0, "is_active"] == False
    assert updated_df.loc[0, "active_checked_at"] == "2026-05-14 10:00:00"
    assert updated_df.loc[1, "is_active"] == False
