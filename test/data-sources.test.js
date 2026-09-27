const test = require("node:test");
const assert = require("node:assert/strict");
const { normalizeEnplanementRows } = require("../src/data-sources");

test("FAA workbook rows normalize airport identity, annual volume, growth, and preliminary status", () => {
  const report = normalizeEnplanementRows([
    ["Rank", "ST", "Locid", "City", "Airport Name", "S/L", "CY 25 Enplanements", "CY 24 Enplanements", "% Change"],
    [1, "MA", "BOS", "Boston", "Boston Logan International", "P", 200, 180, 0.1111],
  ], "https://example.gov/arp-cy2025-all-enplanements-preliminary.xlsx", "2026-09-27T00:00:00.000Z");

  assert.equal(report.latestYear, 2025);
  assert.equal(report.previousYear, 2024);
  assert.equal(report.preliminary, true);
  assert.deepEqual(report.airports[0], {
    airportCode: "BOS",
    stateCode: "MA",
    city: "Boston",
    name: "Boston Logan International",
    serviceLevel: "P",
    latestYear: 2025,
    previousYear: 2024,
    passengerVolume: 200,
    previousPassengerVolume: 180,
    growthPct: 11.11,
  });
});

test("FAA workbook normalization rejects files without comparable year columns", () => {
  assert.throws(() => normalizeEnplanementRows([["ST", "Locid"]]), /two annual enplanement columns/);
});
