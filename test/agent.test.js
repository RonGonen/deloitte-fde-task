const test = require("node:test");
const assert = require("node:assert/strict");
const { answerQuestion, extractPassengerFloor, extractStateCodes, isExpansionCandidate, parseAirportQuery, runAiConversation } = require("../src/agent");

const AIRPORTS = [
  { airportCode: "BOS", stateCode: "MA", city: "Boston", name: "Boston Logan International" },
  { airportCode: "BDL", stateCode: "CT", city: "Windsor Locks", name: "Bradley International" },
  { airportCode: "SFO", stateCode: "CA", city: "San Francisco", name: "San Francisco International" },
  { airportCode: "LAX", stateCode: "CA", city: "Los Angeles", name: "Los Angeles International" },
  { airportCode: "SEA", stateCode: "WA", city: "Seattle", name: "Seattle-Tacoma International" },
];

test("planner ranks airports for arbitrary states and supported measures", () => {
  const plan = parseAirportQuery("Show me the fastest-growing airports in California", AIRPORTS);
  assert.equal(plan.kind, "rank_airports");
  assert.equal(plan.metric, "growthPct");
  assert.deepEqual(plan.stateCodes, ["CA"]);
  assert.deepEqual(extractStateCodes("airports in New England"), ["CT", "ME", "MA", "NH", "RI", "VT"]);
  assert.equal(parseAirportQuery("Which airports have the highest passenger traffic?", AIRPORTS).kind, "rank_airports");
  assert.equal(parseAirportQuery("tell me about sfo", AIRPORTS).kind, "airport_profile");
  assert.equal(extractPassengerFloor("at least 100,000 annual enplanements"), 100000);
  assert.equal(extractPassengerFloor("over 1.5 million passengers"), 1500000);
  assert.equal(parseAirportQuery("Top 10 airports in California with at least 1 million passengers", AIRPORTS).minimumPassengers, 1000000);
  assert.equal(parseAirportQuery("What is the ROI for modernizing BOS?", AIRPORTS).kind, "investment_data_gap");
});

test("planner compares named airports and resolves a contextual ordinal", () => {
  const comparison = parseAirportQuery("Compare BOS with LAX", AIRPORTS);
  assert.equal(comparison.kind, "compare_airports");
  assert.deepEqual(comparison.airportCodes, ["BOS", "LAX"]);
  const stateCodeCollision = parseAirportQuery("Compare BOS and SEA passenger traffic", AIRPORTS);
  assert.equal(stateCodeCollision.kind, "compare_airports");
  assert.deepEqual(stateCodeCollision.airportCodes, ["BOS", "SEA"]);
  const followUp = parseAirportQuery("Tell me about the second one", AIRPORTS, { kind: "rank_airports", airportCodes: ["SEA", "SFO"] });
  assert.equal(followUp.kind, "airport_profile");
  assert.deepEqual(followUp.airportCodes, ["SFO"]);
  const addAirport = parseAirportQuery("And compare BOS too", AIRPORTS, { kind: "compare_airports", airportCodes: ["SFO", "LAX"] });
  assert.equal(addAirport.kind, "compare_airports");
  assert.deepEqual(addAirport.airportCodes, ["SFO", "LAX", "BOS"]);
  assert.deepEqual(parseAirportQuery("And compare SFO too", AIRPORTS, { kind: "compare_airports", airportCodes: ["BOS", "SEA"] }).airportCodes, ["BOS", "SEA", "SFO"]);
  assert.equal(parseAirportQuery("Tell me about LAX", AIRPORTS, { kind: "compare_airports", airportCodes: ["BOS", "LAX"] }).kind, "airport_profile");
  const continueProfile = parseAirportQuery("Tell me more about it", AIRPORTS, { kind: "airport_profile", airportCodes: ["BOS"] });
  assert.equal(continueProfile.kind, "airport_profile");
  assert.deepEqual(continueProfile.airportCodes, ["BOS"]);
  const reRank = parseAirportQuery("Sort those by growth instead", AIRPORTS, { kind: "rank_airports", metric: "passengerVolume", stateCodes: ["CA"], airportCodes: ["SFO", "LAX"] });
  assert.equal(reRank.kind, "rank_airports");
  assert.equal(reRank.metric, "growthPct");
  assert.deepEqual(reRank.stateCodes, ["CA"]);
  assert.equal(reRank.onlyAirportCodes, true);
  const changeRegion = parseAirportQuery("Rank fastest-growing airports in Oregon", AIRPORTS, { kind: "rank_airports", metric: "passengerVolume", stateCodes: ["CA"], airportCodes: ["SFO", "LAX"] });
  assert.deepEqual(changeRegion.stateCodes, ["OR"]);
  assert.equal(changeRegion.onlyAirportCodes, false);
  const compareRanked = parseAirportQuery("Compare the first and second", AIRPORTS, { kind: "rank_airports", airportCodes: ["SEA", "SFO"] });
  assert.equal(compareRanked.kind, "compare_airports");
  assert.deepEqual(compareRanked.airportCodes, ["SEA", "SFO"]);
});

