const fs = require("node:fs");
const path = require("node:path");
const {
  compareAirports,
  compareCongestion,
  demandPressure,
  filterAirports,
  longHaulShare,
  rankAirports,
  rankInvestmentCandidates,
} = require("./analytics");
const { loadAirportCoordinates, loadFaaEnplanements } = require("./data-sources");

const DEMO = JSON.parse(fs.readFileSync(path.join(__dirname, "../data/demo-indicators.json"), "utf8"));
const MIN_EXPANSION_ENPLANEMENTS = 100000;
const STATES = {
  alabama: "AL", alaska: "AK", arizona: "AZ", arkansas: "AR", california: "CA", colorado: "CO",
  connecticut: "CT", delaware: "DE", florida: "FL", georgia: "GA", hawaii: "HI", idaho: "ID",
  illinois: "IL", indiana: "IN", iowa: "IA", kansas: "KS", kentucky: "KY", louisiana: "LA",
  maine: "ME", maryland: "MD", massachusetts: "MA", michigan: "MI", minnesota: "MN",
  mississippi: "MS", missouri: "MO", montana: "MT", nebraska: "NE", nevada: "NV",
  "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
  "north carolina": "NC", "north dakota": "ND", ohio: "OH", oklahoma: "OK", oregon: "OR",
  pennsylvania: "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
  tennessee: "TN", texas: "TX", utah: "UT", vermont: "VT", virginia: "VA", washington: "WA",
  "west virginia": "WV", wisconsin: "WI", wyoming: "WY",
};
const REGIONS = {
  "new england": ["CT", "ME", "MA", "NH", "RI", "VT"],
  northeast: ["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"],
  "west coast": ["CA", "OR", "WA"],
  midwest: ["IL", "IN", "IA", "KS", "MI", "MN", "MO", "NE", "ND", "OH", "SD", "WI"],
  southeast: ["AL", "AR", "FL", "GA", "KY", "LA", "MS", "NC", "SC", "TN", "VA", "WV"],
  southwest: ["AZ", "NM", "OK", "TX"],
};

function isExpansionCandidate(airport) {
  return ["P", "CS"].includes(airport.serviceLevel)
    && Number.isFinite(airport.passengerVolume)
    && airport.passengerVolume >= MIN_EXPANSION_ENPLANEMENTS;
}

function extractStateCodes(text) {
  const normalized = text.toLowerCase();
  for (const [region, codes] of Object.entries(REGIONS)) {
    if (normalized.includes(region)) return [...codes];
  }
  const codes = new Set();
  for (const [name, code] of Object.entries(STATES)) {
    if (new RegExp(`\\b${name.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&")}\\b`, "i").test(text)) codes.add(code);
  }
  for (const match of text.matchAll(/\b([A-Z]{2})\b/g)) {
    if (Object.values(STATES).includes(match[1])) codes.add(match[1]);
  }
  return [...codes];
}

function resolveAirportMentions(text, airports, context = {}) {
  const matches = new Map();
  const commonWords = new Set(["ALL", "AND", "ANY", "ARE", "BUT", "CAN", "FOR", "HAS", "HER", "HIS", "HOW", "ITS", "NEW", "NOT", "NOW", "OUR", "OUT", "THE", "TOO", "TWO", "USE", "WAS", "WHO", "WHY", "YES", "YOU"]);
  const codes = [...text.matchAll(/\b([A-Z0-9]{3,4})\b/gi)]
    .map((match) => match[1].toUpperCase())
    .filter((code) => !commonWords.has(code));
  for (const code of codes) {
    const airport = airports.find((candidate) => candidate.airportCode.toUpperCase() === code);
    if (airport) matches.set(airport.airportCode, airport);
  }

  const normalized = text.toLowerCase();
  for (const airport of airports) {
    const candidates = [airport.city, airport.name].filter(Boolean);
    if (candidates.some((candidate) => candidate.length > 3 && normalized.includes(candidate.toLowerCase()))) {
      matches.set(airport.airportCode, airport);
    }
  }

  return [...matches.values()];
}

