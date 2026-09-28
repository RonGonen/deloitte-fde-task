/* Chat client: talks to /api/chat, renders answers safely, optional voice in/out. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const messagesEl = $("messages"), inputEl = $("input"), sendBtn = $("send"), micBtn = $("mic"), speakBtn = $("speak");
  const template = $("msg-template");
  let sessionId = sessionStorage.getItem("aiia.session") || (window.crypto && crypto.randomUUID ? crypto.randomUUID() : null);
  if (sessionId) sessionStorage.setItem("aiia.session", sessionId);
  let speakEnabled = false;
  let inFlight = false;

  // ---------- API helper: bearer token (if the server requires one), ok-checks, fixed error messages ----------
  let apiToken = sessionStorage.getItem("aiia.token") || "";
  async function api(path, options, retry) {
    const opts = Object.assign({ headers: {} }, options || {});
    opts.headers = Object.assign({}, opts.headers);
    if (apiToken) opts.headers["Authorization"] = "Bearer " + apiToken;
    const res = await fetch(path, opts);
    if (res.status === 401 && !retry) {
      const entered = window.prompt("This server requires an access token (APP_TOKEN). Paste it to continue:");
      if (entered && entered.trim()) { apiToken = entered.trim(); sessionStorage.setItem("aiia.token", apiToken); return api(path, options, true); }
    }
    let body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    if (!res.ok) {
      const detail = body && body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : "HTTP " + res.status;
      const err = new Error(detail); err.status = res.status; throw err;
    }
    return body;
  }

  // ---------- safe markdown-ish renderer (escape first, then add our own tags) ----------
  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const inline = (s) => escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  function renderMarkdown(text) {
    const lines = text.split(/\r?\n/);
    let html = "", i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (/^\s*\|.*\|\s*$/.test(line)) {
        const rows = [];
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(lines[i]); i++; }
        const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        const body = rows.filter((r) => !/^[\s|:\-]+$/.test(r)); // drop markdown separator rows like |---|---|
        const header = cells(body[0]);
        html += "<table><thead><tr>" + header.map((c) => "<th>" + inline(c) + "</th>").join("") + "</tr></thead><tbody>";
        body.slice(1).forEach((r) => { html += "<tr>" + cells(r).map((c) => "<td>" + inline(c) + "</td>").join("") + "</tr>"; });
        html += "</tbody></table>";
        continue;
      }
      if (/^\s*[-*]\s+/.test(line)) {
        html += "<ul>";
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { html += "<li>" + inline(lines[i].replace(/^\s*[-*]\s+/, "")) + "</li>"; i++; }
        html += "</ul>";
        continue;
      }
      if (/^\s*\d+[.)]\s+/.test(line)) {
        html += "<ol>";
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { html += "<li>" + inline(lines[i].replace(/^\s*\d+[.)]\s+/, "")) + "</li>"; i++; }
        html += "</ol>";
        continue;
      }
      if (/^\s*#{1,6}\s+/.test(line)) { html += "<h3>" + inline(line.replace(/^\s*#{1,6}\s+/, "")) + "</h3>"; i++; continue; }
      if (line.trim() === "") { i++; continue; }
      let para = [];
      while (i < lines.length && lines[i].trim() !== "" && !/^\s*(\||[-*]\s|\d+[.)]\s|#{1,6}\s)/.test(lines[i])) { para.push(lines[i]); i++; }
      html += "<p>" + para.map(inline).join("<br>") + "</p>";
    }
    return html;
  }

  // ---------- message rendering ----------
  function pill(text, cls) { const s = document.createElement("span"); s.className = "pill " + (cls || ""); s.textContent = text; return s; }

  function addMessage(role, text, meta) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.classList.add(role);
    node.querySelector(".who").textContent = role === "user" ? "You" : "Agent";
    const body = node.querySelector(".msg-body");
    if (role === "user") { body.textContent = text; node.querySelector(".sources-panel").remove(); node.querySelector(".data-panel").remove(); }
    else {
      body.innerHTML = renderMarkdown(text || "");
      const badges = node.querySelector(".badges");
      if (meta) {
        badges.appendChild(pill(meta.mode === "llm" ? "LLM: " + (meta.model || meta.provider) : "rules-based", meta.mode === "llm" ? "pill-llm" : "pill-rules"));
        if (meta.latency_ms != null) badges.appendChild(pill((meta.latency_ms / 1000).toFixed(1) + " s", "pill-muted"));
        const conf = topConfidence(meta.tool_results);
        if (conf) badges.appendChild(pill("confidence: " + conf.level + (conf.tool ? " (" + conf.tool + ")" : ""), conf.level === "high" ? "pill-ok" : "pill-warn"));
        renderSources(node.querySelector(".sources-panel .panel-body"), meta);
        node.querySelector(".data-json").textContent = meta.tool_results && meta.tool_results.length ? JSON.stringify(meta.tool_results, null, 2) : "No tool was needed for this answer.";
        (meta.warnings || []).forEach((w) => { const d = document.createElement("div"); d.className = "warning"; d.textContent = "⚠ " + w; body.appendChild(d); });
      } else { node.querySelector(".sources-panel").remove(); node.querySelector(".data-panel").remove(); }
    }
    messagesEl.appendChild(node);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return node;
  }

  const TOOL_NAMES = { rank_airports: "expansion score", airport_profile: "airport profile", compare_congestion: "congestion index",
    long_haul_share: "long-haul share", demand_pressure: "unmet demand indicator", live_airport_status: "live status",
    explain_methodology: "methodology", resolve_airports: "airport lookup" };
  function topConfidence(results) {
    if (!results || !results.length) return null;
    const order = { high: 0, medium: 1, low: 2 };
    let worst = null, worstTool = null, distinct = 0;
    results.forEach((r) => {
      const l = r.confidence && r.confidence.level; if (!l) return; distinct++;
      if (worst === null || order[l] > order[worst]) { worst = l; worstTool = r.tool; }
    });
    if (!worst) return null;
    return { level: worst, tool: (worst !== "high" && distinct > 1) ? (TOOL_NAMES[worstTool] || worstTool) : null };
  }

  function renderSources(container, meta) {
    container.textContent = "";
    if (meta.sources && meta.sources.length) {
      const h = document.createElement("div"); h.innerHTML = "<strong>Sources</strong>"; container.appendChild(h);
      const ul = document.createElement("ul");
      meta.sources.forEach((s) => {
        const li = document.createElement("li"); li.className = "src";
        const a = document.createElement("a"); a.href = s.url || "#"; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = s.name || "source";
        li.appendChild(a);
        li.appendChild(document.createTextNode(" — " + [s.period ? "period: " + s.period : null, s.vintage ? "vintage: " + s.vintage : null, s.retrieved_at ? "retrieved: " + s.retrieved_at : null].filter(Boolean).join("; ")));
        ul.appendChild(li);
      });
      container.appendChild(ul);
    }
    if (meta.caveats && meta.caveats.length) {
      const h = document.createElement("div"); h.innerHTML = "<strong>Assumptions, uncertainty and scope</strong>"; container.appendChild(h);
      const ul = document.createElement("ul");
      meta.caveats.forEach((c) => { const li = document.createElement("li"); li.textContent = c; ul.appendChild(li); });
      container.appendChild(ul);
    }
    (meta.tool_results || []).forEach((r) => {
      if (r.confidence && (r.confidence.missing_components || []).length) {
        const d = document.createElement("div"); d.textContent = "Missing components for " + r.tool + ": " + r.confidence.missing_components.join(", "); container.appendChild(d);
      }
    });
    if (!container.childNodes.length) container.textContent = "No data sources were needed for this answer.";
  }

  // ---------- speech ----------
  function speak(text) {
    if (!speakEnabled || !("speechSynthesis" in window)) return;
    const plain = text.replace(/\|/g, " ").replace(/[*#`_>-]/g, " ").replace(/\s+/g, " ").trim().slice(0, 600);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(plain));
  }
  speakBtn.addEventListener("click", () => {
    speakEnabled = !speakEnabled;
    speakBtn.setAttribute("aria-pressed", String(speakEnabled));
    speakBtn.textContent = speakEnabled ? "🔊" : "🔈";
    if (!speakEnabled && "speechSynthesis" in window) window.speechSynthesis.cancel();
  });
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) { micBtn.disabled = true; micBtn.title = "Voice input is not supported in this browser (try Chrome)."; }
  else {
    let rec = null;
    micBtn.addEventListener("click", () => {
      if (rec) { rec.stop(); return; }
      rec = new Recognition(); rec.lang = "en-US"; rec.interimResults = true;
      micBtn.classList.add("active"); micBtn.textContent = "⏺";
      rec.onresult = (e) => { inputEl.value = Array.from(e.results).map((r) => r[0].transcript).join(" "); };
      rec.onerror = () => { micBtn.classList.remove("active"); micBtn.textContent = "🎤"; rec = null; };
      rec.onend = () => { micBtn.classList.remove("active"); micBtn.textContent = "🎤"; rec = null; if (inputEl.value.trim()) send(); };
      rec.start();
    });
  }

  // ---------- send ----------
  async function send() {
    const message = inputEl.value.trim();
    if (!message || inFlight) return;
    inFlight = true;
    inputEl.value = "";
    addMessage("user", message);
    sendBtn.disabled = true;
    const pending = addMessage("assistant", "Working… fetching FAA/BTS data and computing scores.");
    pending.classList.add("pending");
    try {
      const data = await api("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId }) });
      pending.remove();
      sessionId = data.session_id; sessionStorage.setItem("aiia.session", sessionId);
      addMessage("assistant", data.text, data);
      speak(data.text);
    } catch (err) {
      pending.remove();
      addMessage("assistant", err.status ? "The server rejected the request (" + err.message + ")." : "The server could not be reached. Is it running on this machine?", null);
    } finally { inFlight = false; sendBtn.disabled = false; inputEl.focus(); }
  }
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  $("chips").addEventListener("click", (e) => { const q = e.target && e.target.getAttribute("data-q"); if (q) { inputEl.value = q; send(); } });

  // ---------- health ----------
  api("/api/health").then((h) => {
    const p = $("provider-pill");
    p.textContent = h.provider === "rules" ? "rules-based (no LLM configured)" : "LLM: " + h.model + " via " + h.provider;
    p.className = "pill " + (h.provider === "rules" ? "pill-rules" : "pill-llm");
    const faa = h.sources && h.sources.faa_enplanements;
    const delay = h.sources && h.sources.bts_delay_cause;
    $("data-pill").textContent = [faa && faa.vintage ? "FAA " + faa.vintage : null, delay && delay.period ? "BTS " + delay.period : null, h.universe_size + " airports scored"].filter(Boolean).join(" · ");
    renderDataCard(h);
  }).catch(() => { $("provider-pill").textContent = "server unavailable"; });

  // ---------- side panel: top candidates (same engine as the chat), live status, data vintages, weights ----------
  const topBody = document.querySelector("#top-table tbody"), topScope = $("top-scope"), regionSel = $("top-region"), floorSel = $("top-floor");
  const fmtInt = (n) => (n == null ? "n/a" : Math.round(n).toLocaleString("en-US"));
  const fmtCompact = (n) => (n == null ? "n/a" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(Math.round(n)));

  function loadRegions() {
    return api("/api/regions").then((d) => {
      (d.regions || []).forEach((name) => {
        const opt = document.createElement("option"); opt.value = name;
        opt.textContent = name.replace(/\b\w/g, (c) => c.toUpperCase()); regionSel.appendChild(opt);
      });
    }).catch(() => {});
  }

  let topRequestId = 0;
  function showTopMessage(text) {
    topBody.textContent = "";
    const tr = document.createElement("tr"); const td = document.createElement("td"); td.colSpan = 4; td.className = "muted"; td.textContent = text;
    tr.appendChild(td); topBody.appendChild(tr);
  }
  function loadTop() {
    const requestId = ++topRequestId;
    topScope.textContent = "loading…";
    const params = new URLSearchParams({ min_enplanements: floorSel.value, limit: "10" });
    if (regionSel.value) params.set("region", regionSel.value);
    return api("/api/rank?" + params.toString()).then((d) => {
      if (requestId !== topRequestId) return; // a newer request superseded this one
      const data = d.data || {};
      if (data.weights) renderWeights(data.weights);
      if (!data.ranked || !data.ranked.length) { showTopMessage(data.message || "No airports match this scope."); topScope.textContent = "no results"; return; }
      topBody.textContent = "";
      data.ranked.forEach((x) => {
        const tr = document.createElement("tr");
        tr.title = "Ask the agent about " + (x.iata || x.lid);
        tr.dataset.code = x.iata || x.lid;
        tr.dataset.rank = x.rank;
        const tdRank = document.createElement("td"); tdRank.textContent = x.rank;
        const tdName = document.createElement("td");
        const strong = document.createElement("strong"); strong.textContent = (x.iata || x.lid) + " ";
        const place = (x.city || "").replace(/\s+(International|Intl|Regional|Municipal|Metropolitan)?\s*(Airport|Jetport|Field)\s*$/i, "").trim() || x.name;
        tdName.appendChild(strong); tdName.appendChild(document.createTextNode(place + ", " + x.state));
        const tdScore = document.createElement("td"); tdScore.className = "score"; tdScore.textContent = x.score == null ? "n/a" : x.score.toFixed(1);
        const bar = document.createElement("span"); bar.className = "bar"; const fill = document.createElement("span"); fill.style.width = Math.max(0, Math.min(100, x.score || 0)) + "%"; bar.appendChild(fill); tdScore.appendChild(bar);
        const tdSize = document.createElement("td"); tdSize.className = "size"; tdSize.textContent = fmtCompact(x.metrics && x.metrics.enplanements);
        if (x.data_gaps && x.data_gaps.length) tr.title += " (scored on partial data: " + x.data_gaps.length + " input" + (x.data_gaps.length > 1 ? "s" : "") + " missing)";
        tr.appendChild(tdRank); tr.appendChild(tdName); tr.appendChild(tdScore); tr.appendChild(tdSize);
        topBody.appendChild(tr);
      });
      const scopeLabel = (data.scope && data.scope.states && data.scope.states.length) ? data.scope.states.join(", ") : "United States";
      topScope.textContent = scopeLabel + " · " + data.candidates_in_filter + " of " + data.universe_size + " airports ≥ " + fmtInt(data.min_enplanements);
    }).catch((err) => {
      if (requestId !== topRequestId) return;
      showTopMessage(err.status ? "Ranking unavailable (" + err.message + ")." : "Ranking unavailable: the server could not be reached.");
      topScope.textContent = "unavailable";
    });
  }
  topBody.addEventListener("click", (e) => {
    const row = e.target && e.target.closest("tr"); if (!row || !row.dataset.code) return;
    const scope = regionSel.value ? regionSel.options[regionSel.selectedIndex].textContent : "the United States";
    const floor = floorSel.options[floorSel.selectedIndex].textContent;
    inputEl.value = "Tell me about " + row.dataset.code + " and why it ranks #" + row.dataset.rank + " for expansion in " + scope +
      " (airports with at least " + floor + " annual enplanements).";
    send();
  });
  regionSel.addEventListener("change", loadTop);
  floorSel.addEventListener("change", loadTop);

  function loadLive() {
    if (document.visibilityState === "hidden") return; // nobody is looking; save the FAA feed and the server
    api("/api/live").then((d) => {
      const data = d.data || {}; const list = $("live-list"); list.textContent = "";
      $("live-time").textContent = data.update_time ? "FAA " + data.update_time.replace(/^\w+\s/, "") : "";
      const items = [];
      Object.entries(data.by_type || {}).forEach(([type, arr]) => arr.forEach((ev) => items.push(Object.assign({}, ev, { type: type }))));
      if (data.error) { const li = document.createElement("li"); li.className = "muted"; li.textContent = "FAA live status feed is unavailable right now."; list.appendChild(li); return; }
      if (!items.length) { const li = document.createElement("li"); li.className = "muted"; li.textContent = "No active ground delays, ground stops or closures nationwide."; list.appendChild(li); return; }
      const order = { ground_stop: 0, closure: 1, ground_delay: 2, general_delay: 3 };
      const rank = (t) => (order[t] === undefined ? 9 : order[t]);
      items.sort((a, b) => rank(a.type) - rank(b.type)).slice(0, 12).forEach((ev) => {
        const li = document.createElement("li");
        const code = document.createElement("span"); code.className = "code"; code.textContent = ev.airport;
        const type = document.createElement("span"); type.className = "type"; type.textContent = ev.type.replace(/_/g, " ");
        li.appendChild(code); li.appendChild(type);
        const detail = [ev.reason, ev.average ? "avg " + ev.average : null, ev.direction ? ev.direction.toLowerCase() : null].filter(Boolean).join(" · ");
        if (detail) li.appendChild(document.createTextNode(" — " + detail));
        list.appendChild(li);
      });
      if (items.length > 12) { const li = document.createElement("li"); li.className = "muted"; li.textContent = "+" + (items.length - 12) + " more airports with active events"; list.appendChild(li); }
    }).catch(() => { const list = $("live-list"); list.textContent = ""; const li = document.createElement("li"); li.className = "muted"; li.textContent = "FAA live status feed is unavailable right now."; list.appendChild(li); });
  }

  function renderDataCard(h) {
    const list = $("data-list"); list.textContent = "";
    const src = h.sources || {};
    const rows = [
      ["FAA enplanements", src.faa_enplanements && src.faa_enplanements.vintage],
      ["FAA TAF", src.taf && src.taf.period],
      ["BTS delay causes", src.bts_delay_cause && src.bts_delay_cause.period],
      ["BTS routes / taxi-out", src.bts_ontime && src.bts_ontime.period],
      ["Airports & runways", src.ourairports && src.ourairports.vintage],
      ["Scored universe", h.universe_size + " airports"],
      ["Answer engine", h.provider === "rules" ? "rules-based" : h.model + " via " + h.provider],
    ];
    rows.forEach(([k, v]) => {
      const li = document.createElement("li"); const kk = document.createElement("span"); kk.className = "k"; kk.textContent = k;
      const vv = document.createElement("span"); vv.className = "v"; vv.textContent = v || "unavailable"; li.appendChild(kk); li.appendChild(vv); list.appendChild(li);
    });
  }

  const WEIGHT_LABELS = { forecast_growth: "Forecast growth", demand_momentum: "Demand momentum", capacity_pressure: "Capacity pressure", scale: "Scale" };
  function renderWeights(weights) {
    const box = $("weights"); box.textContent = "";
    Object.keys(WEIGHT_LABELS).forEach((key) => {
      if (weights[key] == null) return;
      const pct = Math.round(weights[key] * 100);
      const row = document.createElement("div"); row.className = "w";
      const l = document.createElement("span"); l.textContent = WEIGHT_LABELS[key];
      const track = document.createElement("div"); track.className = "track"; const fill = document.createElement("div"); fill.className = "fill"; fill.style.width = pct + "%"; track.appendChild(fill);
      const v = document.createElement("span"); v.textContent = pct + "%";
      row.appendChild(l); row.appendChild(track); row.appendChild(v); box.appendChild(row);
    });
  }

  loadRegions().then(loadTop);
  loadLive();
  setInterval(loadLive, 5 * 60 * 1000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") loadLive(); });

  addMessage("assistant", "Hello. I screen US airports for modernization and expansion opportunities using FAA enplanement and forecast data, BTS delay statistics, runway and slot data. Ask a question or pick a suggestion below. I will always show my sources and what the data cannot tell you.", null);
})();
