const test = require("node:test");
const assert = require("node:assert/strict");
const {
  compareCongestion,
  compareAirports,
  demandPressure,
  filterAirports,
  haversineMiles,
  longHaulShare,
  percentChange,
  rankAirports,
  rankInvestmentCandidates,
  rankNewEnglandAirports,
} = require("../src/analytics");

test("percent change returns null for missing or invalid baselines", () => {
  assert.equal(percentChange(120, 100), 20);
  assert.equal(percentChange(120, 0), null);
  assert.equal(percentChange(null, 100), null);
});

test("New England ranking is deterministic and excludes incomplete or out-of-region airports", () => {
  const airports = [
    { airportCode: "BOS", stateCode: "MA" },
    { airportCode: "BDL", stateCode: "CT" },
    { airportCode: "JFK", stateCode: "NY" },
    { airportCode: "PWM", stateCode: "ME" },
  ];
  const metrics = {
    BOS: { growthPct: 8, passengerVolume: 200 },
    BDL: { growthPct: 4, passengerVolume: 100 },
    JFK: { growthPct: 99, passengerVolume: 999 },
    PWM: { growthPct: 2 },
  };
  const ranked = rankNewEnglandAirports(airports, metrics);
  assert.deepEqual(ranked.map(({ airport }) => airport.airportCode), ["BOS", "BDL"]);
  assert.equal(ranked[0].score, 100);
  assert.equal(rankNewEnglandAirports(airports, metrics)[0].score, ranked[0].score);
});

test("congestion comparison uses a shared period and reports unavailable data", () => {
  const result = compareCongestion({
    LAX: { period: "2025", operations: 100, delayedOperations: 25, cancellations: 3, averageDelayMinutes: 14 },
  }, ["LAX", "SNA"]);
  assert.equal(result[0].delayRatePct, 25);
  assert.equal(result[0].period, "2025");
  assert.equal(result[1].available, false);
});

test("long-haul share counts flights and computes route distance from coordinates", () => {
  const airports = {
    ANC: { latitude: 61.1744, longitude: -149.996 },
    SEA: { latitude: 47.4502, longitude: -122.3088 },
    JFK: { latitude: 40.6413, longitude: -73.7781 },
  };
  const result = longHaulShare([
    { origin: "ANC", destination: "SEA", flightCount: 3 },
    { origin: "ANC", destination: "JFK", flightCount: 1 },
  ], airports);
  assert.equal(result.totalFlights, 4);
  assert.equal(result.longHaulFlights, 1);
  assert.equal(result.percentage, 25);
  assert.ok(haversineMiles(airports.ANC, airports.JFK) > 3000);
});

test("demand pressure is a bounded screening score, not available when inputs are missing", () => {
  const result = demandPressure({ loadFactorPct: 95, delayRatePct: 20, cancellationRatePct: 5 });
  assert.equal(result.score, 100);
  assert.deepEqual(demandPressure({ loadFactorPct: 90 }).available, false);
});

test("general airport filters and rankings work across regions and retain nonhub primary airports", () => {
  const airports = [
    { airportCode: "BOS", stateCode: "MA", serviceLevel: "P", passengerVolume: 200, growthPct: 4 },
    { airportCode: "BTV", stateCode: "VT", serviceLevel: "P", passengerVolume: 100, growthPct: 8 },
    { airportCode: "SFO", stateCode: "CA", serviceLevel: "P", passengerVolume: 300, growthPct: 3 },
    { airportCode: "XYZ", stateCode: "CA", serviceLevel: "N", passengerVolume: 80, growthPct: 2 },
    { airportCode: "GA1", stateCode: "CA", serviceLevel: "GA", passengerVolume: 500, growthPct: 20 },
  ];
  const california = filterAirports(airports, { stateCodes: ["CA"] });
  assert.deepEqual(california.map((airport) => airport.airportCode), ["SFO", "XYZ"]);
  assert.deepEqual(rankAirports(airports, { metric: "growthPct", limit: 2 }).map((airport) => airport.airportCode), ["GA1", "BTV"]);
  assert.deepEqual(compareAirports(airports, ["BOS", "SFO"]).map((airport) => airport.airportCode), ["BOS", "SFO"]);
  const screening = rankInvestmentCandidates(airports.slice(0, 3), Object.fromEntries(airports.slice(0, 3).map((airport) => [airport.airportCode, airport])));
  assert.equal(screening.length, 3);
});
