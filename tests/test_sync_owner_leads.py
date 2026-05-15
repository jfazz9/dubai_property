from scripts.sync_owner_leads import google_sheet_csv_url


def test_google_sheet_csv_url_converts_edit_url_with_gid():
    url = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=456"

    assert google_sheet_csv_url(url) == "https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=456"


def test_google_sheet_csv_url_uses_explicit_gid():
    url = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=456"

    assert google_sheet_csv_url(url, gid="789") == "https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=789"


def test_google_sheet_csv_url_can_use_sheet_name():
    url = "https://docs.google.com/spreadsheets/d/abc123/edit?usp=sharing"

    assert google_sheet_csv_url(url, sheet="data") == "https://docs.google.com/spreadsheets/d/abc123/gviz/tq?tqx=out%3Acsv&sheet=data"


def test_google_sheet_csv_url_leaves_non_google_url_alone():
    url = "https://example.com/file.csv"

    assert google_sheet_csv_url(url) == url
