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

  if (/\b(time ?frame|date range|data period|which years|what years|how recent|when was .*data|source date)\b/.test(text)) {
    return { kind: "data_timeframe", metric, stateCodes, airportCodes: context.airportCodes || [] };
  }

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

const AI_TOOLS = [
  {
    type: "function",
    function: {
      name: "search_airports",
      description: "Search, filter, and rank airports using the latest FAA annual enplanements and year-over-year growth. Use for rankings and market screens.",
      parameters: {
        type: "object",
        properties: {
          states: { type: "array", items: { type: "string" }, description: "Two-letter state codes to include; empty means all reported states." },
          region: { type: "string", description: "A named U.S. region such as New England, Northeast, Midwest, Southeast, Southwest, or West Coast." },
          metric: { type: "string", enum: ["enplanements", "growth"], description: "The raw metric to sort by." },
          limit: { type: "integer", minimum: 1, maximum: 25 },
          minimum_enplanements: { type: "integer", minimum: 0, description: "Optional minimum annual passenger boardings to avoid small-base growth comparisons." },
          investment_screen: { type: "boolean", description: "Use the explicit exploratory growth/scale screening score, not a financial valuation." },
        },
        required: ["metric"],
        additionalProperties: false,
      },
    },
  },
  {
    type: "function",
    function: {
      name: "compare_airports",
      description: "Compare airports using the same annual FAA enplanement source and period.",
      parameters: { type: "object", properties: { airport_codes: { type: "array", items: { type: "string" }, minItems: 2, maxItems: 10 } }, required: ["airport_codes"], additionalProperties: false },
    },
  },
  {
    type: "function",
    function: {
      name: "airport_profile",
      description: "Retrieve FAA annual enplanements and matched public facility/coordinate reference for one or more airports.",
      parameters: { type: "object", properties: { airport_codes: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 5 } }, required: ["airport_codes"], additionalProperties: false },
    },
  },
  {
    type: "function",
    function: {
      name: "get_data_timeframe",
      description: "Return the currently loaded FAA dataset years, publication status, retrieval date, source URL, and enplanement definition. Use to answer timeframe/source/freshness follow-ups.",
      parameters: { type: "object", properties: {}, additionalProperties: false },
    },
  },
  {
    type: "function",
    function: {
      name: "get_investment_data_gaps",
      description: "Explain which project economics, capacity, or unmet-demand evidence is unavailable; never fabricate ROI or terminal capacity.",
      parameters: { type: "object", properties: { airport_codes: { type: "array", items: { type: "string" } }, question: { type: "string" } }, required: ["question"], additionalProperties: false },
    },
  },
  {
    type: "function",
    function: {
      name: "get_operational_example",
      description: "Return one of the illustrative operational examples. These inputs are synthetic and must always be described as DEMO, not observed data.",
      parameters: { type: "object", properties: { topic: { type: "string", enum: ["congestion", "long_haul", "demand_pressure"] } }, required: ["topic"], additionalProperties: false },
    },
  },
];

function getDataTimeframe(report) {
  return {
    intent: "data_timeframe",
    title: "FAA dataset timeframe",
    period: `${report.previousYear} to ${report.latestYear}${report.preliminary ? " (latest year preliminary)" : ""}`,
    summary: `The current FAA workbook compares calendar year ${report.previousYear} with calendar year ${report.latestYear}. ${report.latestYear} is ${report.preliminary ? "preliminary" : "final"}. Enplanements are passenger boardings, not total arriving plus departing passengers.`,
    results: [],
    source: sourceFor(report),
    limitation: `Retrieved ${new Date(report.fetchedAt).toLocaleDateString()}. The report's published dataset vintage may differ from today's date.`,
  };
}

