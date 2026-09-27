const form = document.querySelector("#question-form");
const input = document.querySelector("#question-input");
const conversation = document.querySelector("#conversation");
const sendButton = document.querySelector(".send-button");
const welcome = document.querySelector("#welcome-note");
const periodStatus = document.querySelector("#period-status");
const conversationHistory = [];
let conversationContext = null;

function addUserMessage(text) {
  const wrapper = document.createElement("div");
  wrapper.className = "message message-user";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  wrapper.append(paragraph);
  conversation.append(wrapper);
}

function appendCell(row, text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) cell.className = className;
  row.append(cell);
  return cell;
}

function formatNumber(value) {
  return Number.isFinite(value) ? new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value) : "—";
}

function appendResultsTable(answer, container) {
  if (!Array.isArray(answer.results) || answer.results.length === 0) return;
  const table = document.createElement("table");
  table.className = "results-table";
  const header = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const ranking = ["new_england_expansion", "rank_airports"].includes(answer.intent);
  const scoredRanking = answer.intent === "new_england_expansion";
  const labels = scoredRanking
    ? ["AIRPORT", "STATE", "ENPLANEMENTS", "GROWTH", "SCREEN SCORE"]
    : answer.intent === "rank_airports"
      ? ["AIRPORT", "STATE", "ENPLANEMENTS", "GROWTH", "SERVICE"]
    : answer.intent === "la_congestion"
      ? ["AIRPORT", "PERIOD", "OPERATIONS", "DELAYED", "DELAY RATE"]
      : answer.intent === "compare_airports"
        ? ["AIRPORT", "PERIOD", "ENPLANEMENTS", "CHANGE", "MEASURE"]
      : answer.intent === "anc_long_haul"
        ? ["ROUTE", "DISTANCE", "FLIGHTS"]
        : ["AIRPORT", "STATE", "ENPLANEMENTS", "GROWTH", "SERVICE"];
  for (const label of labels) {
    const cell = document.createElement("th");
    cell.textContent = label;
    headerRow.append(cell);
  }
  header.append(headerRow);
  const body = document.createElement("tbody");

  for (const result of answer.results) {
    const row = document.createElement("tr");
    if (scoredRanking) {
      appendCell(row, `${result.code}  ${result.airport}`, "result-code");
      appendCell(row, result.state);
      appendCell(row, formatNumber(result.enplanements));
      appendCell(row, `${formatNumber(result.growthPct)}%`);
      const score = appendCell(row, "");
      score.className = "score-cell";
      score.append(document.createTextNode(`${formatNumber(result.score)} / 100`));
      const bar = document.createElement("div");
      bar.className = "score-bar";
      const fill = document.createElement("i");
      fill.style.width = `${Math.max(0, Math.min(100, result.score))}%`;
      bar.append(fill);
      score.append(bar);
    } else if (ranking) {
      appendCell(row, `${result.airportCode}  ${result.airport}`, "result-code");
      appendCell(row, result.state);
      appendCell(row, formatNumber(result.enplanements));
      appendCell(row, `${formatNumber(result.growthPct)}%`);
      appendCell(row, result.serviceLevel);
    } else if (answer.intent === "la_congestion") {
      appendCell(row, result.airportCode, "result-code");
      appendCell(row, result.period);
      appendCell(row, formatNumber(result.operations));
      appendCell(row, formatNumber(result.delayedOperations));
      appendCell(row, `${formatNumber(result.delayRatePct)}%`);
    } else if (answer.intent === "compare_airports") {
      appendCell(row, result.airportCode, "result-code");
      appendCell(row, `${result.previousYear}–${result.currentYear}`);
      appendCell(row, formatNumber(result.enplanements));
      appendCell(row, `${formatNumber(result.growthPct)}%`);
      appendCell(row, "Passenger boardings");
    } else if (["airport_profile", "explain_ranking"].includes(answer.intent)) {
      appendCell(row, result.airportCode, "result-code");
      appendCell(row, result.state);
      appendCell(row, formatNumber(result.enplanements));
      appendCell(row, `${formatNumber(result.growthPct)}%`);
      appendCell(row, result.serviceLevel);
    } else if (answer.intent === "anc_long_haul") {
      appendCell(row, `${result.origin} → ${result.destination}`, "result-code");
      appendCell(row, `${formatNumber(result.distanceMiles)} mi`);
      appendCell(row, formatNumber(result.flightCount));
    } else {
      appendCell(row, result.airportCode, "result-code");
      appendCell(row, `${formatNumber(result.loadFactorPct)}%`);
      appendCell(row, `${formatNumber(result.delayRatePct)}%`);
      appendCell(row, `${formatNumber(result.cancellationRatePct)}%`);
    }
    body.append(row);
  }
  table.append(header, body);
  container.append(table);
}

