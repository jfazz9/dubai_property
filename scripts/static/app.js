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
    const estimateButton    = document.querySelector("#ai-estimate");
    const estimatePanel     = document.querySelector("#estimate-panel");
    const oppScanButton     = document.querySelector("#opp-scan");
    const oppPurposeFilter  = document.querySelector("#opp-purpose-filter");
    const opportunityPanel  = document.querySelector("#opportunity-panel");
    const aiReportButton = document.querySelector("#ai-report");
    const clientReportButton = document.querySelector("#client-report");
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
    let lastReportContext = null;
    let lastRenderedData = null;

    const wfSteps = [1, 2, 3, 4].map(n => document.querySelector(`#wf-${n}`));
    function setWorkflowStep(doneUpTo) {
      // Update step indicator pills
      wfSteps.forEach((el, i) => {
        if (!el) return;
        el.classList.remove("done", "active");
        if (i < doneUpTo) el.classList.add("done");
        else if (i === doneUpTo) el.classList.add("active");
      });
      // Light up the relevant buttons to show what's ready to use
      promptBox.classList.toggle("prompt-ready", doneUpTo === 0);
      scenarioButtons.forEach(btn => btn.classList.toggle("step-ready", doneUpTo === 1));
      aiReportButton.classList.toggle("step-ready", doneUpTo === 2);
      clientReportButton.classList.toggle("step-ready", doneUpTo === 3);
    }

    // Sync quick-filter purpose with main purpose
    if (purpose.value === "sale" || purpose.value === "rent") quickPurpose.value = purpose.value;
    purpose.addEventListener("change", () => {
      if (purpose.value === "sale" || purpose.value === "rent") quickPurpose.value = purpose.value;
    });

    // Quick filter toggle
    quickToggle.addEventListener("click", () => {
      quickBar.hidden = !quickBar.hidden;
      quickToggle.classList.toggle("on", !quickBar.hidden);
      quickToggle.textContent = quickBar.hidden ? "Quick filter ▾" : "Quick filter ▴";
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
      lastRenderedData = data;
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
      if (data.report_context) lastReportContext = data.report_context;
      // Advance the workflow indicator based on how far we've got
      if (data.report_context) setWorkflowStep(3);       // steps 1-3 done, client report next
      else if (data.rank_context) setWorkflowStep(2);    // steps 1-2 done, build report next
      else setWorkflowStep(1);                           // step 1 done, scenario next
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
      estimatePanel.hidden = true;
      estimatePanel.innerHTML = "";
      opportunityPanel.hidden = true;
      opportunityPanel.innerHTML = "";
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
      lastReportContext = null;
      lastRenderedData = null;
      setWorkflowStep(0);
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

    function approxMoney(value, purposeValue) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "Price to verify";
      if (purposeValue === "rent") {
        const rounded = Math.round(n / 5000) * 5000;
        return `around AED ${Math.round(rounded / 1000)}k/year`;
      }
      if (n >= 1_000_000) {
        const rounded = Math.round(n / 100000) * 100000;
        return `around AED ${(rounded / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
      }
      return `around AED ${Math.round(n / 1000)}k`;
    }

    function approxSize(value) {
      const n = Number(value);
      if (!Number.isFinite(n) || n <= 0) return "size to verify";
      const mid = Math.round(n / 100) * 100;
      const low = Math.max(0, mid - 100);
      const high = mid + 100;
      return `approx. ${low.toLocaleString()}-${high.toLocaleString()} sqft`;
    }

    function clientCategory(item) {
      const text = `${item.title || ""} ${item.url || ""}`.toLowerCase();
      if (text.includes("townhouse") || text.includes("townhouse-for-")) return "townhouse";
      if (text.includes("villa") || text.includes("villa-for-")) return "villa";
      return "home";
    }

    function clientAvailability(item) {
      const text = [
        item.title,
        item.ai_fit_summary,
        item.ai_strengths,
        item.match_reasons,
      ].join(" ").toLowerCase();
      if (text.includes("vacant on transfer") || /\bvot\b/.test(text)) return "vacant on transfer / timing to verify";
      if (text.includes("ready to move") || text.includes("available now") || text.includes("vacant now") || text.includes("keys")) return "vacant / near-immediate availability";
      if (text.includes("vacant") || text.includes("available")) return "availability indicated, to verify";
      if (text.includes("notice served") || text.includes("rented")) return "timing depends on current occupancy";
      return "availability to verify";
    }

    function sanitizeClientText(value) {
      let text = String(value || "");
      text = text.replace(/https?:\/\/\S+/gi, "");
      text = text.replace(/\bProperty Finder\b/gi, "");
      text = text.replace(/\bowner[- ]?lead\b/gi, "follow-up");
      text = text.replace(/\bpoach(?:ing)?\b/gi, "follow-up");
      text = text.replace(/\bagent\b/gi, "representative");
      text = text.replace(/\bexclusive\b/gi, "represented");
      text = text.replace(/\bpermit\b[^.,;]*/gi, "");
      text = text.replace(/\b(listing|advert|description)\b/gi, "option");
      text = text.replace(/\s+/g, " ").trim();
      return text;
    }

    function splitClientPoints(value, maxPoints = 3) {
      const text = sanitizeClientText(value);
      if (!text) return [];
      return text
        .split(/;|\.|\n/)
        .map((part) => part.trim())
        .filter(Boolean)
        .filter((part) => part.length > 8)
        .slice(0, maxPoints);
    }

    function clientSellingPoints(item) {
      const points = [
        ...splitClientPoints(item.ai_strengths, 3),
        ...splitClientPoints(item.ai_fit_summary, 2),
      ];
      if (item.outdoor_matches) {
        const outdoor = String(item.outdoor_matches)
          .split(",")
          .map((part) => part.trim())
          .filter(Boolean)
          .slice(0, 3)
          .join(", ");
        if (outdoor) points.push(`Outdoor/lifestyle clues: ${outdoor}`);
      }
      return [...new Set(points)].slice(0, 4);
    }

    function clientRecommendation(item, index) {
      const text = sanitizeClientText(item.ai_fit_summary || item.ai_opportunity_angle || item.match_reasons || "");
      if (text) return text;
      if (index === 0) return "Strongest overall match from the current shortlist, subject to availability and condition checks.";
      return "Worth keeping as a comparison option, subject to availability and viewing feedback.";
    }

    function clientScore(item) {
      const score = Number(item.ai_score || item.match_score || 0);
      if (!Number.isFinite(score) || score <= 0) return "To assess";
      return `${Math.min(95, Math.max(55, Math.round(score)))}/100`;
    }

    function renderClientOption(item, index, purposeValue) {
      const community = escapeHtml(item.predicted_community || "Area to verify");
      const type = escapeHtml(`${item.predicted_type && item.predicted_type !== "Unknown" ? item.predicted_type + " " : ""}${clientCategory(item)}`);
      const beds = item.bedrooms ? `${escapeHtml(item.bedrooms)} bed${Number(item.bedrooms) === 1 ? "" : "s"}` : "bedrooms to verify";
      const points = clientSellingPoints(item);
      const pointHtml = points.length
        ? `<ul>${points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>`
        : `<ul><li>Potentially suitable option based on price, area and property profile.</li></ul>`;
      return `
        <article class="client-option">
          <h2>Option ${index + 1} — ${community}</h2>
          <div class="client-facts">
            <span>${escapeHtml(type)}</span>
            <span>${beds}</span>
            <span>${escapeHtml(approxMoney(item.price, purposeValue))}</span>
            <span>${escapeHtml(approxSize(item.property_size_sqft))}</span>
          </div>
          <p><strong>Availability:</strong> ${escapeHtml(clientAvailability(item))}</p>
          <p><strong>Suitability score:</strong> ${escapeHtml(clientScore(item))}</p>
          <div><strong>Key selling points:</strong>${pointHtml}</div>
          <p><strong>Recommendation:</strong> ${escapeHtml(clientRecommendation(item, index))}</p>
          <p class="next-step">Next step: I will verify current availability, condition and viewing access before sharing any appointment options.</p>
        </article>`;
    }

    function openClientReport() {
      if (!lastRenderedData || !Array.isArray(lastRenderedData.matches) || !lastRenderedData.matches.length) {
        error.hidden = false;
        error.textContent = "Run Find or an AI scenario first, then create a client report.";
        return;
      }
      const data = lastRenderedData;
      const purposeValue = data.enquiry?.purpose || purpose.value || "sale";
      const options = data.matches.slice(0, 5);
      const generatedAt = new Date().toLocaleString();
      const budget = data.enquiry?.budget ? approxMoney(data.enquiry.budget, purposeValue) : "budget to verify";
      const community = data.enquiry?.community || "selected area";
      const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Client Property Shortlist</title>
  <style>
    body { font-family: Arial, sans-serif; color: #17211c; margin: 0; background: #f5f6f3; }
    main { width: min(860px, calc(100vw - 32px)); margin: 0 auto; padding: 28px 0 48px; }
    header { border-bottom: 2px solid #0b6b57; padding-bottom: 14px; margin-bottom: 18px; }
    h1 { font-size: 24px; margin: 0 0 6px; }
    .meta { color: #66736b; font-size: 13px; line-height: 1.5; }
    .intro { background: #fff; border: 1px solid #d7ded8; border-radius: 8px; padding: 14px 16px; margin-bottom: 14px; line-height: 1.5; }
    .client-option { background: #fff; border: 1px solid #d7ded8; border-radius: 8px; padding: 16px; margin-bottom: 12px; break-inside: avoid; }
    .client-option h2 { font-size: 18px; margin: 0 0 10px; color: #0b6b57; }
    .client-facts { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 10px; }
    .client-facts span { border: 1px solid #d7ded8; border-radius: 999px; padding: 5px 9px; font-size: 12px; color: #33423a; background: #fbfcfa; }
    p { font-size: 14px; line-height: 1.5; margin: 8px 0; }
    ul { margin: 6px 0 8px 18px; padding: 0; }
    li { margin: 4px 0; line-height: 1.4; }
    .next-step { color: #0b6b57; font-weight: 600; }
    .fine-print { margin-top: 18px; color: #66736b; font-size: 12px; line-height: 1.5; }
    .actions { margin: 0 0 14px; }
    button { min-height: 34px; padding: 0 14px; border: 0; border-radius: 6px; background: #0b6b57; color: #fff; font-weight: 700; cursor: pointer; }
    @media print { body { background: #fff; } main { width: 100%; padding: 0; } .actions { display: none; } .client-option, .intro { border-color: #ccc; } }
  </style>
</head>
<body>
  <main>
    <div class="actions"><button onclick="window.print()">Save as PDF</button></div>
    <header>
      <h1>Property Shortlist</h1>
      <div class="meta">${escapeHtml(community)} · ${escapeHtml(budget)} · prepared ${escapeHtml(generatedAt)}</div>
    </header>
    <section class="intro">
      <p>This shortlist summarises the strongest available options based on the current brief. Prices, sizes and availability are shown as approximate and will be verified before viewings are arranged.</p>
    </section>
    ${options.map((item, index) => renderClientOption(item, index, purposeValue)).join("")}
    <p class="fine-print">Note: details are indicative only and subject to availability, final viewing confirmation, owner approval and contract terms.</p>
  </main>
</body>
</html>`;
      const reportWindow = window.open("", "_blank");
      if (!reportWindow) {
        error.hidden = false;
        error.textContent = "Popup blocked. Allow popups for this page to open the client report.";
        return;
      }
      reportWindow.document.open();
      reportWindow.document.write(html);
      reportWindow.document.close();
    }

    function renderAiClientReport(report) {
      const txn = report.transaction_section || {};
      const inv = report.inventory_section || {};
      const alt = report.alternative_section || {};
      const cmp = report.comparison_section || {};
      const strat = report.strategic_assessment || {};
      const generatedAt = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

      function renderListingCard(listing) {
        return `
          <div class="listing-card">
            <div class="listing-label">${escapeHtml(listing.label || "")}</div>
            <div class="listing-price">${escapeHtml(listing.price || "")}</div>
            <div class="listing-tag">${escapeHtml(listing.description_tag || "")}</div>
            <div class="listing-stats">${escapeHtml(listing.stats_line || "")}</div>
            <p class="listing-narrative">${escapeHtml(listing.narrative || "")}</p>
          </div>`;
      }

      function renderSectionHeading(num, title) {
        return `<div class="section-heading"><span class="section-num">${escapeHtml(num)} —</span> <span class="section-title">${escapeHtml(title)}</span></div>`;
      }

      const transactions = Array.isArray(txn.transactions) ? txn.transactions : [];
      const txnTableRows = transactions.map((t) => `
        <tr>
          <td>${escapeHtml(t.date || "")}</td>
          <td>${escapeHtml(t.price || "")}</td>
          <td>${escapeHtml(t.size || "")}</td>
          <td>${escapeHtml(t.ppsf || "")}</td>
        </tr>`).join("");
      const txnHtml = `
        <section class="report-section">
          ${renderSectionHeading("01", txn.heading || "RECENT TRANSACTION DATA")}
          <table class="data-table">
            <thead><tr><th>DATE</th><th>SOLD PRICE (AED)</th><th>SIZE (sqft)</th><th>AED/sqft</th></tr></thead>
            <tbody>${txnTableRows}</tbody>
          </table>
          <div class="stats-box">
            <div class="stat-cell"><div class="stat-label">Sales Range</div><div class="stat-value">${escapeHtml(txn.range || "")}</div></div>
            <div class="stat-cell"><div class="stat-label">Average Sold Price</div><div class="stat-value">${escapeHtml(txn.average_price || "")}</div></div>
            <div class="stat-cell"><div class="stat-label">Average AED/sqft</div><div class="stat-value">${escapeHtml(txn.average_ppsf || "")}</div></div>
            <div class="stat-cell"><div class="stat-label">Layout Note</div><div class="stat-value">${escapeHtml(txn.layout_note || "")}</div></div>
          </div>
          <p class="narrative">${escapeHtml(txn.narrative || "")}</p>
        </section>`;

      const invListings = Array.isArray(inv.listings) ? inv.listings : [];
      const invHtml = `
        <section class="report-section">
          ${renderSectionHeading("02", inv.heading || "CURRENT INVENTORY")}
          ${invListings.map(renderListingCard).join("")}
          <div class="summary-box"><p>${escapeHtml(inv.summary_paragraph || "")}</p></div>
        </section>`;

      const altListings = Array.isArray(alt.listings) ? alt.listings : [];
      const altHtml = `
        <section class="report-section">
          ${renderSectionHeading("03", alt.heading || "STRONGEST CURRENT ALTERNATIVE")}
          <p class="narrative">${escapeHtml(alt.intro_paragraph || "")}</p>
          ${altListings.map(renderListingCard).join("")}
          <div class="summary-box"><p>${escapeHtml(alt.summary_paragraph || "")}</p></div>
        </section>`;

      const cmpRows = Array.isArray(cmp.rows) ? cmp.rows : [];
      const cmpHeaders = cmpRows.map((r) => `<th>${escapeHtml(r.label || "")}</th>`).join("");
      const cmpTableHtml = `
        <table class="data-table comparison-table">
          <thead><tr><th></th>${cmpHeaders}</tr></thead>
          <tbody>
            <tr><td class="row-label">Asking Price</td>${cmpRows.map((r) => `<td>${escapeHtml(r.price || "")}</td>`).join("")}</tr>
            <tr><td class="row-label">Size</td>${cmpRows.map((r) => `<td>${escapeHtml(r.size || "")}</td>`).join("")}</tr>
            <tr><td class="row-label">AED/sqft</td>${cmpRows.map((r) => `<td>${escapeHtml(r.ppsf || "")}</td>`).join("")}</tr>
            <tr><td class="row-label">Beds/Baths</td>${cmpRows.map((r) => `<td>${escapeHtml(r.beds_baths || "")}</td>`).join("")}</tr>
            <tr><td class="row-label">Availability</td>${cmpRows.map((r) => `<td>${escapeHtml(r.availability || "")}</td>`).join("")}</tr>
          </tbody>
        </table>`;
      const cmpHtml = `
        <section class="report-section">
          ${renderSectionHeading("04", cmp.heading || "INVENTORY COMPARISON")}
          ${cmpTableHtml}
        </section>`;

      const stratSections = Array.isArray(strat.sections) ? strat.sections : [];
      const approachItems = Array.isArray(strat.approach_items) ? strat.approach_items : [];
      const stratHtml = `
        <section class="report-section">
          ${renderSectionHeading("05", "STRATEGIC ASSESSMENT | Advisory Summary")}
          <div class="market-context-box">
            <div class="market-context-label">MARKET CONTEXT</div>
            <p>${escapeHtml(strat.market_context || "")}</p>
          </div>
          ${stratSections.map((s) => `
            <div class="strat-section">
              <div class="strat-heading">${escapeHtml(s.heading || "")}</div>
              <p>${escapeHtml(s.body || "")}</p>
            </div>`).join("")}
          <div class="approach-heading">HOW I AM APPROACHING THIS FOR YOU</div>
          ${approachItems.map((item) => `
            <div class="approach-item">
              <div class="approach-num">${escapeHtml(item.number || "")}</div>
              <div class="approach-body">
                <div class="approach-action">${escapeHtml(item.action || "")}</div>
                <p>${escapeHtml(item.detail || "")}</p>
              </div>
            </div>`).join("")}
        </section>`;

      const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(report.title || "Client Property Report")}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: 'Segoe UI', Arial, sans-serif; color: #17211c; margin: 0; background: #eef0ed; }
    main { max-width: 880px; margin: 0 auto; padding: 32px 16px 56px; }
    .actions { margin-bottom: 16px; }
    button { min-height: 34px; padding: 0 16px; border: 0; border-radius: 6px; background: #0b6b57; color: #fff; font-weight: 700; cursor: pointer; font-size: 14px; }
    /* Header */
    .report-header { background: #fff; border-radius: 8px; padding: 28px 28px 22px; margin-bottom: 20px; border-bottom: 3px solid #0b6b57; }
    .report-title { font-size: 28px; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; margin: 0 0 6px; color: #11231c; }
    .report-subtitle { font-size: 15px; font-weight: 400; color: #33423a; margin: 0 0 10px; }
    .report-meta { font-size: 12px; color: #7a8a80; letter-spacing: 0.05em; text-transform: uppercase; }
    /* Section heading */
    .report-section { background: #fff; border-radius: 8px; padding: 24px 28px; margin-bottom: 16px; }
    .section-heading { display: flex; align-items: baseline; gap: 8px; border-bottom: 2px solid #e4e8e5; padding-bottom: 10px; margin-bottom: 18px; }
    .section-num { font-size: 13px; color: #7a8a80; font-weight: 600; letter-spacing: 0.06em; white-space: nowrap; }
    .section-title { font-size: 14px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #11231c; }
    /* Tables */
    table.data-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 16px; }
    table.data-table thead tr { background: #0b6b57; color: #fff; }
    table.data-table thead th { padding: 9px 10px; text-align: left; font-weight: 600; letter-spacing: 0.04em; }
    table.data-table tbody tr:nth-child(even) { background: #f6f9f7; }
    table.data-table tbody td { padding: 8px 10px; border-bottom: 1px solid #e4e8e5; vertical-align: top; }
    /* Stats box */
    .stats-box { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: #e4e8e5; border: 1px solid #e4e8e5; border-radius: 6px; overflow: hidden; margin-bottom: 16px; }
    .stat-cell { background: #fff; padding: 12px 14px; }
    .stat-label { font-size: 11px; color: #7a8a80; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
    .stat-value { font-size: 14px; font-weight: 600; color: #11231c; }
    /* Listing card */
    .listing-card { background: #fff; border: 1px solid #dde4e0; border-radius: 8px; padding: 18px 20px; margin-bottom: 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); break-inside: avoid; }
    .listing-label { font-size: 11px; font-weight: 700; color: #0b6b57; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 6px; font-variant: small-caps; }
    .listing-price { font-size: 24px; font-weight: 800; color: #11231c; margin-bottom: 4px; }
    .listing-tag { font-size: 13px; color: #7a8a80; font-style: italic; margin-bottom: 6px; }
    .listing-stats { font-size: 13px; color: #4a5a52; margin-bottom: 10px; letter-spacing: 0.01em; }
    .listing-narrative { font-size: 14px; line-height: 1.6; color: #33423a; margin: 0; }
    /* Summary box */
    .summary-box { background: #f0f7f4; border-left: 3px solid #0b6b57; border-radius: 4px; padding: 14px 16px; margin-top: 8px; }
    .summary-box p { font-size: 14px; line-height: 1.6; color: #33423a; margin: 0; }
    /* Comparison table */
    .comparison-table .row-label { font-weight: 700; color: #0b6b57; background: #f6f9f7; }
    /* Strategic section */
    .market-context-box { background: #f0f7f4; border: 1px solid #c3ddd5; border-radius: 6px; padding: 16px 18px; margin-bottom: 20px; }
    .market-context-label { font-size: 11px; font-weight: 700; color: #0b6b57; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px; }
    .market-context-box p { font-size: 14px; line-height: 1.6; color: #33423a; margin: 0; }
    .strat-section { margin-bottom: 16px; }
    .strat-heading { font-size: 12px; font-weight: 700; color: #0b6b57; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px; }
    .strat-section p { font-size: 14px; line-height: 1.6; color: #33423a; margin: 0; }
    .approach-heading { font-size: 13px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #11231c; border-top: 1px solid #e4e8e5; padding-top: 16px; margin: 20px 0 14px; }
    .approach-item { display: flex; gap: 16px; margin-bottom: 16px; align-items: flex-start; }
    .approach-num { font-size: 28px; font-weight: 800; color: #0b6b57; line-height: 1; min-width: 36px; }
    .approach-body { flex: 1; }
    .approach-action { font-size: 14px; font-weight: 700; color: #11231c; margin-bottom: 4px; }
    .approach-body p { font-size: 14px; line-height: 1.6; color: #33423a; margin: 0; }
    /* Narrative */
    p.narrative { font-size: 14px; line-height: 1.6; color: #33423a; margin: 0 0 8px; }
    /* Footer */
    .report-footer { text-align: center; font-size: 12px; color: #7a8a80; margin-top: 24px; padding: 12px 0; border-top: 1px solid #dde4e0; }
    /* Print */
    @media print {
      body { background: #fff; }
      main { max-width: 100%; padding: 0; }
      .actions { display: none; }
      .report-section, .listing-card, .report-header { box-shadow: none; border-color: #ccc; }
      .stats-box { background: #ccc; }
    }
  </style>
</head>
<body>
  <main>
    <div class="actions"><button onclick="window.print()">Save as PDF</button></div>
    <div class="report-header">
      <div class="report-title">${escapeHtml(report.title || "Client Property Report")}</div>
      <div class="report-subtitle">${escapeHtml(report.subtitle || "")}</div>
      <div class="report-meta">Prepared: ${escapeHtml(generatedAt)} &middot; Confidential</div>
    </div>
    ${txnHtml}
    ${invHtml}
    ${altHtml}
    ${cmpHtml}
    ${stratHtml}
    <div class="report-footer">${escapeHtml(report.footer || report.disclaimer || "")}</div>
  </main>
</body>
</html>`;
      const reportWindow = window.open("", "_blank");
      if (!reportWindow) {
        error.hidden = false;
        error.textContent = "Popup blocked. Allow popups for this page to open the client report.";
        return;
      }
      reportWindow.document.open();
      reportWindow.document.write(html);
      reportWindow.document.close();
    }

    async function runClientReport() {
      const text = promptBox.value.trim();
      const token = activeApiKey || tokenBox.value.trim();
      if (!text) { promptBox.focus(); return; }
      if (!token) { error.hidden = false; error.textContent = "Add and check an OpenAI API key first (AI key button above)."; return; }
      if (!lastReportContext || !lastReportContext.ranked_urls?.length) {
        error.hidden = false;
        error.textContent = "Run Build Report first, then create a client report.";
        return;
      }
      const rankedUrls = lastReportContext.ranked_urls;
      const scenario = lastReportContext.scenario;
      clientReportButton.disabled = true;
      clientReportButton.textContent = "Writing…";
      error.hidden = true;
      aiPanel.hidden = false;
      aiPanel.textContent = "Writing a client-safe report from the built report shortlist...";
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 240000);
      try {
        const res = await fetch("/api/client-report", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: text, purpose: purpose.value, scenario, listing_scope: listingScope.value, listing_communities: selectedListingCommunities(), market_scope: marketScope.value, market_communities: selectedMarketCommunities(), api_key: token, limit: 6, ranked_urls: rankedUrls }),
          signal: controller.signal
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Client report failed");
        renderAiClientReport(data.client_report || {});
        aiPanel.hidden = false;
        aiPanel.textContent = "Client report opened in a new tab.";
        setWorkflowStep(4);
      } catch (err) {
        error.hidden = false;
        error.textContent = err.name === "AbortError" ? "Client report timed out. Try fewer ranked results." : err.message;
        aiPanel.hidden = true;
      } finally {
        clearTimeout(timeoutId);
        clientReportButton.disabled = false;
        clientReportButton.textContent = "Client report";
      }
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

    function fmtAed(n) {
      if (!Number.isFinite(n)) return "—";
      if (n >= 1_000_000) return (n / 1_000_000).toFixed(2).replace(/\.?0+$/, "") + "M";
      if (n >= 1_000) return (n / 1_000).toFixed(0) + "K";
      return n.toLocaleString();
    }

    async function runEstimate() {
      const text = promptBox.value.trim();
      const token = activeApiKey || tokenBox.value.trim();
      if (!text) { promptBox.focus(); return; }
      if (!token) { error.hidden = false; error.textContent = "Add and check an OpenAI API key first (AI key button above)."; return; }
      estimateButton.disabled = true;
      estimateButton.textContent = "Estimating…";
      error.hidden = true;
      estimatePanel.hidden = false;
      estimatePanel.innerHTML = `<div style="color:#6d3bbf;font-size:13px;">Analysing comparables and generating estimate…</div>`;
      // Pass selected listing communities so the estimator can widen the comp pool.
      // The user can also name communities directly in the prompt.
      const extraComms = selectedListingCommunities().filter(c => c !== "Arabian Ranches 2");
      try {
        const res = await fetch("/api/estimate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: text,
            purpose: purpose.value,
            api_key: token,
            extra_communities: extraComms,
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Estimate failed");
        const est = data.estimate || {};
        const confidence = est.confidence ? `<span style="font-size:11px;color:#6d3bbf;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Confidence: ${escapeHtml(est.confidence)}</span>` : "";
        const isRent = data.purpose === "rent";
        const currSuffix = isRent ? "/yr" : "";
        const rangeHtml = (Number.isFinite(est.low) && Number.isFinite(est.mid) && Number.isFinite(est.high)) ? `
          <div class="estimate-range">
            <div class="estimate-band low">
              <div class="band-label">Low</div>
              <div class="band-price">AED ${fmtAed(est.low)}${currSuffix}</div>
              <div class="band-note">${escapeHtml(est.rationale?.low || "")}</div>
            </div>
            <div class="estimate-band mid">
              <div class="band-label">Mid (anchor)</div>
              <div class="band-price">AED ${fmtAed(est.mid)}${currSuffix}</div>
              <div class="band-note">${escapeHtml(est.rationale?.mid || "")}</div>
            </div>
            <div class="estimate-band high">
              <div class="band-label">High</div>
              <div class="band-price">AED ${fmtAed(est.high)}${currSuffix}</div>
              <div class="band-note">${escapeHtml(est.rationale?.high || "")}</div>
            </div>
          </div>` : `<p style="color:#c00;font-size:13px;">Could not produce a price range — ${escapeHtml(est.parse_error || est.raw || "no data")}</p>`;
        const premiums = (est.premium_factors || []).map(f => `<li>${escapeHtml(f)}</li>`).join("");
        const discounts = (est.discount_factors || []).map(f => `<li>${escapeHtml(f)}</li>`).join("");
        const risks = (est.key_risks || []).map(f => `<li>${escapeHtml(f)}</li>`).join("");
        // Data quality tip: if type wasn't found in the specified communities, tell the user which have it
        const typeAvailableIn = data.type_available_in || [];
        const crossWarning = data.cross_community_warning || "";
        let dataTipHtml = "";
        if (crossWarning) {
          const tipComms = typeAvailableIn.slice(0, 5);
          const suggestionHtml = tipComms.length
            ? `<br>Try adding <strong>${tipComms.join(", ")}</strong> to your prompt, or tick them in the scope panel.`
            : "";
          dataTipHtml = `<p class="estimate-meta" style="color:#b45309;margin-top:4px;">&#9888; ${escapeHtml(crossWarning)}${suggestionHtml}</p>`;
        }
        const comps = (data.sample_comparables || []);
        const compRows = comps.map(c => `<tr>
          <td>${escapeHtml(c.community || "")}</td>
          <td>${escapeHtml(c.type || "")}</td>
          <td>${c.beds || "—"}</td>
          <td>${c.bua_sqft ? c.bua_sqft.toLocaleString() : "—"}</td>
          <td>${c.plot_sqft ? c.plot_sqft.toLocaleString() : "—"}</td>
          <td>${c.price ? "AED " + fmtAed(c.price) + (isRent ? "/yr" : "") : "—"}</td>
          <td>${c.price_per_sqft && !isRent ? "AED " + Math.round(c.price_per_sqft) : "—"}</td>
        </tr>`).join("");
        const compsHtml = compRows ? `
          <details class="estimate-comps">
            <summary>Comparable listings used (${comps.length})</summary>
            <table>
              <tr><th>Community</th><th>Type</th><th>Beds</th><th>BUA sqft</th><th>Plot sqft</th><th>Price</th>${isRent ? "" : "<th>PPSF</th>"}</tr>
              ${compRows}
            </table>
          </details>` : "";
        const purposeLabel = isRent ? "Rental" : "Sale";
        estimatePanel.innerHTML = `
          <h2>Property Value Estimate <span style="font-size:12px;font-weight:400;color:#6d3bbf;">${purposeLabel}</span></h2>
          <p class="estimate-meta">Based on <strong>${data.comparable_count || 0}</strong> comparable active listings · ${escapeHtml(data.match_basis || "")} · ${escapeHtml((data.all_communities || [data.community]).join(" / ") || "")} ${data.villa_type || ""} ${data.bedrooms ? data.bedrooms + " bed" : ""}</p>
          ${dataTipHtml}
          ${confidence}
          ${rangeHtml}
          ${premiums ? `<div class="estimate-section-title">Premium factors</div><ul class="estimate-list">${premiums}</ul>` : ""}
          ${discounts ? `<div class="estimate-section-title">Discount factors</div><ul class="estimate-list">${discounts}</ul>` : ""}
          ${risks ? `<div class="estimate-section-title">Key risks & unknowns</div><ul class="estimate-list estimate-risks">${risks}</ul>` : ""}
          ${est.data_basis ? `<p class="estimate-meta" style="margin-top:6px;">${escapeHtml(est.data_basis)}</p>` : ""}
          ${compsHtml}`;
      } catch (err) {
        error.hidden = false;
        error.textContent = err.message;
        estimatePanel.hidden = true;
      } finally {
        estimateButton.disabled = false;
        estimateButton.textContent = "Estimate value";
      }
    }

    async function runOpportunityScan() {
      const token = activeApiKey || tokenBox.value.trim();
      const scanPurpose = oppPurposeFilter?.value || "both";
      if (!token) { error.hidden = false; error.textContent = "Add and check an OpenAI API key first (AI key button above)."; return; }
      oppScanButton.disabled = true;
      oppScanButton.textContent = "Scanning…";
      error.hidden = true;
      opportunityPanel.hidden = false;
      opportunityPanel.innerHTML = `<div style="color:#c0411a;font-size:13px;">Scanning database for poachable listings…</div>`;

      try {
        const res = await fetch("/api/opportunity-scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_key: token,
            purpose_filter: scanPurpose,
            limit: 15,
          }),
        });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || "Opportunity scan failed.");

        const opps = data.opportunities || [];
        const scanNote = data.scan_note || "";
        const scannedCount = data.total_active_scanned || 0;
        const candidateCount = data.candidates_sent_to_ai || 0;

        const typeLabels = {
          stale_overpriced: "Stale + Overpriced",
          stale_listing: "Stale Listing",
          overpriced: "Overpriced",
          weak_listing: "Weak Listing",
          motivated_seller: "Motivated Seller",
        };

        function fmtPrice(price, currency) {
          if (!price) return "—";
          const n = Number(price);
          const suffix = currency === "AED/yr" ? "/yr" : "";
          if (n >= 1_000_000) return "AED " + (n / 1_000_000).toFixed(2).replace(/\.?0+$/, "") + "M" + suffix;
          if (n >= 1_000) return "AED " + (n / 1_000).toFixed(0) + "K" + suffix;
          return "AED " + n.toLocaleString() + suffix;
        }

        function stalePill(days) {
          if (days == null) return "";
          if (days >= 60) return `<span class="opp-pill stale">${days}d on market</span>`;
          if (days >= 30) return `<span class="opp-pill stale">${days}d on market</span>`;
          return `<span class="opp-pill">${days}d on market</span>`;
        }

        function pricePill(pct, price, currency) {
          if (!price) return "";
          const priceStr = fmtPrice(price, currency);
          if (pct != null && pct > 5) return `<span class="opp-pill overpriced">${priceStr} (+${pct}% vs median)</span>`;
          return `<span class="opp-pill">${priceStr}</span>`;
        }

        function agentPills(opp) {
          const pills = [];
          if (opp.agent_is_superagent || /superagent/i.test(opp.agent_badge || "")) {
            pills.push(`<span class="opp-pill agent-strong">SuperAgent</span>`);
          }
          if (opp.agent_rating) {
            const reviews = opp.agent_review_count != null ? ` &middot; ${opp.agent_review_count} ratings` : "";
            pills.push(`<span class="opp-pill agent-rating">${Number(opp.agent_rating).toFixed(1)} star${reviews}</span>`);
          } else {
            pills.push(`<span class="opp-pill agent-weak">No visible rating</span>`);
          }
          if (opp.agent_closed_deals != null) {
            pills.push(`<span class="opp-pill">${opp.agent_closed_deals} closed deals</span>`);
          }
          if (opp.agent_response_time) {
            pills.push(`<span class="opp-pill">${escapeHtml(opp.agent_response_time)} response</span>`);
          }
          return pills.join("");
        }

        const cards = opps.map(opp => {
          const score = opp.opportunity_score || 0;
          const typeLabel = typeLabels[opp.opportunity_type] || (opp.opportunity_type || "Opportunity").replace(/_/g, " ");
          const beds = opp.bedrooms ? `${opp.bedrooms} bed · ` : "";
          const sqft = opp.property_size_sqft ? `${opp.property_size_sqft.toLocaleString()} sqft` : "";
          const statsLine = [beds + opp.community, opp.predicted_type, sqft].filter(Boolean).join(" · ");

          return `
  <div class="opp-card">
    <div class="opp-card-header">
      <div class="opp-score-badge">${score}</div>
      <div class="opp-headline">${escapeHtml(opp.headline || "Opportunity")}</div>
    </div>
    <div><span class="opp-type-badge">${escapeHtml(typeLabel)}</span></div>
    <div class="opp-stats">
      ${stalePill(opp.days_on_market)}
      ${pricePill(opp.price_vs_median_pct, opp.price, opp.price_currency)}
      ${statsLine ? `<span class="opp-pill">${escapeHtml(statsLine)}</span>` : ""}
      ${agentPills(opp)}
    </div>
    <div class="opp-reason">${escapeHtml(opp.reason || "")}</div>
    <div class="opp-approach">→ ${escapeHtml(opp.approach || "")}</div>
    ${opp.talking_point ? `<div class="opp-talking-point">"${escapeHtml(opp.talking_point)}"</div>` : ""}
    <div class="opp-agent">
      <strong>${escapeHtml(opp.agent_name || "Unknown agent")}</strong>
      ${opp.agency_name ? ` · ${escapeHtml(opp.agency_name)}` : ""}
    </div>
  </div>`;
        }).join("");

        const purposeLabel = scanPurpose === "sale" ? "Sales" : scanPurpose === "rent" ? "Rentals" : "All";
        opportunityPanel.innerHTML = `
  <h2>Opportunity Scan <span style="font-size:12px;font-weight:400;color:#c0411a;">${purposeLabel} · ${opps.length} leads identified</span></h2>
  <p class="opp-scan-note">Scanned ${scannedCount} active listings · ${candidateCount} candidates analysed${scanNote ? " · " + escapeHtml(scanNote) : ""}</p>
  <div class="opp-grid">${cards || "<p style='color:var(--muted);font-size:13px;'>No strong opportunities found — try running a fresh scrape to update listing data.</p>"}</div>`;
      } catch (err) {
        error.hidden = false;
        error.textContent = err.message;
        opportunityPanel.hidden = true;
      } finally {
        oppScanButton.disabled = false;
        oppScanButton.textContent = "Opportunity scan";
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
    estimateButton.addEventListener("click", () => { ensureApiKeyVisible(); runEstimate(); });
    oppScanButton.addEventListener("click", () => { ensureApiKeyVisible(); runOpportunityScan(); });
    aiReportButton.addEventListener("click", () => { ensureApiKeyVisible(); runBuildReport(); });
    clientReportButton.addEventListener("click", () => { ensureApiKeyVisible(); runClientReport(); });
    scenarioButtons.forEach((btn) => btn.addEventListener("click", () => { ensureApiKeyVisible(); runScenario(btn.dataset.scenario, btn); }));
    promptBox.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runSearch(); });

    // Set initial state on page load
    setWorkflowStep(0);