async function executeAgentTool(name, args = {}) {
  if (name === "get_data_timeframe") return getDataTimeframe(await loadFaaEnplanements());
  if (name === "get_investment_data_gaps") {
    const plan = { airportCodes: Array.isArray(args.airport_codes) ? args.airport_codes.map((code) => String(code).toUpperCase()) : [] };
    return investmentDataGapAnswer(plan);
  }
  if (name === "get_operational_example") {
    const kinds = { congestion: "la_congestion", long_haul: "anc_long_haul", demand_pressure: "sfo_unmet_demand" };
    return analyzeDemoIntent(kinds[args.topic] || "la_congestion");
  }

  const report = await loadFaaEnplanements();
  const airportPool = report.airports.filter((airport) => ["P", "CS"].includes(airport.serviceLevel));
  const referenceCodes = Array.isArray(args.airport_codes) ? args.airport_codes.map((code) => String(code).trim().toUpperCase()) : [];
  const period = `${report.previousYear} to ${report.latestYear}${report.preliminary ? " (latest year preliminary)" : ""}`;

  if (name === "search_airports") {
    const regionCodes = args.region ? extractStateCodes(String(args.region)) : [];
    const states = Array.isArray(args.states) ? args.states.map((code) => String(code).toUpperCase()) : [];
    const stateCodes = [...new Set([...states, ...regionCodes])];
    const expansion = Boolean(args.investment_screen);
    const floor = Math.max(Number(args.minimum_enplanements) || 0, expansion ? MIN_EXPANSION_ENPLANEMENTS : 0);
    const filtered = filterAirports(airportPool, { stateCodes, minimumPassengers: floor });
    const limit = Math.min(25, Math.max(1, Number(args.limit) || 10));
    const metric = args.metric === "growth" ? "growthPct" : "passengerVolume";
    const ranked = expansion
      ? rankInvestmentCandidates(filtered, Object.fromEntries(filtered.map((airport) => [airport.airportCode, airport])), limit)
      : rankAirports(filtered, { metric, limit });
    const rows = ranked.map((item) => expansion
      ? { ...airportResult(item.airport), score: item.score, growthComponent: item.components.growthPct, scaleComponent: item.components.passengerVolume }
      : airportResult(item));
    const source = sourceFor(report);
    return {
      intent: "rank_airports",
      title: expansion ? "Airport expansion screening shortlist" : `Airport ranking by ${metric === "growthPct" ? "passenger growth" : "enplanements"}`,
      period,
      results: rows,
      source,
      limitation: expansion
        ? "Exploratory peer-relative screen only: growth (65%) plus passenger scale (35%). It does not establish capacity need, project feasibility, or ROI."
        : "Enplanements mean passenger boardings. The latest year may be preliminary; passenger volume or growth alone does not prove investment suitability.",
      context: { kind: "rank_airports", metric, stateCodes, limit, expansion, minimumPassengers: floor, airportCodes: rows.map((row) => row.airportCode) },
    };
  }

  if (name === "compare_airports" || name === "airport_profile") {
    const found = compareAirports(report.airports, referenceCodes).filter(Boolean);
    const missing = referenceCodes.filter((code) => !found.some((airport) => airport.airportCode === code));
    const reference = await loadAirportCoordinates().catch(() => ({}));
    const rows = found.map((airport) => airportResult(airport, reference[airport.airportCode]));
    return {
      intent: name,
      title: name === "airport_profile" ? "Airport snapshot" : "Airport passenger comparison",
      period,
      results: rows,
      source: sourceFor(report),
      limitation: `${missing.length ? `No FAA record found for ${missing.join(", ")}. ` : ""}Annual enplanements are boardings, not capacity, route-level traffic, or financial performance. Facility details are cross-referenced from OurAirports.`,
      context: { kind: name, airportCodes: found.map((airport) => airport.airportCode) },
    };
  }
  throw new Error(`Unsupported data tool: ${name}`);
}

function getModelHistory(history = []) {
  return history
    .filter((turn) => ["user", "assistant"].includes(turn.role) && typeof turn.content === "string")
    .slice(-12)
    .map((turn) => ({ role: turn.role, content: turn.content.slice(0, 3000) }));
}

async function requestModel(messages, tools = AI_TOOLS) {
  const baseUrl = (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL || "gpt-4o-mini",
      temperature: 0.2,
      messages,
      tools,
      tool_choice: "auto",
    }),
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new Error(`AI provider returned HTTP ${response.status}. Check the local provider settings and API key.`);
  return response.json();
}