function extractPassengerFloor(text) {
  const match = text.match(/\b(?:at least|over|more than|minimum(?: of)?)\s+([\d,.]+)\s*(million|m|thousand|k)?\s*(?:annual\s+)?(?:passengers|enplanements|boardings)?\b/i);
  if (!match) return 0;
  const value = Number(match[1].replaceAll(",", ""));
  if (!Number.isFinite(value)) return 0;
  const unit = (match[2] || "").toLowerCase();
  return Math.round(value * (unit === "million" || unit === "m" ? 1_000_000 : unit === "thousand" || unit === "k" ? 1_000 : 1));
}

function parseAirportQuery(question, airports, context = {}, history = []) {
  const text = question.toLowerCase();
  const stateCodes = extractStateCodes(question);
  const airportMentions = resolveAirportMentions(question, airports, context);
  const metric = /growth|grow|fastest growing|year.over.year|yoy|change/.test(text)
    ? "growthPct"
    : "passengerVolume";

  if (context.kind === "rank_airports" && /\b(why|how did|explain|what drove)\b/.test(text)) {
    return { kind: "explain_ranking", metric: context.metric, stateCodes: context.stateCodes || [], airportCodes: context.airportCodes || [], limit: context.limit || 5, expansion: context.expansion || false };
  }
  if (context.kind === "rank_airports" && /\b(growth|passengers|enplanements|sort|rank|same region|same states)\b/.test(text)) {
    const changedGeography = stateCodes.some((code) => !(context.stateCodes || []).includes(code));
    return {
      ...context,
      kind: "rank_airports",
      metric,
      stateCodes: stateCodes.length ? stateCodes : context.stateCodes || [],
      onlyAirportCodes: !changedGeography,
      minimumPassengers: extractPassengerFloor(question) || context.minimumPassengers || 0,
    };
  }
  if (airportMentions.length === 0 && context.airportCodes?.length) {
    const ordinals = { first: 0, "1st": 0, second: 1, "2nd": 1, third: 2, "3rd": 2, fourth: 3, "4th": 3, fifth: 4, "5th": 4, last: context.airportCodes.length - 1 };
    const ordinalMentions = [...text.matchAll(/\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last)\b/g)];
    if (context.kind === "rank_airports" && ordinalMentions.length > 1) {
      const codes = ordinalMentions.map((match) => context.airportCodes[ordinals[match[1]]]).filter(Boolean);
      return { kind: "compare_airports", metric, airportCodes: [...new Set(codes)], stateCodes };
    }
    const ordinalMatch = text.match(/\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last)\b/);
    if (ordinalMatch) {
      const selected = context.airportCodes[ordinals[ordinalMatch[1]]];
      if (selected) return { kind: "airport_profile", metric, stateCodes, airportCodes: [selected] };
    }
  }

  if (/long[- ]haul|long distance/.test(text) && /flight|route/.test(text)) {
    return { kind: "anc_long_haul", metric, stateCodes, airportCodes: airportMentions.map((airport) => airport.airportCode) };
  }
  if (/congestion|delay|delays|on.time/.test(text) && /compare|versus|\bvs\b|\band\b/.test(text)) {
    return { kind: "la_congestion", metric, stateCodes, airportCodes: airportMentions.map((airport) => airport.airportCode) };
  }
  if (/unmet demand|unserved|could not book|couldn't book/.test(text)) {
    return { kind: "sfo_unmet_demand", metric, stateCodes, airportCodes: airportMentions.map((airport) => airport.airportCode) };
  }
  if (/\b(roi|return on investment|payback|project cost|construction cost|capital cost|moderni[sz]ation cost|terminal capacity|spare capacity|unused capacity|capacity utilization)\b/.test(text)) {
    return { kind: "investment_data_gap", metric, stateCodes, airportCodes: airportMentions.map((airport) => airport.airportCode) };
  }

  if (airportMentions.length > 1 && /\b(compare|versus|vs|against|difference)\b/.test(text)) {
    return { kind: "compare_airports", metric, stateCodes: [], airportCodes: airportMentions.map((airport) => airport.airportCode) };
  }

  const explicitComparison = /\b(compare|versus|vs|against|difference)\b/.test(text);
  const isRanking = !explicitComparison && /top|rank|busiest|most passengers|highest(?: passenger)? traffic|passenger.*traffic|enplanements|largest|fastest.growing|strong candidates|shortlist|best airports/.test(text);
  if (isRanking || (stateCodes.length > 0 && /airport|traffic|passenger|growth|rank/.test(text))) {
    const expansion = /expansion|investment|terminal|capital|opportunity/.test(text);
    return {
      kind: "rank_airports",
      metric,
      stateCodes: stateCodes.length ? stateCodes : context.stateCodes || [],
      airportCodes: [],
      limit: Number(text.match(/\btop\s+(\d{1,2})\b/)?.[1]) || context.limit || 5,
      minimumPassengers: extractPassengerFloor(question),
      expansion,
      previousKind: context.kind,
      historyLength: history.length,
    };
  }

  if (context.kind === "compare_airports" && airportMentions.length === 1 && /\b(compare|add|also|too|include|and|what about)\b/.test(text)) {
    return { ...context, kind: "compare_airports", airportCodes: [...new Set([...(context.airportCodes || []), ...airportMentions.map((airport) => airport.airportCode)])] };
  }
  if (airportMentions.length > 1 || (airportMentions.length === 1 && /compare|versus|\bvs\b|against|difference/.test(text))) {
    return { kind: "compare_airports", metric, stateCodes, airportCodes: airportMentions.map((airport) => airport.airportCode) };
  }
  if (context.kind === "compare_airports" && /\b(those|them|same airports|by growth|by passengers|instead)\b/.test(text)) {
    return { ...context, kind: "compare_airports", metric };
  }
  if (context.kind === "airport_profile" && /\b(it|that airport|there|tell me more|more about it)\b/.test(text)) {
    return { ...context, kind: "airport_profile" };
  }
  if (airportMentions.length === 1) {
    return { kind: "airport_profile", metric, stateCodes, airportCodes: [airportMentions[0].airportCode] };
  }
  if (context.kind === "rank_airports" && stateCodes.length > 0) {
    return { ...context, stateCodes, kind: "rank_airports", metric: context.metric || metric };
  }
  return { kind: "clarify", metric, stateCodes, airportCodes: [] };
}