function addAnswer(answer) {
  const wrapper = document.createElement("article");
  wrapper.className = "message message-assistant";
  const head = document.createElement("div");
  head.className = "answer-head";
  const title = document.createElement("h3");
  title.textContent = answer.title;
  head.append(title);
  if (answer.source) {
    const mode = document.createElement("span");
    mode.className = `mode-pill${answer.source.mode === "DEMO" ? " demo" : ""}`;
    mode.textContent = answer.source.mode;
    head.append(mode);
  }
  wrapper.append(head);

  if (answer.period) {
    const period = document.createElement("div");
    period.className = "period-line";
    period.textContent = `PERIOD  /  ${answer.period}`;
    wrapper.append(period);
  }

  const summary = document.createElement("p");
  summary.className = "answer-summary";
  summary.textContent = answer.summary;
  wrapper.append(summary);
  appendResultsTable(answer, wrapper);

  const limitation = document.createElement("p");
  limitation.className = "limitation";
  limitation.textContent = answer.limitation;
  wrapper.append(limitation);

  if (answer.source?.url) {
    const sourceLink = document.createElement("a");
    sourceLink.className = "source-link";
    sourceLink.href = answer.source.url;
    sourceLink.target = "_blank";
    sourceLink.rel = "noreferrer";
    sourceLink.textContent = `SOURCE  /  ${answer.source.name} ↗`;
    wrapper.append(sourceLink);
  } else if (answer.source) {
    const sourceNote = document.createElement("div");
    sourceNote.className = "source-link";
    sourceNote.textContent = `SOURCE  /  ${answer.source.name}`;
    wrapper.append(sourceNote);
  }
  conversation.append(wrapper);
  conversation.scrollTop = conversation.scrollHeight;
}

async function ask(question) {
  welcome.hidden = true;
  addUserMessage(question);
  conversationHistory.push({ role: "user", content: question });
  const typing = document.createElement("div");
  typing.className = "typing";
  typing.textContent = "Checking the evidence…";
  conversation.append(typing);
  sendButton.disabled = true;

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: conversationHistory.slice(-12), context: conversationContext }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "The question could not be processed.");
    conversationContext = payload.context || conversationContext;
    addAnswer(payload);
    conversationHistory.push({
      role: "assistant",
      content: JSON.stringify({ title: payload.title, summary: payload.summary, intent: payload.intent, context: payload.context, results: payload.results?.slice(0, 5) }),
    });
    if (payload.period) periodStatus.textContent = payload.period;
  } catch (error) {
    addAnswer({ title: "Analysis unavailable", summary: error.message, results: [], limitation: "The local server could not complete this request." });
  } finally {
    typing.remove();
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  input.style.height = "auto";
  ask(question);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
});

document.querySelectorAll(".prompt-button").forEach((button) => {
  button.addEventListener("click", () => ask(button.dataset.question));
});

fetch("/api/status")
  .then((response) => response.json())
  .then((status) => {
    document.querySelector("#data-status").textContent = "FAA traffic is fetched on query; three operational examples are illustrative.";
    if (status.llmEnabled) {
      document.querySelector("#ai-status").textContent = "OPTIONAL LLM";
      document.querySelector("#ai-dot").classList.add("live");
    }
  })
  .catch(() => {
    document.querySelector("#data-status").textContent = "Status check unavailable; live FAA data is fetched when queried.";
  });