test("planner keeps operational sample workflows explicitly synthetic", async () => {
  const comparison = await answerQuestion("Compare LAX and SNA congestion levels.");
  assert.equal(comparison.source.mode, "DEMO");
  assert.match(comparison.limitation, /synthetic/);
  const demand = await answerQuestion("What is unmet demand at SFO?");
  assert.match(demand.limitation, /cannot estimate missed bookings/);
});

test("expansion ranking excludes general aviation and very low-volume facilities", () => {
  assert.equal(isExpansionCandidate({ serviceLevel: "GA", passengerVolume: 500000 }), false);
  assert.equal(isExpansionCandidate({ serviceLevel: "P", passengerVolume: 19914 }), false);
  assert.equal(isExpansionCandidate({ serviceLevel: "P", passengerVolume: 100000 }), true);
});

test("investor returns and capacity requests are explicit data gaps, not airport snapshots", async () => {
  const answer = await answerQuestion("What is the return on investment for a BOS terminal upgrade?");
  assert.equal(answer.intent, "investment_data_gap");
  assert.match(answer.limitation, /decision-grade case needs airport financials/);
  assert.equal(answer.results.length, 0);
});

test("AI tool loop uses previous turns, executes a source tool, and writes a natural follow-up", async () => {
  const requests = [];
  const answer = await runAiConversation(
    "What is the timeframe of the data?",
    [
      { role: "user", content: "Rank passenger markets." },
      { role: "assistant", content: "ATL leads on preliminary 2025 enplanements." },
    ],
    { kind: "rank_airports", airportCodes: ["ATL", "DFW"] },
    {
      sourceContext: "FAA calendar 2024-2025",
      modelRequest: async (messages) => {
        requests.push(messages);
        if (requests.length === 1) {
          return { choices: [{ message: { role: "assistant", content: null, tool_calls: [{ id: "call-timeframe", type: "function", function: { name: "get_data_timeframe", arguments: "{}" } }] } }] };
        }
        return { choices: [{ message: { role: "assistant", content: "The figures we just discussed compare calendar 2024 with preliminary calendar 2025." } }] };
      },
      toolExecutor: async (name) => {
        assert.equal(name, "get_data_timeframe");
        return { intent: "data_timeframe", period: "2024 to 2025 (preliminary)", source: { mode: "LIVE" }, summary: "FAA timeframe." };
      },
    },
  );

  assert.match(requests[0].map((message) => message.content || "").join(" "), /ATL leads on preliminary 2025/);
  assert.ok(requests[1].some((message) => message.role === "tool" && message.tool_call_id === "call-timeframe"));
  assert.match(answer.summary, /figures we just discussed/);
  assert.equal(answer.period, "2024 to 2025 (preliminary)");
  assert.equal(answer.assistantMode, "AI");
});

test("rules-only fallback answers a timeframe follow-up from the live dataset", async () => {
  const answer = await answerQuestion("What is the timeframe of the data?", [
    { role: "user", content: "Rank passenger markets." },
    { role: "assistant", content: "Here are the top airports." },
  ], { kind: "rank_airports", airportCodes: ["ATL", "DFW"] });
  assert.equal(answer.intent, "data_timeframe");
  assert.match(answer.summary, /calendar year 2024 with calendar year 2025/);
  assert.equal(answer.assistantMode, "RULES_ONLY");
});
