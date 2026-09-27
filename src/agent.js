const fs = require("node:fs");
const path = require("node:path");
const {
  compareCongestion,
  demandPressure,
  longHaulShare,
  rankNewEnglandAirports,
} = require("./analytics");
const { loadAirportCoordinates, loadFaaEnplanements } = require("./data-sources");

const DEMO = JSON.parse(fs.readFileSync(path.join(__dirname, "../data/demo-indicators.json"), "utf8"));
const INTENTS = ["new_england_expansion", "la_congestion", "anc_long_haul", "sfo_unmet_demand"];
const MIN_ANNUAL_ENPLANEMENTS = 100000;

function isExpansionCandidate(airport) {
  return ["P", "CS"].includes(airport.serviceLevel)
    && Number.isFinite(airport.passengerVolume)
    && airport.passengerVolume >= MIN_ANNUAL_ENPLANEMENTS;
}

function classifyLocally(question, previousIntent) {
  const text = question.toLowerCase();
  if (/new england|terminal expansion|expansion candidate|investment candidate/.test(text)) return "new_england_expansion";
  if (/\blax\b|\bsna\b|santa ana|los angeles|la airport/.test(text)) return "la_congestion";
  if (/\banc\b|anchorage|long[- ]haul/.test(text)) return "anc_long_haul";
  if (/\bsfo\b|san francisco|unmet demand|unmet flight/.test(text)) return "sfo_unmet_demand";
  if (previousIntent && /\b(why|explain|more|detail|what about|break that down|how so)\b/.test(text)) return previousIntent;
  return null;
}

async function classifyWithModel(question, previousIntent) {
  if (!process.env.OPENAI_API_KEY) return null;
  try {
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL || "gpt-4o-mini",
        temperature: 0,
        response_format: { type: "json_object" },
        messages: [
          { role: "system", content: `Classify the user message into exactly one intent: ${INTENTS.join(", ")}, or null if unrelated. Never calculate or invent data. For a follow-up, reuse the previous intent: ${previousIntent || "none"}. Return JSON only: {"intent":"..."}.` },
          { role: "user", content: question },
        ],
      }),
      signal: AbortSignal.timeout(7000),
    });
    if (!response.ok) return null;
    const payload = await response.json();
    const result = JSON.parse(payload.choices?.[0]?.message?.content ?? "{}");
    return INTENTS.includes(result.intent) ? result.intent : null;
  } catch {
    return null;
  }
}

function makeDataSource(name, url, mode, note) {
  return { name, url, mode, note };
}

function analyzeNewEngland(report) {
  const airports = report.airports.filter(isExpansionCandidate);
  const metrics = Object.fromEntries(airports.map((airport) => [airport.airportCode, airport]));
  const ranked = rankNewEnglandAirports(airports, metrics);
  return {
    intent: "new_england_expansion",
    title: "New England terminal-expansion shortlist",
    period: `${report.previousYear} to ${report.latestYear}${report.preliminary ? " (latest year preliminary)" : ""}`,
    summary: ranked.length
      ? `Ranked ${ranked.length} primary or commercial-service airports with at least 100,000 annual enplanements across CT, ME, MA, NH, RI, and VT. Score: passenger growth (65%) and passenger volume (35%).`
      : "No New England airports had comparable enplanement data in the selected dataset.",
    results: ranked.map((item) => ({
      code: item.airport.airportCode,
      airport: item.airport.name,
      city: item.airport.city,
      state: item.airport.stateCode,
      score: item.score,
      growthPct: item.metrics.growthPct,
      enplanements: item.metrics.passengerVolume,
      growthComponent: item.components.growthPct,
      scaleComponent: item.components.passengerVolume,
    })),
    source: makeDataSource(
      "FAA Airport Enplanement Data",
      report.datasetUrl,
      report.preliminary ? "LIVE · PRELIMINARY" : "LIVE · FINAL",
      `Retrieved ${new Date(report.fetchedAt).toLocaleDateString()}; published FAA airport totals.`,
    ),
    limitation: "This is a screening shortlist, not proof of terminal capacity constraints or project ROI. The score compares only growth and passenger scale; it does not include terminal capacity, local demand, costs, or community impacts.",
  };
}