async function classifyWithModel(question, history, context, airports) {
  if (!process.env.OPENAI_API_KEY) return null;
  try {
    const recentTurns = history.slice(-8).map(({ role, content }) => ({ role, content: String(content).slice(0, 1000) }));
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL || "gpt-4o-mini",
        temperature: 0,
        response_format: { type: "json_object" },
        messages: [
          { role: "system", content: `Plan one airport query using only these fields: kind (rank_airports, compare_airports, airport_profile, anc_long_haul, la_congestion, sfo_unmet_demand, clarify), metric (passengerVolume or growthPct), stateCodes, airportCodes, limit, expansion. Supported airport identifiers include: ${airports.slice(0, 200).map((airport) => `${airport.airportCode}:${airport.city}`).join("; ")}. Use prior messages to resolve references such as "those", "the second one", or "what about it". Do not invent identifiers or numbers. Existing context: ${JSON.stringify(context || {})}. Return JSON only.` },
          ...recentTurns,
          { role: "user", content: question },
        ],
      }),
      signal: AbortSignal.timeout(7000),
    });
    if (!response.ok) return null;
    const payload = await response.json();
    const plan = JSON.parse(payload.choices?.[0]?.message?.content ?? "{}");
    const validKinds = new Set(["rank_airports", "compare_airports", "airport_profile", "anc_long_haul", "la_congestion", "sfo_unmet_demand", "clarify"]);
    return validKinds.has(plan.kind) ? { ...plan, stateCodes: Array.isArray(plan.stateCodes) ? plan.stateCodes : [], airportCodes: Array.isArray(plan.airportCodes) ? plan.airportCodes : [] } : null;
  } catch {
    return null;
  }
}

