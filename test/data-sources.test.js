const test = require("node:test");
const assert = require("node:assert/strict");
const { normalizeAirportReference, normalizeEnplanementRows } = require("../src/data-sources");

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

test("airport reference indexes IATA and local identifiers with facility metadata", () => {
  const airports = normalizeAirportReference([{
    iata_code: "BOS",
    local_code: "BOS",
    gps_code: "KBOS",
    latitude_deg: "42.3656",
    longitude_deg: "-71.0096",
    iso_country: "US",
    iso_region: "US-MA",
    type: "large_airport",
    scheduled_service: "yes",
    name: "Boston Logan International",
  }]);
  assert.equal(airports.BOS.regionCode, "MA");
  assert.equal(airports.KBOS.scheduledService, true);
  assert.equal(airports.BOS.latitude, 42.3656);
  assert.equal(airports.BOS.facilityType, "large_airport");
});

test("IATA identifier takes precedence over colliding local and GPS codes", () => {
  const airports = normalizeAirportReference([
    { iata_code: "LAX", local_code: "LAX", gps_code: "KLAX", latitude_deg: 33.94, longitude_deg: -118.4, type: "large_airport", scheduled_service: "yes" },
    { iata_code: "", local_code: "OTHER", gps_code: "LAX", latitude_deg: 10, longitude_deg: 10, type: "small_airport", scheduled_service: "no" },
  ]);
  assert.equal(airports.LAX.facilityType, "large_airport");
  assert.equal(airports.LAX.scheduledService, true);
});
