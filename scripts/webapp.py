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
      --wash: #f7f8f5;
      --panel: #ffffff;
      --accent: #0b6b57;
      --accent-2: #b8742a;
      --danger: #9b2d20;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--wash);
    }
    main {
      width: min(1120px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 28px 0 44px;
    }
    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0;
      font-size: 28px;
      line-height: 1.1;
      font-weight: 700;
      letter-spacing: 0;
    }
    .sub {
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
    }
    .status {
      color: var(--muted);
      font-size: 13px;
      text-align: right;
      white-space: nowrap;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .topbar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 12px;
    }
    .utility-row {
      display: flex;
      justify-content: flex-start;
      margin: 0 0 8px;
    }
    .icon-button {
      width: 40px;
      min-width: 40px;
      padding: 0;
      border-color: var(--line);
      background: #fff;
      color: var(--ink);
      font-size: 18px;
    }
    .scenario-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 12px;
    }
    .box-title {
      width: 100%;
      margin: 0 0 2px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .scenario-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      width: 100%;
    }
    .scenario-report-row {
      border-top: 1px solid var(--line);
      padding-top: 8px;
      margin-top: 2px;
      width: 100%;
      display: flex;
      justify-content: stretch;
    }
    .scenario-report-row .report-button {
      width: 100%;
    }
    .token-input {
      min-height: 40px;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 12px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }
    .ai-button {
      min-width: 132px;
      border-color: var(--accent-2);
      background: var(--accent-2);
    }
    .general-ai-button {
      border-color: var(--accent-2);
      background: #fffaf2;
      color: #7a4a16;
    }
    .report-button {
      min-width: 124px;
      border-color: #264f7a;
      background: #264f7a;
      color: #fff;
    }
    .check-button {
      min-width: 96px;
      border-color: var(--line);
      background: #fff;
      color: var(--ink);
    }
    .check-button.api-active {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    .check-button.api-inactive {
      border-color: var(--danger);
      background: #fff;
      color: var(--danger);
    }
    .topbar.api-ready {
      border-color: var(--accent);
      background: #f1faf6;
      box-shadow: 0 0 0 2px rgba(34, 122, 82, 0.08);
    }
    .topbar-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .help-button {
      border-color: var(--line);
      background: #fff;
      color: var(--ink);
    }
    .search {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      margin-bottom: 18px;
    }
    .quick-query {
      background: #fbfcfa;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      display: grid;
      grid-template-columns: repeat(8, minmax(88px, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }
    .quick-query input,
    .quick-query select {
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
      background: #fff;
      min-width: 0;
    }
    .quick-query button {
      min-height: 38px;
      white-space: nowrap;
    }
    .query-panel {
      min-width: 0;
    }
    .query-title {
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .lookup {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      margin-bottom: 18px;
    }
    .url-input {
      min-height: 40px;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 12px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }
    textarea {
      min-height: 92px;
      resize: vertical;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }
    textarea:focus {
      outline: 2px solid rgba(11, 107, 87, 0.18);
      border-color: var(--accent);
    }
    .controls {
      display: grid;
      gap: 10px;
      align-content: start;
      min-width: 132px;
    }
    .market-controls {
      grid-column: 1 / -1;
      border-top: 1px solid var(--line);
      padding-top: 10px;
      display: grid;
      gap: 8px;
    }
    .dual-control {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }
    .dual-control input {
      margin: 0;
    }
    .market-custom {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(92px, 1fr));
      gap: 6px 10px;
      font-size: 13px;
      color: var(--muted);
    }
    .market-custom label {
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    .market-custom input {
      margin: 0;
    }
    select, button {
      min-height: 40px;
      border-radius: 6px;
      border: 1px solid var(--line);
      padding: 0 12px;
      font: inherit;
      background: #fff;
      color: var(--ink);
    }
    button {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      font-weight: 700;
    }
    button:disabled {
      opacity: 0.62;
      cursor: wait;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 12px;
      min-height: 70px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
    }
    .metric strong {
      font-size: 18px;
      line-height: 1.15;
    }
    .response {
      white-space: pre-wrap;
      border-left: 4px solid var(--accent-2);
      background: #fffaf2;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #332416;
    }
    .ai-panel {
      border-left: 4px solid var(--accent);
      background: #f1faf6;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #14342c;
    }
    .ai-panel h2 {
      margin: 0 0 8px;
      font-size: 17px;
      letter-spacing: 0;
    }
    .ai-panel pre {
      margin: 0;
      white-space: pre-wrap;
      font: inherit;
      line-height: 1.45;
    }
    .help-panel {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 14px;
    }
    .help-panel h2 {
      margin: 0 0 10px;
      font-size: 18px;
      letter-spacing: 0;
    }
    .help-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .help-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfa;
      line-height: 1.4;
    }
    .help-card h3 {
      margin: 0 0 6px;
      font-size: 15px;
      letter-spacing: 0;
    }
    .help-card code {
      display: block;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: #23443b;
      background: #eef6f2;
      border-radius: 6px;
      padding: 8px;
      margin: 6px 0;
      font-family: Consolas, monospace;
      font-size: 12px;
    }
    .help-card p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    .help-card ol, .help-card ul {
      margin: 8px 0 0;
      padding-left: 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .help-card.wide {
      grid-column: 1 / -1;
    }
    .report-section {
      margin-bottom: 14px;
    }
    .report-section:last-child {
      margin-bottom: 0;
    }
    .owner-panel {
      border-left: 4px solid var(--accent);
      background: #f1faf6;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #14342c;
      line-height: 1.45;
    }
    .owner-panel h2 {
      margin: 0 0 8px;
      font-size: 17px;
      letter-spacing: 0;
    }
    .url-line {
      display: block;
      overflow-wrap: anywhere;
      font-size: 13px;
      margin-top: 6px;
    }
    .listing-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-top: 8px;
    }
    .mini-button {
      min-height: 32px;
      padding: 0 10px;
      font-size: 13px;
      border-color: var(--line);
      background: #fff;
      color: var(--ink);
    }
    .copy-link-button {
      min-width: 38px;
      font-weight: 700;
    }
    .similar-box {
      border-left: 3px solid var(--accent-2);
      background: #fffaf2;
      padding: 8px 10px;
      margin-top: 8px;
      color: #4a3520;
      font-size: 13px;
      line-height: 1.45;
    }
    .exclusive-box {
      border-left: 3px solid var(--danger);
      background: #fff4f3;
      padding: 8px 10px;
      margin-top: 8px;
      color: #5d1d17;
      font-size: 13px;
      line-height: 1.45;
    }
    .results {
      display: grid;
      gap: 10px;
    }
    .section-title {
      margin: 20px 0 10px;
      font-size: 18px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .watchlist-note {
      color: var(--muted);
      font-size: 13px;
      margin: -4px 0 10px;
    }
    .toolbar {
      display: flex;
      justify-content: flex-end;
      margin: 0 0 10px;
    }
    .secondary-button {
      border-color: var(--line);
      background: #fff;
      color: var(--ink);
    }
    @media print {
      body { background: #fff; }
      .topbar, .search, .lookup, .toolbar, button { display: none !important; }
      main { width: 100%; padding: 0; }
      .listing { break-inside: avoid; }
      .ai-panel, .response, .listing, .metric { background: #fff; }
    }
    .listing {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .listing h2 {
      margin: 0 0 8px;
      font-size: 17px;
      line-height: 1.25;
      letter-spacing: 0;
    }
    .facts {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-bottom: 8px;
    }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 8px;
      font-size: 12px;
      color: var(--muted);
      background: #fbfcfa;
    }
    .reasons {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .score {
      min-width: 92px;
      text-align: right;
    }
    .score strong {
      display: block;
      font-size: 24px;
      color: var(--accent);
    }
    a {
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }
    .error {
      color: var(--danger);
      font-weight: 700;
      margin: 12px 0;
    }
    @media (max-width: 760px) {
      main { width: min(100vw - 18px, 1120px); padding-top: 16px; }
      header { display: block; }
      .status { text-align: left; margin-top: 8px; }
      .topbar { grid-template-columns: 1fr; }
      .scenario-bar { display: flex; }
      .lookup { grid-template-columns: 1fr; }
      .search { grid-template-columns: 1fr; }
      .quick-query { grid-template-columns: 1fr 1fr; }
      .controls { grid-template-columns: 1fr 1fr; min-width: 0; }
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .help-grid { grid-template-columns: 1fr; }
      .listing { grid-template-columns: 1fr; }
      .score { text-align: left; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Property Detector</h1>
        <div class="sub">Search your collected master data with a client-style prompt.</div>
      </div>
      <div class="header-actions">
        <button class="help-button" id="help-toggle" type="button">Help guide</button>
        <div class="status" id="status">Local data only</div>
      </div>
    </header>

    <div class="utility-row">
      <button class="icon-button" id="clear-page" type="button" title="Clear page" aria-label="Clear page">&#129699;</button>
    </div>

    <section class="topbar">
      <input class="token-input" id="openai-token" type="password" autocomplete="off" placeholder="OpenAI API key for AI optimisation (not saved)">
      <div class="topbar-actions">
        <button class="check-button api-inactive" id="check-openai" type="button">Check key</button>
      </div>
    </section>

    <section class="quick-query" aria-label="Quick listing query">
      <select id="quick-purpose">
        <option value="sale">Sale</option>
        <option value="rent">Rent</option>
      </select>
      <input id="quick-bed-min" type="number" min="0" step="1" placeholder="Beds min">
      <input id="quick-bed-max" type="number" min="0" step="1" placeholder="Beds max">
      <input id="quick-price-min" type="text" placeholder="Price min">
      <input id="quick-price-max" type="text" placeholder="Price max">
      <input id="quick-community" type="text" placeholder="Community">
      <select id="quick-category">
        <option value="any">Any type</option>
        <option value="villa">Villa</option>
        <option value="townhouse">Townhouse</option>
      </select>
      <button class="secondary-button" id="quick-query" type="button">Quick query</button>
    </section>

    <form class="search" action="/search" method="get">
      <div class="query-panel">
        <div class="query-title">Query</div>
        <textarea id="prompt" name="prompt" placeholder="after a 3/4 bed in ar2 at 5.5m budget">__PROMPT__</textarea>
      </div>
      <div class="controls">
        <select id="intent" name="intent">
          <option value="auto" __INTENT_AUTO_SELECTED__>Intent: Auto</option>
          <option value="best_value" __INTENT_BEST_VALUE_SELECTED__>Best value</option>
          <option value="move_in_ready" __INTENT_MOVE_IN_READY_SELECTED__>Move-in ready</option>
          <option value="upgrade_potential" __INTENT_UPGRADE_POTENTIAL_SELECTED__>Upgrade potential</option>
          <option value="negotiation" __INTENT_NEGOTIATION_SELECTED__>Negotiation</option>
          <option value="listing_opportunity" __INTENT_LISTING_OPPORTUNITY_SELECTED__>Listing opportunity</option>
        </select>
        <select id="purpose" name="purpose">
          <option value="auto" __AUTO_SELECTED__>Auto</option>
          <option value="sale" __SALE_SELECTED__>Sale</option>
          <option value="rent" __RENT_SELECTED__>Rent</option>
        </select>
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
        <button id="search" type="submit">Find</button>
      </div>
      <div class="market-controls">
        <label class="dual-control">
          <input id="dual-communities" type="checkbox">
          Dual community selection
        </label>
        <div class="watchlist-note">Listing communities</div>
        <div class="market-custom" id="listing-custom">
          __LISTING_COMMUNITY_CHECKBOXES__
        </div>
        <div class="watchlist-note">Comp communities</div>
        <div class="market-custom" id="market-custom">
          __MARKET_COMMUNITY_CHECKBOXES__
        </div>
      </div>
    </form>

    <section class="scenario-bar">
      <div class="box-title">AI Optimisation</div>
      <div class="scenario-actions">
        <button class="secondary-button general-ai-button" id="ai-feedback" type="button">General</button>
        <button class="secondary-button scenario-button" type="button" data-scenario="best_value">Best value</button>
        <button class="secondary-button scenario-button" type="button" data-scenario="budget_reality">Budget reality</button>
        <button class="secondary-button scenario-button" type="button" data-scenario="fallback">Analyse fallback</button>
        <button class="secondary-button scenario-button" type="button" data-scenario="negotiation">Negotiation case</button>
        <button class="secondary-button scenario-button" type="button" data-scenario="listing_opportunity">Listing opportunity</button>
        <button class="secondary-button scenario-button" type="button" data-scenario="upgrade_potential">Upgrade potential</button>
        <button class="secondary-button scenario-button" type="button" data-scenario="move_in_ready">Move-in ready</button>
      </div>
      <div class="scenario-report-row">
        <button class="report-button" id="ai-report" type="button">Build report</button>
      </div>
    </section>

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

    <section class="lookup">
      <input class="url-input" id="owner-url" type="url" placeholder="Paste Property Finder URL to lookup owner">
      <button id="owner-lookup" type="button">Lookup owner</button>
    </section>

    <section class="summary" id="summary">__SUMMARY_HTML__</section>
    <div class="toolbar" id="report-toolbar" __RESPONSE_HIDDEN__>
      <button class="secondary-button" id="print-report" type="button">Save PDF</button>
    </div>
    <section class="response" id="response" __RESPONSE_HIDDEN__>
      <h2 class="section-title">Local Shortlist Summary</h2>
      <div>__RESPONSE_HTML__</div>
    </section>
    <section class="ai-panel" id="ai-panel" hidden></section>
    <h2 class="section-title" id="best-shortlist-title" __RESPONSE_HIDDEN__>Best Shortlist</h2>
    <section class="owner-panel" id="owner-panel" hidden></section>
    <section class="error" id="error" __ERROR_HIDDEN__>__ERROR_HTML__</section>
    <section class="results" id="results">__RESULTS_HTML__</section>
    <section id="above-budget-section" __ABOVE_BUDGET_HIDDEN__>
      <h2 class="section-title">Above Budget Watchlist</h2>
      <div class="watchlist-note">Suitable options above the search ceiling, shown separately for market context.</div>
      <div class="results" id="above-budget-results">__ABOVE_BUDGET_HTML__</div>
    </section>
    <section id="fallback-section" hidden>
      <h2 class="section-title">Fallback Alternatives</h2>
      <div class="watchlist-note">Premium compromise options first, then budget alternatives if the client will not increase to the main product type.</div>
      <div class="results" id="fallback-results"></div>
    </section>
  </main>

  <script>
    const promptBox = document.querySelector("#prompt");
    const intent = document.querySelector("#intent");
    const purpose = document.querySelector("#purpose");
    const listingScope = document.querySelector("#listing-scope");
    const listingCustom = document.querySelector("#listing-custom");
    const marketScope = document.querySelector("#market-scope");
    const marketCustom = document.querySelector("#market-custom");
    const dualCommunities = document.querySelector("#dual-communities");
    const button = document.querySelector("#search");
    const clearButton = document.querySelector("#clear-page");
    const quickButton = document.querySelector("#quick-query");
    const quickPurpose = document.querySelector("#quick-purpose");
    const quickBedMin = document.querySelector("#quick-bed-min");
    const quickBedMax = document.querySelector("#quick-bed-max");
    const quickPriceMin = document.querySelector("#quick-price-min");
    const quickPriceMax = document.querySelector("#quick-price-max");
    const quickCommunity = document.querySelector("#quick-community");
    const quickCategory = document.querySelector("#quick-category");
    const aiButton = document.querySelector("#ai-feedback");
    const aiReportButton = document.querySelector("#ai-report");
    const scenarioButtons = document.querySelectorAll(".scenario-button");
    const checkButton = document.querySelector("#check-openai");
    const topbar = document.querySelector(".topbar");
    const helpToggle = document.querySelector("#help-toggle");
    const helpPanel = document.querySelector("#help-panel");
    const ownerButton = document.querySelector("#owner-lookup");
    const tokenBox = document.querySelector("#openai-token");
    const ownerUrlBox = document.querySelector("#owner-url");
    const summary = document.querySelector("#summary");
    const response = document.querySelector("#response");
    const aiPanel = document.querySelector("#ai-panel");
    const reportToolbar = document.querySelector("#report-toolbar");
    const bestShortlistTitle = document.querySelector("#best-shortlist-title");
    const printReportButton = document.querySelector("#print-report");
    const ownerPanel = document.querySelector("#owner-panel");
    const error = document.querySelector("#error");
    const results = document.querySelector("#results");
    const aboveBudgetSection = document.querySelector("#above-budget-section");
    const aboveBudgetResults = document.querySelector("#above-budget-results");
    const fallbackSection = document.querySelector("#fallback-section");
    const fallbackResults = document.querySelector("#fallback-results");
    const status = document.querySelector("#status");
    let activeApiKey = "";
    let lastRankContext = null;
    if (purpose.value === "sale" || purpose.value === "rent") quickPurpose.value = purpose.value;
    purpose.addEventListener("change", () => {
      if (purpose.value === "sale" || purpose.value === "rent") quickPurpose.value = purpose.value;
    });

    function selectedListingCommunities() {
      return Array.from(document.querySelectorAll(".listing-community:checked")).map((input) => input.value);
    }

    function selectedMarketCommunities() {
      return Array.from(document.querySelectorAll(".market-community:checked")).map((input) => input.value);
    }

    function updateListingCustomVisibility() {
      listingCustom.hidden = listingScope.value !== "custom";
    }

    function updateMarketCustomVisibility() {
      marketCustom.hidden = marketScope.value !== "custom";
    }

    function activateCommunityScope(scopeElement, customElement) {
      if (scopeElement.value !== "custom") {
        scopeElement.value = "custom";
        customElement.hidden = false;
      }
    }

    function mirrorCommunitySelection(sourceClass, targetClass, community, checked) {
      if (!dualCommunities.checked) return;
      const target = Array.from(document.querySelectorAll(`.${targetClass}`)).find((input) => input.value === community);
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

    updateListingCustomVisibility();
    updateMarketCustomVisibility();
    listingScope.addEventListener("change", updateListingCustomVisibility);
    marketScope.addEventListener("change", updateMarketCustomVisibility);
    listingCustom.addEventListener("change", handleCommunitySelection);
    marketCustom.addEventListener("change", handleCommunitySelection);

    function money(value, purposeValue) {
      if (value === null || value === undefined || value === "") return "Unknown";
      const number = Number(value);
      if (!Number.isFinite(number)) return "Unknown";
      const suffix = purposeValue === "rent" ? " AED/year" : " AED";
      return number.toLocaleString() + suffix;
    }

    function metric(label, value) {
      return `<div class="metric"><span>${label}</span><strong>${value || "Unknown"}</strong></div>`;
    }

    function escapeHtml(value) {
      return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function renderListings(items, purposeValue) {
      return items.map((item) => `
        <article class="listing">
          <div>
            <h2>${item.title || "Untitled listing"}</h2>
            <div class="facts">
              <span class="pill">${money(item.price, purposeValue)}</span>
              <span class="pill">${item.bedrooms || "?"} bed</span>
              <span class="pill">${item.bathrooms || "?"} bath</span>
              <span class="pill">${item.predicted_community || "Unknown"}</span>
              <span class="pill">${item.predicted_type || "Type unknown"}</span>
              ${item.ai_score ? `<span class="pill">AI ${item.ai_score}/100</span>` : ""}
              <span class="pill">${item.property_size_sqft || "?"} sqft</span>
            </div>
            <div class="reasons">${item.ai_fit_summary ? "AI: " + item.ai_fit_summary : ""}</div>
            <div class="reasons">${item.ai_opportunity_angle ? "Opportunity: " + item.ai_opportunity_angle : ""}</div>
            <div class="reasons">${item.ai_strengths ? "Strengths: " + item.ai_strengths : ""}</div>
            <div class="reasons">${item.ai_concerns ? "Concerns: " + item.ai_concerns : ""}</div>
            <div class="reasons">${item.ai_verify ? "Verify: " + item.ai_verify : ""}</div>
            <div class="reasons">${item.match_reasons || ""}</div>
            <div class="reasons">${item.outdoor_matches ? "Clues: " + item.outdoor_matches : ""}</div>
            ${item.has_exclusive_warning ? `
              <div class="exclusive-box">
                <strong>Exclusive listing:</strong> likely strong agent-owner relationship. Avoid owner call unless you have another clear lead.
              </div>
            ` : ""}
            ${item.similar_count > 1 ? `
              <div class="similar-box">
                <strong>Similar listing warning:</strong> ${item.similar_count} listings share close price/details. Check photos before treating as the same property.
                ${(item.similar_urls || []).map((url) => `
                  <div class="listing-actions">
                    <a href="${url}" target="_blank" rel="noreferrer">${url}</a>
                    <button class="mini-button copy-link-button" type="button" data-copy="${escapeHtml(url)}">Copy</button>
                    <button class="mini-button owner-inline-lookup" type="button" data-url="${escapeHtml(url)}">Lookup owner</button>
                  </div>
                `).join("")}
              </div>
            ` : ""}
            <div class="listing-actions">
              <a href="${item.url}" target="_blank" rel="noreferrer">Open listing</a>
              <button class="mini-button copy-link-button" type="button" data-copy="${escapeHtml(item.url || "")}">Copy link</button>
              <button class="mini-button owner-inline-lookup" type="button" data-url="${escapeHtml(item.url || "")}">Lookup owner</button>
            </div>
            <a class="url-line" href="${item.url}" target="_blank" rel="noreferrer">${item.url || ""}</a>
          </div>
          <div class="score"><span>Score</span><strong>${item.match_score}</strong></div>
        </article>
      `).join("");
    }

    async function copyText(value, buttonElement) {
      if (!value) return;
      try {
        await navigator.clipboard.writeText(value);
        if (buttonElement) {
          const oldText = buttonElement.textContent;
          buttonElement.textContent = "Copied";
          setTimeout(() => { buttonElement.textContent = oldText; }, 1200);
        }
      } catch (err) {
        error.hidden = false;
        error.textContent = "Could not copy link. Select the URL and copy it manually.";
      }
    }

    function handleListingActionClick(event) {
      const copyButton = event.target.closest(".copy-link-button");
      if (copyButton) {
        copyText(copyButton.dataset.copy || "", copyButton);
        return;
      }

      const lookupButton = event.target.closest(".owner-inline-lookup");
      if (!lookupButton) return;
      ownerUrlBox.value = lookupButton.dataset.url || "";
      lookupOwner();
    }

    function render(data) {
      error.hidden = true;
      response.hidden = false;
      reportToolbar.hidden = false;
      bestShortlistTitle.hidden = false;
      bestShortlistTitle.textContent = data.report_title || "Best Shortlist";
      status.textContent = `${data.rows_searched} rows searched`;
      summary.innerHTML = [
        metric("Purpose", data.enquiry.purpose),
        metric("Budget", money(data.enquiry.budget, data.enquiry.purpose)),
        metric("Budget floor", money(data.enquiry.budget_floor, data.enquiry.purpose)),
        metric("Search ceiling", money(data.enquiry.stretch_budget, data.enquiry.purpose)),
        metric("Beds", data.enquiry.bedrooms_label),
        metric("Community", data.enquiry.community || "Any")
      ].join("");
      response.querySelector("div").textContent = data.client_response;
      results.innerHTML = renderListings(data.matches || [], data.enquiry.purpose);
      const watchlist = data.over_budget_matches || [];
      aboveBudgetSection.hidden = watchlist.length === 0;
      aboveBudgetResults.innerHTML = renderListings(watchlist, data.enquiry.purpose);
      const fallback = data.fallback_matches || [];
      fallbackSection.hidden = fallback.length === 0;
      fallbackResults.innerHTML = renderListings(fallback, data.enquiry.purpose);
      if (data.rank_context) {
        lastRankContext = data.rank_context;
      }
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
      ownerPanel.hidden = true;
      ownerPanel.innerHTML = "";
      error.hidden = true;
      error.textContent = "";
      results.innerHTML = "";
      aboveBudgetSection.hidden = true;
      aboveBudgetResults.innerHTML = "";
      fallbackSection.hidden = true;
      fallbackResults.innerHTML = "";
      status.textContent = activeApiKey ? "API active" : "Local data only";
      lastRankContext = null;
      promptBox.focus();
    }

    async function runSearch() {
      const text = promptBox.value.trim();
      if (!text) {
        promptBox.focus();
        return;
      }
      button.disabled = true;
      button.textContent = "Finding";
      response.hidden = true;
      reportToolbar.hidden = true;
      bestShortlistTitle.hidden = true;
      error.hidden = true;
      results.innerHTML = "";
      aboveBudgetSection.hidden = true;
      aboveBudgetResults.innerHTML = "";
      fallbackSection.hidden = true;
      fallbackResults.innerHTML = "";
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
        button.disabled = false;
        button.textContent = "Find";
      }
    }

    button.addEventListener("click", (event) => {
      event.preventDefault();
      runSearch();
    });
    async function runQuickQuery() {
      quickButton.disabled = true;
      quickButton.textContent = "Checking";
      error.hidden = true;
      aiPanel.hidden = true;
      aboveBudgetSection.hidden = true;
      fallbackSection.hidden = true;
      aboveBudgetResults.innerHTML = "";
      fallbackResults.innerHTML = "";
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
        quickButton.disabled = false;
        quickButton.textContent = "Quick query";
      }
    }
    quickButton.addEventListener("click", runQuickQuery);
    clearButton.addEventListener("click", clearPage);
    printReportButton.addEventListener("click", () => window.print());
    results.addEventListener("click", handleListingActionClick);
    aboveBudgetResults.addEventListener("click", handleListingActionClick);
    fallbackResults.addEventListener("click", handleListingActionClick);
    async function checkOpenAiKey() {
      const token = tokenBox.value.trim();
      if (!token) {
        error.hidden = false;
        error.textContent = "Add an OpenAI API key first.";
        tokenBox.focus();
        return;
      }
      checkButton.disabled = true;
      checkButton.textContent = "Checking";
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
        checkButton.classList.remove("api-inactive");
        checkButton.classList.add("api-active");
        checkButton.textContent = "API active";
        topbar.classList.add("api-ready");
        aiPanel.textContent = data.message || "OpenAI connection is ready.";
      } catch (err) {
        activeApiKey = "";
        checkButton.classList.remove("api-active");
        checkButton.classList.add("api-inactive");
        topbar.classList.remove("api-ready");
        error.hidden = false;
        error.textContent = err.name === "AbortError"
          ? "OpenAI check timed out after 30 seconds."
          : err.message;
        aiPanel.hidden = true;
      } finally {
        clearTimeout(timeoutId);
        checkButton.disabled = false;
        checkButton.textContent = activeApiKey ? "API active" : "Check key";
      }
    }
    checkButton.addEventListener("click", checkOpenAiKey);
    function renderOwnerLookup(data) {
      ownerPanel.hidden = false;
      if (!data.found) {
        ownerPanel.innerHTML = `<h2>No owner match found</h2><div>${data.message || "No matching owner lead was found for this URL."}</div>`;
        return;
      }
      const lead = data.lead || {};
      const urls = (data.propertyfinder_urls || []).map((url) => `
        <div class="listing-actions">
          <a class="url-line" href="${url}" target="_blank" rel="noreferrer">${url}</a>
          <button class="mini-button copy-link-button" type="button" data-copy="${escapeHtml(url)}">Copy</button>
        </div>
      `).join("");
      ownerPanel.innerHTML = `
        <h2>Owner found</h2>
        <div><strong>Owners:</strong> ${lead.owners || "Unknown"}</div>
        <div><strong>Numbers:</strong> ${lead.numbers || "Unknown"}</div>
        <div><strong>Property:</strong> ${lead.property || "Unknown"}</div>
        <div><strong>Beds:</strong> ${lead.beds || "Unknown"} <strong>Type:</strong> ${lead.type || "Unknown"}</div>
        <div><strong>GFA:</strong> ${lead.gfa || "Unknown"} <strong>BUA:</strong> ${lead.bua || "Unknown"}</div>
        <div><strong>Asking:</strong> ${lead.asking || "Unknown"} <strong>Rental:</strong> ${lead.rental || "Unknown"}</div>
        <div><strong>Notes:</strong> ${lead.notes || ""}</div>
        <div><strong>Matched by:</strong> ${data.match_type || "URL"}</div>
        ${urls}
      `;
    }
    ownerPanel.addEventListener("click", (event) => {
      const copyButton = event.target.closest(".copy-link-button");
      if (!copyButton) return;
      copyText(copyButton.dataset.copy || "", copyButton);
    });
    async function lookupOwner() {
      const url = ownerUrlBox.value.trim();
      if (!url) {
        error.hidden = false;
        error.textContent = "Paste a Property Finder URL first.";
        ownerUrlBox.focus();
        return;
      }
      ownerButton.disabled = true;
      ownerButton.textContent = "Looking";
      error.hidden = true;
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
        error.hidden = false;
        error.textContent = err.message;
        ownerPanel.hidden = true;
      } finally {
        ownerButton.disabled = false;
        ownerButton.textContent = "Lookup owner";
      }
    }
    ownerButton.addEventListener("click", lookupOwner);
    ownerUrlBox.addEventListener("keydown", (event) => {
      if (event.key === "Enter") lookupOwner();
    });
    async function runAiFeedback() {
      return runAiReport({
        buttonElement: aiButton,
        buttonText: "General",
        endpoint: "/api/ai-feedback",
        progressStart: "Shortlisting your database..."
      });
    }

    async function runScenario(scenario, buttonElement) {
      const labels = {
        best_value: "Best value",
        budget_reality: "Budget reality",
        fallback: "Analyse fallback",
        negotiation: "Negotiation case",
        listing_opportunity: "Listing opportunity",
        upgrade_potential: "Upgrade potential",
        move_in_ready: "Move-in ready"
      };
      const starts = {
        best_value: "Building value shortlist...",
        budget_reality: "Building budget reality case...",
        fallback: "Building premium fallback shortlist...",
        negotiation: "Building negotiation case...",
        listing_opportunity: "Finding listing opportunities...",
        upgrade_potential: "Finding upgrade potential...",
        move_in_ready: "Finding move-in ready options..."
      };
      return runAiReport({
        buttonElement,
        buttonText: labels[scenario] || "Scenario",
        endpoint: "/api/ai-scenario-rank",
        progressStart: starts[scenario] || "Building scenario report...",
        scenario
      });
    }

    async function runBuildReport() {
      if (!lastRankContext) {
        error.hidden = false;
        error.textContent = "Rank a scenario first, then build the report.";
        return;
      }
      return runAiReport({
        buttonElement: aiReportButton,
        buttonText: "Build report",
        endpoint: "/api/ai-scenario-report",
        progressStart: "Building report from ranked shortlist...",
        scenario: lastRankContext.scenario,
        rankedUrls: lastRankContext.ranked_urls
      });
    }

    async function runAiReport({ buttonElement, buttonText, endpoint, progressStart, scenario, rankedUrls }) {
      const text = promptBox.value.trim();
      const token = activeApiKey || tokenBox.value.trim();
      if (!text) {
        promptBox.focus();
        return;
      }
      if (!token) {
        error.hidden = false;
        error.textContent = "Add and check an OpenAI API key first. It is only kept in this browser session.";
        if (!tokenBox.hidden) tokenBox.focus();
        return;
      }
      if (buttonElement) {
        buttonElement.disabled = true;
        buttonElement.textContent = "Thinking";
      }
      error.hidden = true;
      aiPanel.hidden = false;
      const progressMessages = [
        progressStart,
        "Adding relevant DXB market comps...",
        "Sending small batches to OpenAI...",
        "Ranking shortlist batches...",
        "Comparing batch winners with market comps...",
        "Building final enquiry report...",
        "Still working. This can take a couple of minutes..."
      ];
      let progressIndex = 0;
      aiPanel.textContent = progressMessages[progressIndex];
      const progressId = setInterval(() => {
        progressIndex = Math.min(progressIndex + 1, progressMessages.length - 1);
        aiPanel.textContent = progressMessages[progressIndex];
      }, 7000);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 300000);
      try {
        const res = await fetch(endpoint, {
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
            api_key: token,
            limit: 10,
            scenario,
            ranked_urls: rankedUrls || []
          }),
          signal: controller.signal
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "AI feedback failed");
        render(data);
        aiPanel.hidden = false;
        aiPanel.innerHTML = `
          <section class="report-section">
            <h2>Market Read</h2>
            <pre>${escapeHtml(data.ai.market_read || "No market read returned.")}</pre>
          </section>
          <section class="report-section">
            <h2>Conclusion</h2>
            <pre>${escapeHtml(data.ai.client_response || "No conclusion returned.")}</pre>
          </section>
        `;
      } catch (err) {
        error.hidden = false;
        error.textContent = err.name === "AbortError"
          ? "AI feedback timed out after 5 minutes. Try a narrower prompt."
          : err.message;
        aiPanel.hidden = true;
      } finally {
        clearInterval(progressId);
        clearTimeout(timeoutId);
        if (buttonElement) {
          buttonElement.disabled = false;
          buttonElement.textContent = buttonText;
        }
      }
    }
    aiButton.addEventListener("click", runAiFeedback);
    aiReportButton.addEventListener("click", runBuildReport);
    scenarioButtons.forEach((scenarioButton) => {
      scenarioButton.addEventListener("click", () => runScenario(scenarioButton.dataset.scenario, scenarioButton));
    });
    helpToggle.addEventListener("click", () => {
      helpPanel.hidden = !helpPanel.hidden;
      helpToggle.textContent = helpPanel.hidden ? "Help guide" : "Hide guide";
    });
    promptBox.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") runSearch();
    });
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
            metric_html("Budget floor", money(enquiry.get("budget_floor"), purpose)),
            metric_html("Search ceiling", money(enquiry.get("stretch_budget"), purpose)),
            metric_html("Beds", enquiry.get("bedrooms_label")),
            metric_html("Community", enquiry.get("community") or "Any"),
            metric_html("Intent", enquiry.get("search_intent", "auto").replace("_", " ").title()),
            metric_html("Listings", enquiry.get("listing_scope_mode", "auto").replace("_", " ").title()),
            metric_html("Comps", enquiry.get("market_scope_mode", "auto").replace("_", " ").title()),
        ])
        response_html = escape(result["client_response"])
        response_hidden = ""

        for item in result["matches"]:
            title = escape(str(item.get("title") or "Untitled listing"))
            listing_url = escape(str(item.get("url") or "#"))
            reasons = escape(str(item.get("match_reasons") or ""))
            clues = escape(str(item.get("outdoor_matches") or ""))
            clue_html = f'<div class="reasons">Clues: {clues}</div>' if clues else ""
            results_html += f"""
        <article class="listing">
          <div>
            <h2>{title}</h2>
            <div class="facts">
              <span class="pill">{escape(money(item.get("price"), purpose))}</span>
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
            <div class="listing-actions">
              <a href="{listing_url}" target="_blank" rel="noreferrer">Open listing</a>
              <button class="mini-button copy-link-button" type="button" data-copy="{listing_url}">Copy link</button>
              <button class="mini-button owner-inline-lookup" type="button" data-url="{listing_url}">Lookup owner</button>
            </div>
          </div>
          <div class="score"><span>Score</span><strong>{escape(str(item.get("match_score") or 0))}</strong></div>
        </article>
"""

        over_budget_matches = result.get("over_budget_matches", [])
        above_budget_hidden = "hidden" if not over_budget_matches else ""

        for item in over_budget_matches:
            title = escape(str(item.get("title") or "Untitled listing"))
            listing_url = escape(str(item.get("url") or "#"))
            reasons = escape(str(item.get("match_reasons") or ""))
            clues = escape(str(item.get("outdoor_matches") or ""))
            clue_html = f'<div class="reasons">Clues: {clues}</div>' if clues else ""
            above_budget_html += f"""
        <article class="listing">
          <div>
            <h2>{title}</h2>
            <div class="facts">
              <span class="pill">{escape(money(item.get("price"), purpose))}</span>
              <span class="pill">{escape(str(item.get("bedrooms") or "?"))} bed</span>
              <span class="pill">{escape(str(item.get("bathrooms") or "?"))} bath</span>
              <span class="pill">{escape(str(item.get("predicted_community") or "Unknown"))}</span>
              <span class="pill">{escape(str(item.get("predicted_type") or "Type unknown"))}</span>
              <span class="pill">{escape(str(item.get("property_size_sqft") or "?"))} sqft</span>
            </div>
            <div class="reasons">{reasons}</div>
            {clue_html}
            {f'<div class="exclusive-box"><strong>Exclusive listing:</strong> likely strong agent-owner relationship. Avoid owner call unless you have another clear lead.</div>' if item.get("has_exclusive_warning") else ""}
            <div class="listing-actions">
              <a href="{listing_url}" target="_blank" rel="noreferrer">Open listing</a>
              <button class="mini-button copy-link-button" type="button" data-copy="{listing_url}">Copy link</button>
              <button class="mini-button owner-inline-lookup" type="button" data-url="{listing_url}">Lookup owner</button>
            </div>
          </div>
          <div class="score"><span>Score</span><strong>{escape(str(item.get("match_score") or 0))}</strong></div>
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

