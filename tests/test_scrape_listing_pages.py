import pandas as pd

from scripts import scrape_listing_pages


def test_load_master_urls_reads_existing_master(monkeypatch, tmp_path):
    master_file = tmp_path / "listing_details_master.csv"
    pd.DataFrame([
        {"url": "https://example.com/known-1"},
        {"url": "https://example.com/known-2"},
        {"url": None},
    ]).to_csv(master_file, index=False)

    monkeypatch.setattr(scrape_listing_pages, "master_file", lambda purpose: master_file)

    assert scrape_listing_pages.load_master_urls("rent") == {
        "https://example.com/known-1",
        "https://example.com/known-2",
    }


def test_load_master_urls_returns_empty_set_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape_listing_pages, "master_file", lambda purpose: tmp_path / "missing.csv")

    assert scrape_listing_pages.load_master_urls("rent") == set()


def test_latest_matching_raw_file_finds_previous_partial_run(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    old_file = raw_dir / "listing_pages_2026-05-13_10-00.csv"
    matching_file = raw_dir / "listing_pages_2026-05-13_11-00.csv"

    pd.DataFrame([
        {"url": "https://example.com/other", "page_status": "ok"},
    ]).to_csv(old_file, index=False)
    pd.DataFrame([
        {"url": "https://example.com/one", "page_status": "ok"},
    ]).to_csv(matching_file, index=False)

    monkeypatch.setattr(scrape_listing_pages, "raw_dir", lambda purpose: raw_dir)

    assert scrape_listing_pages.latest_matching_raw_file("rent", [
        "https://example.com/one",
        "https://example.com/two",
    ]) == matching_file