function sourceFor(report) {
  return {
    name: "FAA Airport Enplanement Data",
    url: report.datasetUrl,
    mode: report.preliminary ? "LIVE · PRELIMINARY" : "LIVE · FINAL",
    note: `Retrieved ${new Date(report.fetchedAt).toLocaleDateString()}.`,
  };
}

function airportResult(airport, reference = null) {
  return {
    airportCode: airport.airportCode,
    airport: airport.name,
    city: airport.city,
    state: airport.stateCode,
    serviceLevel: airport.serviceLevel,
    enplanements: airport.passengerVolume,
    growthPct: airport.growthPct,
    currentYear: airport.latestYear,
    previousYear: airport.previousYear,
    facilityType: reference?.facilityType || null,
    scheduledService: reference?.scheduledService ?? null,
    latitude: reference?.latitude ?? null,
    longitude: reference?.longitude ?? null,
  };
}

function answerFromFaa(plan, report, airportReference = {}) {
  const airportPool = report.airports.filter((airport) => ["P", "CS"].includes(airport.serviceLevel));
  const selectedPool = plan.onlyAirportCodes
    ? airportPool.filter((airport) => plan.airportCodes?.includes(airport.airportCode))
    : airportPool;
  const minimumPassengers = Math.max(plan.expansion ? MIN_EXPANSION_ENPLANEMENTS : 0, plan.minimumPassengers || 0);
  const filtered = filterAirports(selectedPool, { stateCodes: plan.stateCodes || [], minimumPassengers });
  const period = `${report.previousYear} to ${report.latestYear}${report.preliminary ? " (latest year preliminary)" : ""}`;
  const source = sourceFor(report);

  if (plan.kind === "rank_airports") {
    const ranked = plan.expansion && !plan.onlyAirportCodes
      ? rankInvestmentCandidates(filtered, Object.fromEntries(filtered.map((airport) => [airport.airportCode, airport])), plan.limit || 5)
      : rankAirports(filtered, { metric: plan.metric, limit: plan.limit || 5 });
    const label = plan.expansion
      ? "the expansion screening score (65% growth, 35% passenger scale)"
      : plan.metric === "growthPct" ? "year-over-year passenger growth" : "passenger enplanements";
    const newEnglandCodes = ["CT", "ME", "MA", "NH", "RI", "VT"];
    const isNewEngland = newEnglandCodes.every((code) => plan.stateCodes?.includes(code)) && plan.stateCodes.length === newEnglandCodes.length;
    const scope = isNewEngland
      ? " in New England (CT, ME, MA, NH, RI, and VT)"
      : plan.stateCodes?.length
        ? ` in ${plan.stateCodes.join(", ")}`
        : " across the FAA-reported U.S. airport set";
    return {
      intent: "rank_airports",
      title: plan.expansion ? "Airport expansion screening shortlist" : `Airports ranked by ${label}`,
      period,
      summary: ranked.length ? `Here are the top ${ranked.length}${scope}, ordered by ${label}${minimumPassengers ? `, with at least ${minimumPassengers.toLocaleString()} annual enplanements` : ""}.` : `No airports with comparable data were found${scope}.`,
      results: ranked.map((item) => plan.expansion ? {
        ...airportResult(item.airport),
        score: item.score,
        growthComponent: item.components.growthPct,
        scaleComponent: item.components.passengerVolume,
      } : airportResult(item)),
      source,
      limitation: plan.expansion
        ? `This relative screen uses growth (65%) and passenger scale (35%) among primary/commercial airports with at least ${MIN_EXPANSION_ENPLANEMENTS.toLocaleString()} enplanements. It does not establish capacity need, project feasibility, or ROI.`
        : "Enplanements count passenger boardings, not total arriving plus departing passengers. The newest FAA period may be preliminary; ranking does not imply unmet demand or investment suitability.",
      context: {
        kind: "rank_airports",
        metric: plan.metric,
        stateCodes: plan.stateCodes || [],
        limit: plan.limit || 5,
        expansion: Boolean(plan.expansion),
        minimumPassengers,
        airportCodes: ranked.map((item) => item.airport?.airportCode || item.airportCode),
      },
    };
  }

  if (plan.kind === "airport_profile") {
    const found = compareAirports(report.airports, plan.airportCodes || []).filter(Boolean);
    if (!found.length) return noDataAnswer("I couldn't identify that airport in the FAA enplanement dataset.");
    return {
      intent: "airport_profile",
      title: `${found[0].airportCode} airport snapshot`,
      period,
      summary: `${found[0].name} in ${found[0].city}, ${found[0].stateCode} recorded ${found[0].passengerVolume.toLocaleString()} enplanements in ${found[0].latestYear}, a ${found[0].growthPct >= 0 ? "+" : ""}${found[0].growthPct}% change from ${found[0].previousYear}.${airportReference[found[0].airportCode] ? ` It is classified as a ${airportReference[found[0].airportCode].facilityType?.replaceAll("_", " ") || "listed"} facility${airportReference[found[0].airportCode].scheduledService ? " with scheduled service" : ""}, at ${airportReference[found[0].airportCode].latitude.toFixed(3)}, ${airportReference[found[0].airportCode].longitude.toFixed(3)}.` : ""}`,
      results: found.map((airport) => airportResult(airport, airportReference[airport.airportCode])),
      source,
      limitation: "FAA provides annual passenger boardings, not capacity, route-by-route traffic, or financial performance. Facility classification and coordinates come from the community-maintained OurAirports reference.",
      context: { kind: "airport_profile", airportCodes: found.map((airport) => airport.airportCode) },
    };
  }

  if (plan.kind === "explain_ranking") {
    const selected = compareAirports(report.airports, plan.airportCodes || []).filter(Boolean);
    const names = selected.slice(0, 3).map((airport) => `${airport.airportCode} (${airport.growthPct >= 0 ? "+" : ""}${airport.growthPct}% growth; ${airport.passengerVolume.toLocaleString()} enplanements)`);
    return {
      intent: "explain_ranking",
      title: "How the ranking works",
      period,
      summary: plan.expansion
        ? `The screening score weights peer-group passenger growth at 65% and passenger scale at 35%, after min-max normalization. ${names.join("; ")}.`
        : `This list is sorted directly by ${plan.metric === "growthPct" ? "year-over-year growth" : "enplanements"}; it is not an investment score. ${names.join("; ")}.`,
      results: selected.map((airport) => airportResult(airport, airportReference[airport.airportCode])),
      source,
      limitation: "A change to geography, year, or eligibility filters can change the relative results.",
      context: plan,
    };
  }

  if (plan.kind === "compare_airports") {
    const found = compareAirports(report.airports, plan.airportCodes || []).filter(Boolean);
    const missing = (plan.airportCodes || []).filter((code) => !found.some((airport) => airport.airportCode === code));
    return {
      intent: "compare_airports",
      title: "Airport passenger comparison",
      period,
      summary: found.map((airport) => `${airport.airportCode} recorded ${airport.passengerVolume.toLocaleString()} enplanements (${airport.growthPct >= 0 ? "+" : ""}${airport.growthPct}%).`).join(" "),
      results: found.map(airportResult),
      source,
      limitation: missing.length ? `No matching FAA record was found for: ${missing.join(", ")}. ${"Enplanements are boardings and do not measure available capacity."}` : "Enplanements are passenger boardings and do not measure available capacity or congestion.",
      context: { kind: "compare_airports", airportCodes: found.map((airport) => airport.airportCode) },
    };
  }

  return noDataAnswer("I can rank airports by passengers or growth, compare airports, or show an airport snapshot. Which airport, state/region, or measure should I use?");
}

