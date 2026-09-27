/* Chat client: talks to /api/chat, renders answers safely, optional voice in/out. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const messagesEl = $("messages"), inputEl = $("input"), sendBtn = $("send"), micBtn = $("mic"), speakBtn = $("speak");
  const template = $("msg-template");
  let sessionId = sessionStorage.getItem("aiia.session") || (window.crypto && crypto.randomUUID ? crypto.randomUUID() : null);
  if (sessionId) sessionStorage.setItem("aiia.session", sessionId);
  let speakEnabled = false;

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
        const body = rows.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r.replace(/\|/g, "").trim()) || !/^[\s|:-]+$/.test(r));
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
        if (conf) badges.appendChild(pill("confidence: " + conf, conf === "high" ? "pill-ok" : "pill-warn"));
        renderSources(node.querySelector(".sources-panel .panel-body"), meta);
        node.querySelector(".data-json").textContent = meta.tool_results && meta.tool_results.length ? JSON.stringify(meta.tool_results, null, 2) : "No tool was needed for this answer.";
        (meta.warnings || []).forEach((w) => { const d = document.createElement("div"); d.className = "warning"; d.textContent = "⚠ " + w; body.appendChild(d); });
      } else { node.querySelector(".sources-panel").remove(); node.querySelector(".data-panel").remove(); }
    }
    messagesEl.appendChild(node);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return node;
  }

  function topConfidence(results) {
    if (!results || !results.length) return null;
    const order = { high: 0, medium: 1, low: 2 };
    let worst = null;
    results.forEach((r) => { const l = r.confidence && r.confidence.level; if (l && (worst === null || order[l] > order[worst])) worst = l; });
    return worst;
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
    if (!message) return;
    inputEl.value = "";
    addMessage("user", message);
    sendBtn.disabled = true;
    const pending = addMessage("assistant", "Working… fetching FAA/BTS data and computing scores.");
    pending.classList.add("pending");
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId }) });
      const data = await res.json();
      pending.remove();
      if (!res.ok) { addMessage("assistant", "Request rejected: " + (data.detail && JSON.stringify(data.detail)), null); return; }
      sessionId = data.session_id; sessionStorage.setItem("aiia.session", sessionId);
      addMessage("assistant", data.text, data);
      speak(data.text);
    } catch (err) {
      pending.remove();
      addMessage("assistant", "The server could not be reached: " + err.message, null);
    } finally { sendBtn.disabled = false; inputEl.focus(); }
  }
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  $("chips").addEventListener("click", (e) => { const q = e.target && e.target.getAttribute("data-q"); if (q) { inputEl.value = q; send(); } });

  // ---------- health ----------
  fetch("/api/health").then((r) => r.json()).then((h) => {
    const p = $("provider-pill");
    p.textContent = h.provider === "rules" ? "rules-based (no LLM configured)" : "LLM: " + h.model + " via " + h.provider;
    p.className = "pill " + (h.provider === "rules" ? "pill-rules" : "pill-llm");
    const faa = h.sources && h.sources.faa_enplanements;
    const delay = h.sources && h.sources.bts_delay_cause;
    $("data-pill").textContent = [faa && faa.vintage ? "FAA " + faa.vintage : null, delay && delay.period ? "BTS " + delay.period : null, h.universe_size + " airports scored"].filter(Boolean).join(" · ");
  }).catch(() => { $("provider-pill").textContent = "server unavailable"; });

  addMessage("assistant", "Hello. I screen US airports for modernization and expansion opportunities using FAA enplanement and forecast data, BTS delay statistics, runway and slot data. Ask a question or pick a suggestion below. I will always show my sources and what the data cannot tell you.", null);
})();
