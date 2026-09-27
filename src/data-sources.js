const ExcelJS = require("exceljs");
const { parse } = require("csv-parse/sync");
const { percentChange } = require("./analytics");

const FAA_PAGE_URL = "https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger";
const OUR_AIRPORTS_CSV_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv";
const CACHE_TTL_MS = 60 * 60 * 1000;

let faaCache;
let coordinateCache;

function readCell(row, index) {
  const value = row[index];
  if (value && typeof value === "object" && "text" in value) return value.text;
  return value;
}

function normalizeEnplanementRows(rows, datasetUrl, fetchedAt = new Date().toISOString()) {
  const headerRow = rows.find((row) => row?.some((cell) => String(cell).trim() === "Locid"));
  if (!headerRow) throw new Error("FAA workbook is missing its airport identifier column.");

  const headers = headerRow.map((cell) => String(cell ?? "").trim());
  const column = (name) => headers.findIndex((header) => String(header ?? "").toLowerCase() === name.toLowerCase());
  const latestIndex = headers.findIndex((header) => /^CY\s+\d{2,4}\s+Enplanements$/i.test(header));
  const previousIndex = headers.findIndex((header, index) => index !== latestIndex && /^CY\s+\d{2,4}\s+Enplanements$/i.test(header));
  const yearFromHeader = (header) => {
    const suffix = Number(header.match(/CY\s+(\d{2,4})/i)?.[1]);
    return suffix < 100 ? 2000 + suffix : suffix;
  };

  if (latestIndex < 0 || previousIndex < 0) throw new Error("FAA workbook does not contain two annual enplanement columns.");
  const stateIndex = column("ST");
  const codeIndex = column("Locid");
  const cityIndex = column("City");
  const nameIndex = column("Airport Name");
  const serviceIndex = column("S/L");
  const growthIndex = column("% Change");
  const airports = [];

  for (const row of rows) {
    if (!row || row === headerRow || !readCell(row, codeIndex)) continue;
    const current = Number(readCell(row, latestIndex));
    const previous = Number(readCell(row, previousIndex));
    if (!Number.isFinite(current) || current < 0) continue;
    const publishedGrowth = Number(readCell(row, growthIndex));
    const derivedGrowth = percentChange(current, previous);
    airports.push({
      airportCode: String(readCell(row, codeIndex)).trim().toUpperCase(),
      stateCode: String(readCell(row, stateIndex) ?? "").trim().toUpperCase(),
      city: String(readCell(row, cityIndex) ?? "").trim(),
      name: String(readCell(row, nameIndex) ?? "").trim(),
      serviceLevel: String(readCell(row, serviceIndex) ?? "").trim(),
      latestYear: yearFromHeader(headers[latestIndex]),
      previousYear: yearFromHeader(headers[previousIndex]),
      passengerVolume: current,
      previousPassengerVolume: Number.isFinite(previous) ? previous : null,
      growthPct: Number.isFinite(publishedGrowth)
        ? Number((Math.abs(publishedGrowth) <= 1 ? publishedGrowth * 100 : publishedGrowth).toFixed(2))
        : derivedGrowth,
    });
  }

  return {
    airports,
    latestYear: yearFromHeader(headers[latestIndex]),
    previousYear: yearFromHeader(headers[previousIndex]),
    fetchedAt,
    datasetUrl,
    preliminary: /preliminary/i.test(datasetUrl),
    sourceName: "Federal Aviation Administration (FAA)",
  };
}

async function fetchWithTimeout(url, timeoutMs = 15000) {
  const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  if (!response.ok) throw new Error(`Source returned HTTP ${response.status}: ${new URL(url).host}`);
  return response;
}

async function loadFaaEnplanements({ forceRefresh = false } = {}) {
  if (!forceRefresh && faaCache && Date.now() - faaCache.loadedAt < CACHE_TTL_MS) return faaCache.report;

  const page = await fetchWithTimeout(FAA_PAGE_URL);
  const html = await page.text();
  const match = html.match(/href=["']([^"']*arp-cy\d+-all-enplanements-preliminary\.xlsx)["']/i)
    ?? html.match(/href=["']([^"']*arp-cy\d+-all-enplanements\.xlsx)["']/i);
  if (!match) throw new Error("Could not discover an FAA airport enplanement workbook.");

  const datasetUrl = new URL(match[1], FAA_PAGE_URL).toString();
  const workbookResponse = await fetchWithTimeout(datasetUrl);
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(Buffer.from(await workbookResponse.arrayBuffer()));
  const sheet = workbook.worksheets[0];
  if (!sheet) throw new Error("FAA workbook contains no worksheets.");
  const report = normalizeEnplanementRows(sheet.getSheetValues(), datasetUrl);
  faaCache = { loadedAt: Date.now(), report };
  return report;
}

async function loadAirportCoordinates({ forceRefresh = false } = {}) {
  if (!forceRefresh && coordinateCache && Date.now() - coordinateCache.loadedAt < CACHE_TTL_MS) return coordinateCache.airports;

  const response = await fetchWithTimeout(OUR_AIRPORTS_CSV_URL);
  const records = parse(await response.text(), { columns: true, skip_empty_lines: true, bom: true });
  const airports = {};
  for (const record of records) {
    const code = String(record.iata_code ?? "").trim().toUpperCase();
    const latitude = Number(record.latitude_deg);
    const longitude = Number(record.longitude_deg);
    if (!code || !Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
    airports[code] = { latitude, longitude, name: record.name, countryCode: record.iso_country };
  }
  coordinateCache = { loadedAt: Date.now(), airports };
  return airports;
}

module.exports = {
  FAA_PAGE_URL,
  OUR_AIRPORTS_CSV_URL,
  loadAirportCoordinates,
  loadFaaEnplanements,
  normalizeEnplanementRows,
};