function analyzeDemoIntent(intent, coordinates = DEMO.airportCoordinates) {
  if (intent === "la_congestion") {
    const results = compareCongestion(DEMO.congestion, ["LAX", "SNA"]);
    return {
      intent,
      title: "LAX and SNA congestion comparison",
      period: DEMO.period,
      summary: results.map((item) => `${item.airportCode}: ${item.delayRatePct}% delayed operations and ${item.averageDelayMinutes} average delay minutes.`).join(" "),
      results,
      source: makeDataSource("Bundled illustrative data", "", "DEMO", DEMO.label),
      limitation: "The counts and delay measures are synthetic placeholders for demonstrating the calculation. A production comparison must use BTS airport-level on-time records from matching months and define its delay threshold.",
    };
  }

  if (intent === "anc_long_haul") {
    const result = longHaulShare(DEMO.ancSegments, coordinates);
    return {
      intent,
      title: "Long-haul share from Anchorage (ANC)",
      period: DEMO.period,
      summary: `${result.longHaulFlights} of ${result.totalFlights} demonstration flights meet the ${result.thresholdMiles.toLocaleString()}-mile long-haul definition (${result.percentage}%).`,
      results: result.longHaulRoutes,
      metric: result,
      source: makeDataSource("Bundled illustrative routes; OurAirports coordinates when available", "https://ourairports.com/data/", "DEMO", DEMO.label),
      limitation: "Route frequencies are synthetic placeholders. Distances are great-circle miles from airport coordinates; long-haul means at least 3,000 miles. This is not a measured share of current scheduled flights.",
    };
  }

  if (intent === "sfo_unmet_demand") {
    const result = demandPressure(DEMO.sfoPressure);
    return {
      intent,
      title: "SFO capacity-pressure screen",
      period: DEMO.period,
      summary: `The illustrative pressure score is ${result.score}/100, composed from load factor (55%), delay rate (30%), and cancellation rate (15%).`,
      metric: result,
      results: [{ airportCode: "SFO", ...DEMO.sfoPressure }],
      source: makeDataSource("Bundled illustrative indicators", "", "DEMO", DEMO.label),
      limitation: "This score is not a count or estimate of travelers who could not book a flight. Public schedule, delay, and load-factor indicators can flag pressure, but do not reveal unserved booking requests or their causes.",
    };
  }

  return {
    intent: "new_england_expansion",
    title: "New England terminal-expansion shortlist",
    period: DEMO.period,
    summary: "FAA data is unavailable, so this is a demonstration-only shortlist.",
    results: rankNewEnglandAirports(DEMO.newEngland, Object.fromEntries(DEMO.newEngland.map((airport) => [airport.airportCode, airport]))).map((item) => ({
      code: item.airport.airportCode,
      airport: item.airport.name,
      city: item.airport.city,
      state: item.airport.stateCode,
      score: item.score,
      growthPct: item.metrics.growthPct,
      enplanements: item.metrics.passengerVolume,
      growthComponent: item.components.growthPct,
      scaleComponent: item.components.passengerVolume,
    })),
    source: makeDataSource("Bundled illustrative data", "", "DEMO", DEMO.label),
    limitation: "These values are synthetic placeholders, not observed FAA traffic. The shortlist is only for demonstrating the ranking method; it does not establish expansion need or project ROI.",
  };
}

async function answerQuestion(question, previousIntent = null) {
  const localIntent = classifyLocally(question, previousIntent);
  const intent = await classifyWithModel(question, previousIntent) || localIntent;
  if (!intent) {
    return {
      intent: null,
      title: "Choose an airport question",
      summary: "I can rank New England expansion candidates, compare LAX and SNA congestion, calculate ANC's long-haul share, or screen SFO capacity pressure.",
      results: [],
      source: null,
      limitation: "Ask one of the four airport questions from the brief, or follow up on the current result.",
    };
  }

  if (intent === "new_england_expansion") {
    try {
      return analyzeNewEngland(await loadFaaEnplanements());
    } catch {
      return analyzeDemoIntent(intent);
    }
  }
  if (intent === "anc_long_haul") {
    try {
      const liveCoordinates = await loadAirportCoordinates();
      const requiredCodes = ["ANC", ...new Set(DEMO.ancSegments.map((segment) => segment.destination))];
      const selectedCoordinates = Object.fromEntries(requiredCodes.filter((code) => liveCoordinates[code]).map((code) => [code, liveCoordinates[code]]));
      return analyzeDemoIntent(intent, Object.keys(selectedCoordinates).length === requiredCodes.length ? selectedCoordinates : DEMO.airportCoordinates);
    } catch {
      return analyzeDemoIntent(intent);
    }
  }
  return analyzeDemoIntent(intent);
}

module.exports = { answerQuestion, classifyLocally, isExpansionCandidate };
