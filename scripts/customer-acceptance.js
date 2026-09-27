const assert = require("node:assert/strict");

const baseUrl = process.env.APP_URL || "http://127.0.0.1:3000";
const history = [];
let context = null;
const outcomes = [];

async function ask(question) {
  history.push({ role: "user", content: question });
  const response = await fetch(`${baseUrl}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history: history.slice(-12), context }),
  });
  const answer = await response.json();
  assert.equal(response.ok, true, `${question}: HTTP ${response.status} ${answer.error || ""}`);
  context = answer.context || context;
  history.push({ role: "assistant", content: JSON.stringify({ summary: answer.summary, intent: answer.intent, context, results: answer.results?.slice(0, 5) }) });
  return answer;
}

function record(id, description, answer, check) {
  console.log(JSON.stringify({ id, intent: answer.intent, mode: answer.source?.mode, summary: answer.summary, context: answer.context }));
  check(answer);
  outcomes.push({ id, description, result: "PASS", intent: answer.intent, mode: answer.source?.mode || "NO DATA CLAIM", period: answer.period, summary: answer.summary });
}

async function main() {
  const status = await fetch(`${baseUrl}/api/status`).then((response) => response.json());
  assert.equal(status.status, "ready");

  const ranking = await ask("Which airports have the highest passenger traffic?");
  record("INV-01", "National passenger-market ranking uses live FAA data", ranking, (answer) => {
    assert.equal(answer.intent, "rank_airports");
    assert.match(answer.source.mode, /^LIVE/);
    assert.equal(answer.results[0].airportCode, "ATL");
    assert.ok(answer.results.every((airport) => Number.isFinite(airport.enplanements)));
  });

  const resort = await ask("Sort those by growth instead");
  record("INV-02", "Follow-up re-sorts the prior result set without losing context", resort, (answer) => {
    assert.equal(answer.intent, "rank_airports");
    assert.deepEqual(answer.results.map((airport) => airport.airportCode).sort(), ranking.results.map((airport) => airport.airportCode).sort());
    assert.ok(answer.results[0].growthPct >= answer.results.at(-1).growthPct);
  });

  const cutoff = await ask("Which California airports are growing fastest with at least 100,000 annual enplanements?");
  record("INV-03", "Regional growth ranking supports an investor-selected scale floor", cutoff, (answer) => {
    assert.equal(answer.intent, "rank_airports");
    assert.match(answer.summary, /100,000 annual enplanements/);
    assert.ok(answer.results.length > 0);
    assert.ok(answer.results.every((airport) => airport.state === "CA" && airport.enplanements >= 100000));
  });

  const expansion = await ask("Which New England airports are strong candidates for terminal expansion?");
  record("INV-04", "Relative opportunity screen states its geography and scoring method", expansion, (answer) => {
    assert.equal(answer.intent, "rank_airports");
    assert.match(answer.summary, /CT, ME, MA, NH, RI, and VT/);
    assert.match(answer.summary, /65% growth, 35% passenger scale/);
    assert.match(answer.limitation, /does not establish capacity need/);
    assert.ok(answer.results.every((airport) => Number.isFinite(airport.score)));
  });

  const comparison = await ask("Compare BOS and SEA passenger traffic");
  record("INV-05", "Named target airports are compared on a shared period and measure", comparison, (answer) => {
    assert.equal(answer.intent, "compare_airports");
    assert.deepEqual(answer.results.map((airport) => airport.airportCode), ["BOS", "SEA"]);
    assert.equal(answer.results[0].currentYear, answer.results[1].currentYear);
    assert.match(answer.limitation, /do not measure available capacity/);
  });

  const extendComparison = await ask("And compare SFO too");
  record("INV-06", "A follow-up adds a target to the active comparison", extendComparison, (answer) => {
    assert.equal(answer.intent, "compare_airports");
    assert.deepEqual(answer.results.map((airport) => airport.airportCode), ["BOS", "SEA", "SFO"]);
  });

  const profile = await ask("Tell me about LAX");
  record("INV-07", "Airport snapshot enriches FAA traffic with facility reference", profile, (answer) => {
    assert.equal(answer.intent, "airport_profile");
    assert.match(answer.summary, /large airport facility with scheduled service/);
    assert.match(answer.summary, /at -?\d+\.\d{3}, -?\d+\.\d{3}/);
  });

  const roi = await ask("What is the return on investment for modernizing BOS?");
  record("INV-08", "Unsupported ROI request is explicitly identified as missing evidence", roi, (answer) => {
    assert.equal(answer.intent, "investment_data_gap");
    assert.match(answer.limitation, /decision-grade case needs airport financials/);
    assert.equal(answer.results.length, 0);
  });

  const operations = await ask("Compare LAX and SNA congestion levels");
  record("INV-09", "Operational proxy does not present synthetic values as live", operations, (answer) => {
    assert.equal(answer.source.mode, "DEMO");
    assert.match(answer.limitation, /synthetic/);
  });

  console.log(JSON.stringify({ status: "PASS", testCount: outcomes.length, outcomes }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
