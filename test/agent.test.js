const test = require("node:test");
const assert = require("node:assert/strict");
const { answerQuestion, classifyLocally, isExpansionCandidate } = require("../src/agent");

test("question routing recognizes all four benchmark topics", () => {
  assert.equal(classifyLocally("Which airports in New England are strong candidates for terminal expansion?"), "new_england_expansion");
  assert.equal(classifyLocally("Compare LA and Santa Ana airport congestion levels."), "la_congestion");
  assert.equal(classifyLocally("What percentage of long haul flights out of Anchorage?"), "anc_long_haul");
  assert.equal(classifyLocally("What is the unmet flight demand at SFO and why?"), "sfo_unmet_demand");
});

test("follow-up requests retain the preceding benchmark intent", () => {
  assert.equal(classifyLocally("Why?", "anc_long_haul"), "anc_long_haul");
  assert.equal(classifyLocally("What are strong airports?", null), null);
});

test("demo operational answers disclose their illustrative status and limitations", async () => {
  const comparison = await answerQuestion("Compare LAX and SNA congestion levels.");
  assert.equal(comparison.source.mode, "DEMO");
  assert.match(comparison.limitation, /synthetic placeholders/);
  const demand = await answerQuestion("What is unmet demand at SFO?");
  assert.match(demand.limitation, /not a count or estimate/);
});

test("expansion ranking excludes general aviation and very low-volume facilities", () => {
  assert.equal(isExpansionCandidate({ serviceLevel: "GA", passengerVolume: 500000 }), false);
  assert.equal(isExpansionCandidate({ serviceLevel: "P", passengerVolume: 19914 }), false);
  assert.equal(isExpansionCandidate({ serviceLevel: "P", passengerVolume: 100000 }), true);
});