function noDataAnswer(summary) {
  return { intent: null, title: "Let's narrow that down", summary, results: [], source: null, limitation: "No numeric result is shown until the airport, geography, or measure is clear." };
}

function investmentDataGapAnswer(plan) {
  const airportLabel = plan.airportCodes?.length ? ` for ${plan.airportCodes.join(", ")}` : "";
  return {
    intent: "investment_data_gap",
    title: "Investment diligence data not available",
    summary: `I can't substantiate project ROI, modernization cost, or unused terminal capacity${airportLabel} from the current public datasets. I can still compare published enplanements and growth as a first-pass screen.`,
    results: [],
    source: null,
    limitation: "Do not treat passenger growth or delay proxies as an ROI or capacity estimate. A decision-grade case needs airport financials, terminal design capacity/throughput, project scope and cost, airline schedules, and demand forecasts.",
    context: { kind: "investment_data_gap", airportCodes: plan.airportCodes || [] },
  };
}

function analyzeDemoIntent(kind) {
  if (kind === "la_congestion") {
    const results = compareCongestion(DEMO.congestion, ["LAX", "SNA"]);
    return {
      intent: kind,
      title: "Illustrative congestion comparison",
      period: DEMO.period,
      summary: results.map((item) => `${item.airportCode}: ${item.delayRatePct}% delayed operations and ${item.averageDelayMinutes} average delay minutes.`).join(" "),
      results,
      source: { name: "Bundled illustrative inputs", url: "", mode: "DEMO", note: DEMO.label },
      limitation: "These operational values are synthetic, not reported observations. A production answer needs matched-period BTS records and a defined delay threshold.",
      context: { kind, airportCodes: ["LAX", "SNA"] },
    };
  }
  if (kind === "anc_long_haul") {
    const result = longHaulShare(DEMO.ancSegments, DEMO.airportCoordinates);
    return {
      intent: kind,
      title: "Illustrative ANC route-distance analysis",
      period: DEMO.period,
      summary: `${result.longHaulFlights} of ${result.totalFlights} demonstration flights meet the ${result.thresholdMiles.toLocaleString()}-mile definition (${result.percentage}%).`,
      results: result.longHaulRoutes,
      metric: result,
      source: { name: "Bundled illustrative routes and airport coordinates", url: "https://ourairports.com/data/", mode: "DEMO", note: DEMO.label },
      limitation: "Flight counts are synthetic. Long-haul means at least 3,000 great-circle miles; this is not a measured share of scheduled flights.",
      context: { kind, airportCodes: ["ANC"] },
    };
  }
  if (kind === "sfo_unmet_demand") {
    const result = demandPressure(DEMO.sfoPressure);
    return {
      intent: kind,
      title: "Illustrative SFO pressure indicator",
      period: DEMO.period,
      summary: `Illustrative pressure score: ${result.score}/100, using load factor, delays, and cancellations.`,
      metric: result,
      results: [{ airportCode: "SFO", ...DEMO.sfoPressure }],
      source: { name: "Bundled illustrative inputs", url: "", mode: "DEMO", note: DEMO.label },
      limitation: "This cannot estimate missed bookings. Public flight data does not reveal travelers who searched but could not book.",
      context: { kind, airportCodes: ["SFO"] },
    };
  }
}

async function answerQuestion(question, history = [], previousContext = null) {
  let report;
  try {
    report = await loadFaaEnplanements();
  } catch {
    report = null;
  }
  const airports = report?.airports || [];
  const localPlan = parseAirportQuery(question, airports, previousContext || {}, history);
  const modelPlan = report ? await classifyWithModel(question, history, previousContext, airports) : null;
  const plan = modelPlan || localPlan;

  if (plan.kind === "investment_data_gap") return investmentDataGapAnswer(plan);
  if (["la_congestion", "anc_long_haul", "sfo_unmet_demand"].includes(plan.kind)) return analyzeDemoIntent(plan.kind);
  if (report) {
    const airportReference = plan.kind === "airport_profile" || plan.kind === "explain_ranking"
      ? await loadAirportCoordinates().catch(() => ({}))
      : {};
    return answerFromFaa(plan, report, airportReference);
  }
  return noDataAnswer("FAA data is temporarily unavailable. Try again shortly; no substitute figures are being presented as live data.");
}

module.exports = { answerQuestion, extractPassengerFloor, extractStateCodes, isExpansionCandidate, parseAirportQuery, resolveAirportMentions };
