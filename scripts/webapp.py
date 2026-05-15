import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from urllib.parse import parse_qs, urlparse

from workflow_paths import normalize_purpose
from webapp_backend import (
    DEFAULT_RESULT_LIMIT,
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
)


HOST = "127.0.0.1"
PORT = 8000

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Property Detector</title>
  <style>
    :root {
      --ink: #17211c;
      --muted: #66736b;
      --line: #d7ded8;
      --wash: #f5f6f3;
      --panel: #ffffff;
      --accent: #0b6b57;
      --accent-2: #b8742a;
      --danger: #9b2d20;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, Arial, sans-serif;
      font-size: 14px;
      color: var(--ink);
      background: var(--wash);
    }
    main {
      width: min(1140px, calc(100vw - 24px));
      margin: 0 auto;
      padding: 20px 0 60px;
    }

    /* ── Header ── */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .brand h1 {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .brand .sub {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
    }
    .hdr-actions {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .ghost {
      min-height: 30px;
      padding: 0 10px;
      font: inherit;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--muted);
      cursor: pointer;
    }
    .ghost:hover { color: var(--ink); background: var(--wash); }
    .ghost.on { border-color: var(--accent); color: var(--accent); background: #f0faf6; }
    .status-pill {
      font-size: 11px;
      color: var(--muted);
      background: var(--wash);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 9px;
    }

    /* ── AI key bar ── */
    .key-bar {
      display: flex;
      gap: 8px;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 12px;
      margin-bottom: 10px;
    }
    .key-bar.ready { border-color: var(--accent); background: #f0faf6; }
    .key-bar input {
      flex: 1;
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
      font-size: 13px;
    }

    /* ── Quick filter bar ── */
    .quick-bar {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 10px;
      display: grid;
      grid-template-columns: repeat(8, minmax(0, 1fr));
      gap: 6px;
      align-items: end;
    }
    .quick-bar .field { display: flex; flex-direction: column; gap: 3px; }
    .quick-bar label { font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
    .quick-bar input, .quick-bar select {
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 8px;
      font: inherit;
      font-size: 13px;
      background: #fff;
    }

    /* ── Search card ── */
    .search-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      margin-bottom: 16px;
    }
    .search-card textarea {
      display: block;
      width: 100%;
      min-height: 64px;
      max-height: 140px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 9px 11px;
      font: inherit;
      font-size: 14px;
      line-height: 1.45;
      color: var(--ink);
      background: var(--wash);
    }
    .search-card textarea:focus {
      outline: 2px solid rgba(11,107,87,0.18);
      border-color: var(--accent);
      background: #fff;
    }
    .ctrl-row {
      display: flex;
      gap: 6px;
      align-items: center;
      margin-top: 8px;
      flex-wrap: wrap;
    }
    .ctrl-row select {
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 6px;
      font: inherit;
      font-size: 12px;
      background: #fff;
      color: var(--ink);
      flex: 1;
      min-width: 90px;
    }
    .find-btn {
      min-height: 32px;
      padding: 0 20px;
      border: none;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      white-space: nowrap;
    }
    .find-btn:disabled { opacity: 0.6; cursor: wait; }

    /* Communities popover */
    .comm-picker { position: relative; }
    .comm-btn {
      min-height: 32px;
      padding: 0 11px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--muted);
      font: inherit;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
    }
    .comm-btn:hover { color: var(--ink); }
    .comm-btn.active { border-color: var(--accent); color: var(--accent); }
    .comm-panel {
      position: absolute;
      top: calc(100% + 4px);
      right: 0;
      z-index: 200;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-width: 300px;
      box-shadow: 0 6px 24px rgba(0,0,0,0.10);
    }
    .comm-scopes {
      display: flex;
      gap: 6px;
      margin-bottom: 8px;
    }
    .comm-scopes select {
      flex: 1;
      min-height: 30px;
      border: 1px solid var(--line);
      border-radius: 5px;
      padding: 0 7px;
      font: inherit;
      font-size: 12px;
    }
    .comm-dual {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .comm-section {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      margin: 8px 0 4px;
    }
    .comm-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 3px 8px;
    }
    .comm-grid label {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 12px;
      color: var(--muted);
      cursor: pointer;
      padding: 2px 0;
    }
    .comm-grid label:hover { color: var(--ink); }

    /* AI chips row */
    .ai-row {
      display: flex;
      gap: 5px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--line);
    }
    .ai-label {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--muted);
      padding-right: 3px;
    }
    .chip {
      min-height: 24px;
      padding: 0 10px;
      font: inherit;
      font-size: 12px;
      font-weight: 600;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      cursor: pointer;
    }
    .chip:hover { color: var(--ink); background: var(--wash); }
    .chip:disabled { opacity: 0.5; cursor: wait; }
    .chip.general { border-color: var(--accent-2); color: var(--accent-2); }
    .chip.general:hover { background: #fffaf2; }
    .report-chip {
      min-height: 24px;
      padding: 0 12px;
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      border-radius: 999px;
      border: none;
      background: #264f7a;
      color: #fff;
      cursor: pointer;
      margin-left: auto;
    }
    .report-chip:disabled { opacity: 0.5; cursor: wait; }

    /* ── Summary metrics ── */
    .summary {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }
    .metric {
      flex: 1;
      min-width: 90px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 7px;
      padding: 8px 11px;
    }
    .metric span {
      display: block;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      margin-bottom: 3px;
    }
    .metric strong { font-size: 15px; line-height: 1.2; }

    /* ── Response / AI panels ── */
    .response {
      white-space: pre-wrap;
      border-left: 4px solid var(--accent-2);
      background: #fffaf2;
      padding: 11px 14px;
      margin-bottom: 14px;
      color: #332416;
      border-radius: 0 6px 6px 0;
      font-size: 13px;
      line-height: 1.5;
    }
    .ai-panel {
      border-left: 4px solid var(--accent);
      background: #f0faf6;
      padding: 11px 14px;
      margin-bottom: 14px;
      color: #14342c;
      border-radius: 0 6px 6px 0;
    }
    .ai-panel h2 { font-size: 15px; margin-bottom: 7px; }
    .ai-panel pre { white-space: pre-wrap; font: inherit; font-size: 13px; line-height: 1.5; }
    .report-section { margin-bottom: 12px; }
    .toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }

    /* ── Spinner ── */
    .spinner {
      width: 30px; height: 30px;
      border: 3px solid var(--line);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 0.75s linear infinite;
      margin: 44px auto;
      display: none;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Error ── */
    .error {
      color: var(--danger);
      font-weight: 700;
      margin: 10px 0;
      padding: 10px 13px;
      background: #fff4f3;
      border: 1px solid #e8c5c2;
      border-radius: 6px;
      font-size: 13px;
    }

    /* ── Results ── */
    .results { display: grid; gap: 10px; }
    .section-title {
      font-size: 16px;
      font-weight: 700;
      margin: 18px 0 8px;
    }
    .watchlist-note { color: var(--muted); font-size: 12px; margin: -4px 0 8px; }

    /* ── Listing card ── */
    .listing {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      padding: 13px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .listing h2 {
      font-size: 15px;
      font-weight: 700;
      line-height: 1.3;
      margin-bottom: 7px;
    }
    .facts {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin-bottom: 7px;
    }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      color: var(--muted);
      background: #fbfcfa;
    }
    .pill.price { background: var(--ink); color: #fff; border-color: var(--ink); font-weight: 700; }
    .reasons { color: var(--muted); font-size: 13px; line-height: 1.45; margin-bottom: 3px; }
    .similar-box {
      border-left: 3px solid var(--accent-2);
      background: #fffaf2;
      padding: 7px 10px;
      margin-top: 7px;
      color: #4a3520;
      font-size: 12px;
      line-height: 1.45;
    }
    .exclusive-box {
      border-left: 3px solid var(--danger);
      background: #fff4f3;
      padding: 7px 10px;
      margin-top: 7px;
      color: #5d1d17;
      font-size: 12px;
    }
    .card-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      align-items: center;
      margin-top: 8px;
    }
    .mini {
      min-height: 26px;
      padding: 0 9px;
      font: inherit;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid var(--line);
      border-radius: 5px;
      background: #fff;
      color: var(--ink);
      cursor: pointer;
    }
    .score {
      display: flex;
      align-items: flex-start;
      padding-top: 2px;
    }
    .score-badge {
      min-width: 38px;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      text-align: center;
      color: #fff;
    }
    .score-badge.high { background: var(--accent); }
    .score-badge.mid { background: var(--accent-2); }
    .score-badge.low { background: var(--muted); }
    a { color: var(--accent); font-weight: 700; text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* ── Owner drawer ── */
    .drawer-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.18);
      z-index: 298;
    }
    .owner-drawer {
      position: fixed;
      top: 0; right: 0;
      width: 320px;
      height: 100%;
      background: var(--panel);
      border-left: 1px solid var(--line);
      box-shadow: -4px 0 20px rgba(0,0,0,0.08);
      z-index: 299;
      display: flex;
      flex-direction: column;
      transform: translateX(100%);
      transition: transform 0.2s ease;
    }
    .owner-drawer.open { transform: translateX(0); }
    .drawer-hdr {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
    }
    .drawer-hdr h2 { font-size: 15px; }
    .drawer-close {
      width: 28px; height: 28px;
      border: 1px solid var(--line);
      border-radius: 5px;
      background: #fff;
      font-size: 16px;
      cursor: pointer;
      color: var(--muted);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .drawer-body { padding: 14px 16px; overflow-y: auto; flex: 1; }
    .drawer-body input {
      display: block;
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
      font-size: 13px;
      margin-bottom: 7px;
    }
    .drawer-body .lookup-btn {
      display: block;
      width: 100%;
      min-height: 36px;
      border: none;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      margin-bottom: 14px;
    }
    .owner-result {
      background: #f0faf6;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 11px;
      font-size: 13px;
      line-height: 1.6;
    }
    .owner-result div { margin-bottom: 2px; }

    /* ── Help panel ── */
    .help-panel {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 14px;
    }
    .help-panel h2 { font-size: 16px; margin-bottom: 10px; }
    .help-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .help-card {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 11px;
      background: #fbfcfa;
      line-height: 1.4;
    }
    .help-card h3 { font-size: 13px; margin-bottom: 5px; }
    .help-card code {
      display: block;
      white-space: pre-wrap;
      color: #23443b;
      background: #eef6f2;
      border-radius: 5px;
      padding: 6px 8px;
      margin: 5px 0;
      font-family: Consolas, monospace;
      font-size: 11px;
    }
    .help-card p { margin: 5px 0 0; color: var(--muted); font-size: 12px; }
    .help-card ol, .help-card ul { margin: 5px 0 0; padding-left: 16px; color: var(--muted); font-size: 12px; line-height: 1.5; }
    .help-card.wide { grid-column: 1 / -1; }

    /* ── Print ── */
    @media print {
      body { background: #fff; }
      header, .search-card, .toolbar, .owner-drawer, .drawer-overlay { display: none !important; }
      main { width: 100%; padding: 0; }
      .listing { break-inside: avoid; }
    }

    /* ── Mobile ── */
    @media (max-width: 680px) {
      main { width: calc(100vw - 14px); padding-top: 12px; }
      .hdr-actions { gap: 4px; }
      .ctrl-row { flex-direction: column; align-items: stretch; }
      .ctrl-row select, .find-btn { width: 100%; }
      .summary { display: grid; grid-template-columns: repeat(2, 1fr); }
      .listing { grid-template-columns: 1fr; }
      .help-grid { grid-template-columns: 1fr; }
      .owner-drawer { width: 100%; }
      .quick-bar { grid-template-columns: 1fr 1fr; }
      .comm-panel { min-width: 260px; }
    }
  </style>
</head>
<body>
  <main>

    <!-- Header -->
    <header>
      <div class="brand">
        <h1>Property Detector</h1>
        <div class="sub">Search your master data with a client-style prompt</div>
      </div>
      <div class="hdr-actions">
        <button class="ghost" id="clear-page" type="button">Clear</button>
        <button class="ghost" id="quick-toggle" type="button">Quick filter</button>
        <button class="ghost" id="owner-toggle" type="button">Owner lookup</button>
        <button class="ghost" id="ai-key-toggle" type="button">AI key</button>
        <button class="ghost" id="help-toggle" type="button">Help</button>
        <span class="status-pill" id="status">Local data only</span>
      </div>
    </header>

    <!-- AI key bar (hidden by default) -->
    <div class="key-bar" id="key-bar" hidden>
      <input id="openai-token" type="password" autocomplete="off" placeholder="OpenAI API key — session only, not saved">
      <button class="ghost" id="check-openai" type="button" style="white-space:nowrap">Check key</button>
    </div>

    <!-- Quick filter bar (hidden by default) -->
    <div class="quick-bar" id="quick-bar" hidden>
      <div class="field">
        <label>Type</label>
        <select id="quick-purpose"><option value="sale">Sale</option><option value="rent">Rent</option></select>
      </div>
      <div class="field">
        <label>Beds min</label>
        <input id="quick-bed-min" type="number" min="0" step="1" placeholder="0">
      </div>
      <div class="field">
        <label>Beds max</label>
        <input id="quick-bed-max" type="number" min="0" step="1" placeholder="Any">
      </div>
      <div class="field">
        <label>Price min</label>
        <input id="quick-price-min" type="text" placeholder="e.g. 1m">
      </div>
      <div class="field">
        <label>Price max</label>
        <input id="quick-price-max" type="text" placeholder="e.g. 5m">
      </div>
      <div class="field">
        <label>Community</label>
        <input id="quick-community" type="text" placeholder="Any">
      </div>
      <div class="field">
        <label>Category</label>
        <select id="quick-category">
          <option value="any">Any type</option>
          <option value="villa">Villa</option>
          <option value="townhouse">Townhouse</option>
        </select>
      </div>
      <button id="quick-query" style="min-height:32px;align-self:flex-end;border-radius:6px;border:none;background:var(--accent);color:#fff;font:inherit;font-size:13px;font-weight:700;padding:0 14px;cursor:pointer">Filter</button>
    </div>

    <!-- Main search card -->
    <div class="search-card">
      <textarea id="prompt" name="prompt" placeholder="e.g. 3 bed villa in AR2, budget 5.5m">__PROMPT__</textarea>
      <div class="ctrl-row">
        <select id="intent" name="intent">
          <option value="auto" __INTENT_AUTO_SELECTED__>Intent: Auto</option>
          <option value="best_value" __INTENT_BEST_VALUE_SELECTED__>Best value</option>
          <option value="move_in_ready" __INTENT_MOVE_IN_READY_SELECTED__>Move-in ready</option>
          <option value="upgrade_potential" __INTENT_UPGRADE_POTENTIAL_SELECTED__>Upgrade potential</option>
          <option value="negotiation" __INTENT_NEGOTIATION_SELECTED__>Negotiation</option>
          <option value="listing_opportunity" __INTENT_LISTING_OPPORTUNITY_SELECTED__>Listing opp.</option>
        </select>
        <select id="purpose" name="purpose">
          <option value="auto" __AUTO_SELECTED__>Sale / Rent: Auto</option>
          <option value="sale" __SALE_SELECTED__>Sale</option>
          <option value="rent" __RENT_SELECTED__>Rent</option>
        </select>
        <div class="comm-picker">
          <button class="comm-btn" id="comm-btn" type="button">Communities ▾</button>
          <div class="comm-panel" id="comm-panel" hidden>
            <div class="comm-scopes">
              <select id="listing-scope" name="listing_scope">
                <option value="auto" __LISTING_AUTO_SELECTED__>Listings: Auto</option>
                <option value="exact" __LISTING_EXACT_SELECTED__>Prompt community</option>
                <option value="similar" __LISTING_SIMILAR_SELECTED__>Similar communities</option>
                <option value="custom" __LISTING_CUSTOM_SELECTED__>Custom listings</option>
              </select>
              <select id="market-scope" name="market_scope">
                <option value="auto" __MARKET_AUTO_SELECTED__>Comps: Auto</option>
                <option value="exact" __MARKET_EXACT_SELECTED__>Exact community</option>
                <option value="similar" __MARKET_SIMILAR_SELECTED__>Similar communities</option>
                <option value="custom" __MARKET_CUSTOM_SELECTED__>Custom comps</option>
              </select>
            </div>
            <label class="comm-dual">
              <input type="checkbox" id="dual-communities"> Mirror listing &amp; comp selection
            </label>
            <div class="comm-section">Listing communities</div>
            <div class="comm-grid" id="listing-custom">__LISTING_COMMUNITY_CHECKBOXES__</div>
            <div class="comm-section">Comp communities</div>
            <div class="comm-grid" id="market-custom">__MARKET_COMMUNITY_CHECKBOXES__</div>
          </div>
        </div>
        <button class="find-btn" id="search" type="button">Find</button>
      </div>
      <div class="ai-row">
        <span class="ai-label">AI</span>
        <button class="chip general" id="ai-feedback" type="button">General</button>
        <button class="chip scenario-button" type="button" data-scenario="best_value">Best value</button>
        <button class="chip scenario-button" type="button" data-scenario="budget_reality">Budget reality</button>
        <button class="chip scenario-button" type="button" data-scenario="fallback">Fallback</button>
        <button class="chip scenario-button" type="button" data-scenario="negotiation">Negotiation</button>
        <button class="chip scenario-button" type="button" data-scenario="listing_opportunity">Listing opp.</button>
        <button class="chip scenario-button" type="button" data-scenario="upgrade_potential">Upgrade</button>
        <button class="chip scenario-button" type="button" data-scenario="move_in_ready">Move-in ready</button>
        <button class="report-chip" id="ai-report" type="button">Build report</button>
      </div>
    </div>

    <!-- Help panel (hidden by default) -->
    <section class="help-panel" id="help-panel" hidden>
      <h2>Workflow Guide</h2>
      <div class="help-grid">
        <article class="help-card wide">
          <h3>Recommended Workflow</h3>
          <ol>
            <li>Write a simple client-style prompt with the hard facts: beds, product type, area, budget, sale/rent.</li>
            <li>Choose Intent so Find ranks the right kind of stock before OpenAI sees it.</li>
            <li>Choose Listings scope when the client will only consider certain communities.</li>
            <li>Choose Comps scope for the market evidence you want in the AI report.</li>
            <li>Press Find, scan the shortlist, then refine the prompt if the business angle needs more context.</li>
            <li>Press the matching scenario button to rank the shortlist, then Build report for the final write-up.</li>
          </ol>
        </article>
        <article class="help-card wide">
          <h3>Scope Controls</h3>
          <p>Listings controls what appears in Find. Comps controls which market sales or rentals OpenAI uses for evidence. Keep Listings broad for discovery; use Custom listings when the client will only accept specific communities.</p>
          <code>Example: 4 bed villa around 7m in Azalea</code>
          <p>Set Listings to Custom and tick Azalea + Lila if the client accepts Lila but not Casa/Samara. Set Comps to Custom and tick the same communities if you want the report to benchmark that exact buyer pool.</p>
        </article>
        <article class="help-card wide">
          <h3>Two-Step AI</h3>
          <ol>
            <li>General: broad AI feedback when you do not want a specific scenario.</li>
            <li>Scenario button: ranks the cards in batches and keeps timeout risk lower.</li>
            <li>Build report: uses the ranked cards and selected comps to produce the deeper market-backed report.</li>
          </ol>
        </article>
        <article class="help-card">
          <h3>Budget Reality</h3>
          <code>3 bed villa in Arabian Ranches 2 max 200k. Client does not want a townhouse.</code>
          <p>Intent: Budget reality button. Listings: usually Auto or Prompt community. Comps: Exact or Similar. Outcome: realistic above-budget options, market evidence, and a clear budget gap.</p>
          <code>Client wants a 3 bed villa in Arabian Ranches 2 max 210k. Do not lead with townhouses. Build a budget reality case using active villas and recent rentals.</code>
        </article>
        <article class="help-card">
          <h3>Analyse Fallback</h3>
          <code>3 bed villa in Arabian Ranches 2 max 200k. Client does not want a townhouse.</code>
          <p>Use after Budget reality. It should analyse premium compromises first, not just cheap alternatives.</p>
          <code>Analyse the fallback options. Prioritise premium townhouse compromises with single row, large plot, corner/end unit, vacant, upgraded, or better layout before cheaper stock.</code>
        </article>
        <article class="help-card">
          <h3>Best Value</h3>
          <code>3 bed villa in Arabian Ranches 2 budget 5.5m best value</code>
          <p>Intent: Best value. Boosts price reduced, motivated seller, lower ppsf, larger BUA/plot, VOT, and good layout. Outcome: strongest deal logic, not just cheapest listing.</p>
          <code>Find the best value 3 bed villa around 5.5m. Prioritise lower ppsf, larger plot or BUA, motivated seller, price reduction, VOT, and listings that are underpriced versus similar stock.</code>
        </article>
        <article class="help-card">
          <h3>Negotiation Case</h3>
          <code>3 bed villa Casa up to 5.9m. Build a negotiation case.</code>
          <p>Intent: Negotiation. Best when you need offer support. It should rank leverage: motivated seller, VOT, stale listing, high ppsf, BUA mismatch, overpricing, tenancy, or weak presentation.</p>
          <code>Build a negotiation case. Rank by leverage first, not prettiest home. Use active alternatives, recent comps, ppsf gaps, BUA discrepancies, vacancy, seller motivation, and offer angles.</code>
        </article>
        <article class="help-card">
          <h3>Listing Opportunity</h3>
          <code>3 bed villas in Arabian Ranches 2 around 5.5m listing opportunity</code>
          <p>Intent: Listing opportunity. Use from your agent perspective. Outcome: owners/listings worth chasing, while warning on exclusive listings.</p>
          <code>Find listing opportunities around 5.5m. Prioritise non-exclusive, stale, vacant, price-reduced, repeated, weakly presented, or owner-lead listings. Avoid calling owners on strong exclusive listings unless there is another clear lead.</code>
        </article>
        <article class="help-card">
          <h3>Upgrade Potential</h3>
          <code>3 bed villa in Arabian Ranches 2 with extension or renovation potential</code>
          <p>Intent: Upgrade potential. Find rewards blank canvas, original condition, large/corner plots, notice served, investor deal, and under-improved homes. It penalises fully upgraded, fully renovated, fully done, luxury, designer, and already extended stock.</p>
          <code>Looking for true value-add renovation or extension potential. Prioritise blank canvas, original condition, needs work, large or corner plots, notice served, investor deal, and under-improved homes. Do not prioritise already fully upgraded or luxury finished villas.</code>
        </article>
        <article class="help-card">
          <h3>Move-in Ready</h3>
          <code>3 bed villa in Arabian Ranches 2 clean upgraded ready to move</code>
          <p>Intent: Move-in ready. Use for end users or tenants who want low-hassle stock. It rewards upgraded, renovated, VOT, ready to move, well maintained, clean, owner occupied, furnished, and landscaped clues.</p>
          <code>Client wants a clean ready-to-move family home around 4m. Prioritise VOT, upgraded, renovated, well-maintained condition, low hassle, good photos/condition clues, and avoid rented or renovation project stock.</code>
        </article>
        <article class="help-card wide">
          <h3>Prompt Pattern</h3>
          <p>Start broad enough to avoid missing stock, then add context before the scenario button.</p>
          <code>Initial Find: 4 bed villa in Arabian Ranches 2, budget doesn't matter</code>
          <code>Refined before scenario: Looking for true value-add upgrade potential. Prioritise blank canvas, large plot, corner, original condition, investor deal, and notice served. Penalise fully upgraded or already extended homes.</code>
        </article>
      </div>
    </section>

    <!-- Results area -->
    <section class="summary" id="summary">__SUMMARY_HTML__</section>
    <div class="toolbar" id="report-toolbar" __RESPONSE_HIDDEN__>
      <button class="ghost" id="print-report" type="button">Save PDF</button>
    </div>
    <section class="response" id="response" __RESPONSE_HIDDEN__>
      <strong>Shortlist summary</strong><br><div>__RESPONSE_HTML__</div>
    </section>
    <section class="ai-panel" id="ai-panel" hidden></section>
    <h2 class="section-title" id="best-shortlist-title" __RESPONSE_HIDDEN__>Best Shortlist</h2>
    <section class="error" id="error" __ERROR_HIDDEN__>__ERROR_HTML__</section>
    <div class="spinner" id="spinner"></div>
    <section class="results" id="results">__RESULTS_HTML__</section>
    <section id="above-budget-section" __ABOVE_BUDGET_HIDDEN__>
      <h2 class="section-title">Above Budget Watchlist</h2>
      <div class="watchlist-note">Suitable options above the search ceiling, shown separately for market context.</div>
      <div class="results" id="above-budget-results">__ABOVE_BUDGET_HTML__</div>
    </section>
    <section id="fallback-section" hidden>
      <h2 class="section-title">Fallback Alternatives</h2>
      <div class="watchlist-note">Premium compromise options first, then budget alternatives.</div>
      <div class="results" id="fallback-results"></div>
    </section>
  </main>

  <!-- Owner lookup drawer -->
  <div class="drawer-overlay" id="drawer-overlay" hidden></div>
  <aside class="owner-drawer" id="owner-drawer">
    <div class="drawer-hdr">
      <h2>Owner Lookup</h2>
      <button class="drawer-close" id="close-owner-drawer" type="button">&#10005;</button>
    </div>
    <div class="drawer-body">
      <input id="owner-url" type="url" placeholder="Paste a Property Finder URL">
      <button class="lookup-btn" id="owner-lookup" type="button">Lookup owner</button>
      <div id="owner-panel"></div>
    </div>
  </aside>

  <script>
    const promptBox   = document.querySelector("#prompt");
    const intent      = document.querySelector("#intent");
    const purpose     = document.querySelector("#purpose");
    const listingScope  = document.querySelector("#listing-scope");
    const listingCustom = document.querySelector("#listing-custom");
    const marketScope   = document.querySelector("#market-scope");
    const marketCustom  = document.querySelector("#market-custom");
    const dualCommunities = document.querySelector("#dual-communities");
    const button      = document.querySelector("#search");
    const clearButton = document.querySelector("#clear-page");
    const quickToggle = document.querySelector("#quick-toggle");
    const quickBar    = document.querySelector("#quick-bar");
    const quickButton = document.querySelector("#quick-query");
    const quickPurpose   = document.querySelector("#quick-purpose");
    const quickBedMin    = document.querySelector("#quick-bed-min");
    const quickBedMax    = document.querySelector("#quick-bed-max");
    const quickPriceMin  = document.querySelector("#quick-price-min");
    const quickPriceMax  = document.querySelector("#quick-price-max");
    const quickCommunity = document.querySelector("#quick-community");
    const quickCategory  = document.querySelector("#quick-category");
    const aiButton       = document.querySelector("#ai-feedback");
    const aiReportButton = document.querySelector("#ai-report");
    const scenarioButtons = document.querySelectorAll(".scenario-button");
    const checkButton = document.querySelector("#check-openai");
    const keyBar      = document.querySelector("#key-bar");
    const aiKeyToggle = document.querySelector("#ai-key-toggle");
    const helpToggle  = document.querySelector("#help-toggle");
    const helpPanel   = document.querySelector("#help-panel");
    const commBtn     = document.querySelector("#comm-btn");
    const commPanel   = document.querySelector("#comm-panel");
    const ownerToggle = document.querySelector("#owner-toggle");
    const ownerDrawer = document.querySelector("#owner-drawer");
    const drawerOverlay = document.querySelector("#drawer-overlay");
    const closeOwnerDrawer = document.querySelector("#close-owner-drawer");
    const ownerButton = document.querySelector("#owner-lookup");
    const tokenBox    = document.querySelector("#openai-token");
    const ownerUrlBox = document.querySelector("#owner-url");
    const summary     = document.querySelector("#summary");
    const response    = document.querySelector("#response");
    const aiPanel     = document.querySelector("#ai-panel");
    const reportToolbar = document.querySelector("#report-toolbar");
    const bestShortlistTitle = document.querySelector("#best-shortlist-title");
    const printReportButton  = document.querySelector("#print-report");
    const ownerPanel  = document.querySelector("#owner-panel");
    const error       = document.querySelector("#error");
    const spinner     = document.querySelector("#spinner");
    const results     = document.querySelector("#results");
    const aboveBudgetSection = document.querySelector("#above-budget-section");
    const aboveBudgetResults = document.querySelector("#above-budget-results");
    const fallbackSection    = document.querySelector("#fallback-section");
    const fallbackResults    = document.querySelector("#fallback-results");
    const status      = document.querySelector("#status");
    let activeApiKey  = "";
    let lastRankContext = null;

    // Sync quick-filter purpose with main purpose
    if (purpose.value === "sale" || purpose.value === "rent") quickPurpose.value = purpose.value;
    purpose.addEventListener("change", () => {
      if (purpose.value === "sale" || purpose.value === "rent") quickPurpose.value = purpose.value;
    });

    // Quick filter toggle
    quickToggle.addEventListener("click", () => {
      quickBar.hidden = !quickBar.hidden;
      quickToggle.classList.toggle("on", !quickBar.hidden);
    });

    // AI key toggle
    aiKeyToggle.addEventListener("click", () => {
      keyBar.hidden = !keyBar.hidden;
      aiKeyToggle.classList.toggle("on", !keyBar.hidden);
      if (!keyBar.hidden) tokenBox.focus();
    });

    function ensureApiKeyVisible() {
      if (!activeApiKey) {
        keyBar.hidden = false;
        aiKeyToggle.classList.add("on");
        tokenBox.focus();
      }
    }

    // Communities popover
    commBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      commPanel.hidden = !commPanel.hidden;
      commBtn.classList.toggle("active", !commPanel.hidden);
    });
    document.addEventListener("click", (e) => {
      if (!commPanel.hidden && !commPanel.contains(e.target) && e.target !== commBtn) {
        commPanel.hidden = true;
        commBtn.classList.remove("active");
      }
    });

    // Owner drawer
    function openOwnerDrawer() {
      ownerDrawer.classList.add("open");
      drawerOverlay.hidden = false;
      ownerToggle.classList.add("on");
    }
    function closeDrawer() {
      ownerDrawer.classList.remove("open");
      drawerOverlay.hidden = true;
      ownerToggle.classList.remove("on");
    }
    ownerToggle.addEventListener("click", () => {
      ownerDrawer.classList.contains("open") ? closeDrawer() : openOwnerDrawer();
    });
    closeOwnerDrawer.addEventListener("click", closeDrawer);
    drawerOverlay.addEventListener("click", closeDrawer);

    // Help panel
    helpToggle.addEventListener("click", () => {
      helpPanel.hidden = !helpPanel.hidden;
      helpToggle.classList.toggle("on", !helpPanel.hidden);
    });

    function selectedListingCommunities() {
      return Array.from(document.querySelectorAll(".listing-community:checked")).map((i) => i.value);
    }
    function selectedMarketCommunities() {
      return Array.from(document.querySelectorAll(".market-community:checked")).map((i) => i.value);
    }

    function activateCommunityScope(scopeEl, customEl) {
      if (scopeEl.value !== "custom") { scopeEl.value = "custom"; customEl.hidden = false; }
    }
    function mirrorCommunitySelection(sourceClass, targetClass, community, checked) {
      if (!dualCommunities.checked) return;
      const target = Array.from(document.querySelectorAll(`.${targetClass}`)).find((i) => i.value === community);
      if (target) target.checked = checked;
    }
    function handleCommunitySelection(event) {
      const checkbox = event.target.closest(".listing-community, .market-community");
      if (!checkbox) return;
      if (checkbox.classList.contains("listing-community")) {
        activateCommunityScope(listingScope, listingCustom);
        mirrorCommunitySelection("listing-community", "market-community", checkbox.value, checkbox.checked);
        if (dualCommunities.checked) activateCommunityScope(marketScope, marketCustom);
      } else {
        activateCommunityScope(marketScope, marketCustom);
        mirrorCommunitySelection("market-community", "listing-community", checkbox.value, checkbox.checked);
        if (dualCommunities.checked) activateCommunityScope(listingScope, listingCustom);
      }
    }
    listingCustom.hidden = listingScope.value !== "custom";
    marketCustom.hidden  = marketScope.value  !== "custom";
    listingScope.addEventListener("change", () => { listingCustom.hidden = listingScope.value !== "custom"; });
    marketScope.addEventListener("change",  () => { marketCustom.hidden  = marketScope.value  !== "custom"; });
    listingCustom.addEventListener("change", handleCommunitySelection);
    marketCustom.addEventListener("change",  handleCommunitySelection);

    function money(value, purposeValue) {
      if (value === null || value === undefined || value === "") return "Unknown";
      const n = Number(value);
      if (!Number.isFinite(n)) return "Unknown";
      return n.toLocaleString() + (purposeValue === "rent" ? " AED/yr" : " AED");
    }
    function metric(label, value) {
      return `<div class="metric"><span>${label}</span><strong>${value || "—"}</strong></div>`;
    }
    function escapeHtml(value) {
      return String(value || "")
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
    }
    function scoreBadgeClass(score) {
      const n = Number(score);
      if (n >= 70) return "high";
      if (n >= 40) return "mid";
      return "low";
    }

    function renderListings(items, purposeValue) {
      return items.map((item) => `
        <article class="listing">
          <div>
            <h2>${item.title || "Untitled listing"}</h2>
            <div class="facts">
              <span class="pill price">${money(item.price, purposeValue)}</span>
              <span class="pill">${item.bedrooms || "?"} bed</span>
              <span class="pill">${item.bathrooms || "?"} bath</span>
              <span class="pill">${item.predicted_community || "Unknown"}</span>
              <span class="pill">${item.predicted_type || "Type unknown"}</span>
              <span class="pill">${item.property_size_sqft || "?"} sqft</span>
            </div>
            ${item.ai_fit_summary ? `<div class="reasons"><strong>Summary:</strong> ${item.ai_fit_summary}</div>` : ""}
            ${item.ai_opportunity_angle ? `<div class="reasons"><strong>Opportunity:</strong> ${item.ai_opportunity_angle}</div>` : ""}
            ${item.ai_strengths ? `<div class="reasons"><strong>Strengths:</strong> ${item.ai_strengths}</div>` : ""}
            ${item.ai_concerns ? `<div class="reasons"><strong>Concerns:</strong> ${item.ai_concerns}</div>` : ""}
            ${item.ai_verify ? `<div class="reasons"><strong>Verify:</strong> ${item.ai_verify}</div>` : ""}
            ${item.match_reasons ? `<div class="reasons">${item.match_reasons}</div>` : ""}
            ${item.outdoor_matches ? `<div class="reasons"><strong>Clues:</strong> ${item.outdoor_matches}</div>` : ""}
            ${item.has_exclusive_warning ? `<div class="exclusive-box"><strong>Exclusive listing:</strong> likely strong agent-owner relationship. Avoid owner call unless you have another clear lead.</div>` : ""}
            ${item.similar_count > 1 ? `
              <div class="similar-box">
                <strong>Similar listing warning:</strong> ${item.similar_count} listings share close price/details. Check photos before treating as the same property.
                ${(item.similar_urls || []).map((url) => `
                  <div class="card-actions">
                    <a href="${url}" target="_blank" rel="noreferrer">${url}</a>
                    <button class="mini copy-link-button" type="button" data-copy="${escapeHtml(url)}">Copy</button>
                    <button class="mini owner-inline-lookup" type="button" data-url="${escapeHtml(url)}">Owner</button>
                  </div>`).join("")}
              </div>` : ""}
            <div class="card-actions">
              <a href="${item.url}" target="_blank" rel="noreferrer">Open listing</a>
              <button class="mini copy-link-button" type="button" data-copy="${escapeHtml(item.url || "")}">Copy link</button>
              <button class="mini owner-inline-lookup" type="button" data-url="${escapeHtml(item.url || "")}">Owner lookup</button>
            </div>
          </div>
          <div class="score"><span class="score-badge ${scoreBadgeClass(item.match_score)}">${item.match_score}</span></div>
        </article>`).join("");
    }

    async function copyText(value, btn) {
      if (!value) return;
      try {
        await navigator.clipboard.writeText(value);
        if (btn) { const t = btn.textContent; btn.textContent = "Copied"; setTimeout(() => { btn.textContent = t; }, 1200); }
      } catch { error.hidden = false; error.textContent = "Could not copy. Select the URL and copy manually."; }
    }

    function handleListingActionClick(event) {
      const copyBtn = event.target.closest(".copy-link-button");
      if (copyBtn) { copyText(copyBtn.dataset.copy || "", copyBtn); return; }
      const ownerBtn = event.target.closest(".owner-inline-lookup");
      if (!ownerBtn) return;
      ownerUrlBox.value = ownerBtn.dataset.url || "";
      openOwnerDrawer();
      lookupOwner();
    }

    function render(data) {
      error.hidden = true;
      spinner.style.display = "none";
      response.hidden = false;
      reportToolbar.hidden = false;
      bestShortlistTitle.hidden = false;
      bestShortlistTitle.textContent = data.report_title || "Best Shortlist";
      status.textContent = `${data.rows_searched} rows searched`;
      summary.innerHTML = [
        metric("Purpose", data.enquiry.purpose),
        metric("Budget", money(data.enquiry.budget, data.enquiry.purpose)),
        metric("Ceiling", money(data.enquiry.stretch_budget, data.enquiry.purpose)),
        metric("Beds", data.enquiry.bedrooms_label),
        metric("Community", data.enquiry.community || "Any"),
      ].join("");
      response.querySelector("div").textContent = data.client_response;
      results.innerHTML = renderListings(data.matches || [], data.enquiry.purpose);
      const watchlist = data.over_budget_matches || [];
      aboveBudgetSection.hidden = watchlist.length === 0;
      aboveBudgetResults.innerHTML = renderListings(watchlist, data.enquiry.purpose);
      const fallback = data.fallback_matches || [];
      fallbackSection.hidden = fallback.length === 0;
      fallbackResults.innerHTML = renderListings(fallback, data.enquiry.purpose);
      if (data.rank_context) lastRankContext = data.rank_context;
    }

    function clearPage() {
      promptBox.value = "";
      ownerUrlBox.value = "";
      summary.innerHTML = "";
      response.hidden = true;
      response.querySelector("div").textContent = "";
      reportToolbar.hidden = true;
      bestShortlistTitle.hidden = true;
      bestShortlistTitle.textContent = "Best Shortlist";
      aiPanel.hidden = true;
      aiPanel.innerHTML = "";
      ownerPanel.innerHTML = "";
      error.hidden = true;
      error.textContent = "";
      results.innerHTML = "";
      aboveBudgetSection.hidden = true;
      aboveBudgetResults.innerHTML = "";
      fallbackSection.hidden = true;
      fallbackResults.innerHTML = "";
      spinner.style.display = "none";
      status.textContent = activeApiKey ? "API active" : "Local data only";
      lastRankContext = null;
      promptBox.focus();
    }

    async function runSearch() {
      const text = promptBox.value.trim();
      if (!text) { promptBox.focus(); return; }
      button.disabled = true;
      button.textContent = "Finding…";
      response.hidden = true;
      reportToolbar.hidden = true;
      bestShortlistTitle.hidden = true;
      error.hidden = true;
      results.innerHTML = "";
      aboveBudgetSection.hidden = true;
      aboveBudgetResults.innerHTML = "";
      fallbackSection.hidden = true;
      fallbackResults.innerHTML = "";
      spinner.style.display = "block";
      try {
        const res = await fetch("/api/match", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: text,
            purpose: purpose.value,
            intent: intent.value,
            listing_scope: listingScope.value,
            listing_communities: selectedListingCommunities(),
            market_scope: marketScope.value,
            market_communities: selectedMarketCommunities(),
            limit: 20
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Search failed");
        render(data);
      } catch (err) {
        error.hidden = false;
        error.textContent = err.message;
      } finally {
        spinner.style.display = "none";
        button.disabled = false;
        button.textContent = "Find";
      }
    }

    async function runQuickQuery() {
      quickButton.disabled = true;
      quickButton.textContent = "Filtering…";
      error.hidden = true;
      aiPanel.hidden = true;
      aboveBudgetSection.hidden = true;
      fallbackSection.hidden = true;
      aboveBudgetResults.innerHTML = "";
      fallbackResults.innerHTML = "";
      spinner.style.display = "block";
      try {
        const res = await fetch("/api/quick-query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            purpose: quickPurpose.value,
            min_beds: quickBedMin.value,
            max_beds: quickBedMax.value,
            min_price: quickPriceMin.value,
            max_price: quickPriceMax.value,
            community: quickCommunity.value,
            category: quickCategory.value
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Quick query failed");
        render(data);
      } catch (err) {
        error.hidden = false;
        error.textContent = err.message;
      } finally {
        spinner.style.display = "none";
        quickButton.disabled = false;
        quickButton.textContent = "Filter";
      }
    }

    async function checkOpenAiKey() {
      const token = tokenBox.value.trim();
      if (!token) { error.hidden = false; error.textContent = "Add an OpenAI API key first."; tokenBox.focus(); return; }
      checkButton.disabled = true;
      checkButton.textContent = "Checking…";
      error.hidden = true;
      aiPanel.hidden = false;
      aiPanel.textContent = "Checking OpenAI connection...";
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);
      try {
        const res = await fetch("/api/check-openai", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key: token }),
          signal: controller.signal
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "OpenAI check failed");
        activeApiKey = token;
        tokenBox.hidden = true;
        tokenBox.value = "";
        checkButton.classList.add("on");
        checkButton.textContent = "Key active";
        keyBar.classList.add("ready");
        aiKeyToggle.classList.add("on");
        aiKeyToggle.textContent = "AI key ✓";
        aiPanel.textContent = data.message || "OpenAI connection is ready.";
      } catch (err) {
        activeApiKey = "";
        keyBar.classList.remove("ready");
        error.hidden = false;
        error.textContent = err.name === "AbortError" ? "OpenAI check timed out after 30 seconds." : err.message;
        aiPanel.hidden = true;
      } finally {
        clearTimeout(timeoutId);
        checkButton.disabled = false;
        if (!activeApiKey) checkButton.textContent = "Check key";
      }
    }

    function renderOwnerLookup(data) {
      if (!data.found) {
        ownerPanel.innerHTML = `<div style="color:var(--muted);font-size:13px">${data.message || "No matching owner lead found for this URL."}</div>`;
        return;
      }
      const lead = data.lead || {};
      const urls = (data.propertyfinder_urls || []).map((url) => `
        <div class="card-actions" style="margin-top:6px">
          <a href="${url}" target="_blank" rel="noreferrer" style="font-size:12px;overflow-wrap:anywhere">${url}</a>
          <button class="mini copy-link-button" type="button" data-copy="${escapeHtml(url)}">Copy</button>
        </div>`).join("");
      ownerPanel.innerHTML = `
        <div class="owner-result">
          <div><strong>Owners:</strong> ${lead.owners || "Unknown"}</div>
          <div><strong>Numbers:</strong> ${lead.numbers || "Unknown"}</div>
          <div><strong>Property:</strong> ${lead.property || "Unknown"}</div>
          <div><strong>Beds:</strong> ${lead.beds || "?"} &nbsp; <strong>Type:</strong> ${lead.type || "?"}</div>
          <div><strong>GFA:</strong> ${lead.gfa || "?"} &nbsp; <strong>BUA:</strong> ${lead.bua || "?"}</div>
          <div><strong>Asking:</strong> ${lead.asking || "?"} &nbsp; <strong>Rental:</strong> ${lead.rental || "?"}</div>
          ${lead.notes ? `<div><strong>Notes:</strong> ${lead.notes}</div>` : ""}
          <div style="margin-top:4px;font-size:11px;color:var(--muted)">Matched by: ${data.match_type || "URL"}</div>
          ${urls}
        </div>`;
    }
    ownerPanel.addEventListener("click", (event) => {
      const copyBtn = event.target.closest(".copy-link-button");
      if (copyBtn) copyText(copyBtn.dataset.copy || "", copyBtn);
    });

    async function lookupOwner() {
      const url = ownerUrlBox.value.trim();
      if (!url) { ownerUrlBox.focus(); return; }
      ownerButton.disabled = true;
      ownerButton.textContent = "Looking up…";
      ownerPanel.innerHTML = "";
      try {
        const res = await fetch("/api/owner-lookup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Owner lookup failed");
        renderOwnerLookup(data);
      } catch (err) {
        ownerPanel.innerHTML = `<div class="error">${escapeHtml(err.message)}</div>`;
      } finally {
        ownerButton.disabled = false;
        ownerButton.textContent = "Lookup owner";
      }
    }

    async function runAiFeedback() {
      return runAiReport({ buttonElement: aiButton, buttonText: "General", endpoint: "/api/ai-feedback", progressStart: "Shortlisting your database..." });
    }
    async function runScenario(scenario, buttonElement) {
      const labels = { best_value: "Best value", budget_reality: "Budget reality", fallback: "Fallback", negotiation: "Negotiation", listing_opportunity: "Listing opp.", upgrade_potential: "Upgrade", move_in_ready: "Move-in ready" };
      const starts = { best_value: "Building value shortlist...", budget_reality: "Building budget reality case...", fallback: "Building premium fallback shortlist...", negotiation: "Building negotiation case...", listing_opportunity: "Finding listing opportunities...", upgrade_potential: "Finding upgrade potential...", move_in_ready: "Finding move-in ready options..." };
      return runAiReport({ buttonElement, buttonText: labels[scenario] || "Scenario", endpoint: "/api/ai-scenario-rank", progressStart: starts[scenario] || "Building scenario report...", scenario });
    }
    async function runBuildReport() {
      if (!lastRankContext) { error.hidden = false; error.textContent = "Rank a scenario first, then build the report."; return; }
      return runAiReport({ buttonElement: aiReportButton, buttonText: "Build report", endpoint: "/api/ai-scenario-report", progressStart: "Building report from ranked shortlist...", scenario: lastRankContext.scenario, rankedUrls: lastRankContext.ranked_urls });
    }

    async function runAiReport({ buttonElement, buttonText, endpoint, progressStart, scenario, rankedUrls }) {
      const text = promptBox.value.trim();
      const token = activeApiKey || tokenBox.value.trim();
      if (!text) { promptBox.focus(); return; }
      if (!token) { error.hidden = false; error.textContent = "Add and check an OpenAI API key first (AI key button above)."; return; }
      if (buttonElement) { buttonElement.disabled = true; buttonElement.textContent = "Thinking…"; }
      error.hidden = true;
      aiPanel.hidden = false;
      const messages = [progressStart, "Adding relevant DXB market comps...", "Sending small batches to OpenAI...", "Ranking shortlist batches...", "Comparing batch winners with market comps...", "Building final enquiry report...", "Still working. This can take a couple of minutes..."];
      let msgIdx = 0;
      aiPanel.textContent = messages[0];
      const progressId = setInterval(() => { msgIdx = Math.min(msgIdx + 1, messages.length - 1); aiPanel.textContent = messages[msgIdx]; }, 7000);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 300000);
      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: text, purpose: purpose.value, intent: intent.value, listing_scope: listingScope.value, listing_communities: selectedListingCommunities(), market_scope: marketScope.value, market_communities: selectedMarketCommunities(), api_key: token, limit: 10, scenario, ranked_urls: rankedUrls || [] }),
          signal: controller.signal
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "AI feedback failed");
        render(data);
        aiPanel.hidden = false;
        aiPanel.innerHTML = `
          <section class="report-section"><h2>Market Read</h2><pre>${escapeHtml(data.ai.market_read || "No market read returned.")}</pre></section>
          <section class="report-section"><h2>Conclusion</h2><pre>${escapeHtml(data.ai.client_response || "No conclusion returned.")}</pre></section>`;
      } catch (err) {
        error.hidden = false;
        error.textContent = err.name === "AbortError" ? "AI feedback timed out after 5 minutes. Try a narrower prompt." : err.message;
        aiPanel.hidden = true;
      } finally {
        clearInterval(progressId);
        clearTimeout(timeoutId);
        if (buttonElement) { buttonElement.disabled = false; buttonElement.textContent = buttonText; }
      }
    }

    button.addEventListener("click", runSearch);
    quickButton.addEventListener("click", runQuickQuery);
    clearButton.addEventListener("click", clearPage);
    printReportButton.addEventListener("click", () => window.print());
    checkButton.addEventListener("click", checkOpenAiKey);
    ownerButton.addEventListener("click", lookupOwner);
    ownerUrlBox.addEventListener("keydown", (e) => { if (e.key === "Enter") lookupOwner(); });
    results.addEventListener("click", handleListingActionClick);
    aboveBudgetResults.addEventListener("click", handleListingActionClick);
    fallbackResults.addEventListener("click", handleListingActionClick);
    aiButton.addEventListener("click", () => { ensureApiKeyVisible(); runAiFeedback(); });
    aiReportButton.addEventListener("click", () => { ensureApiKeyVisible(); runBuildReport(); });
    scenarioButtons.forEach((btn) => btn.addEventListener("click", () => { ensureApiKeyVisible(); runScenario(btn.dataset.scenario, btn); }));
    promptBox.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runSearch(); });
  </script>
</body>
</html>
"""


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

        if path not in {"/api/match", "/api/quick-query", "/api/ai-feedback", "/api/ai-fallback", "/api/ai-scenario", "/api/ai-scenario-rank", "/api/ai-scenario-report", "/api/check-openai", "/api/owner-lookup"}:
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
