# Design and Architecture

## Product Boundary

This is an exploratory airport-investment screening tool, not a capital-planning model. It answers the four benchmark questions with explicit periods, definitions, provenance, and limitations. The New England passenger-growth shortlist uses live FAA data. Congestion, route frequency, and SFO pressure indicators currently use bundled synthetic data and are labeled `DEMO` in every answer.

## Architecture

```text
Browser chat
    -> Node HTTP API (`server.js`)
        -> intent router (`src/agent.js`)
            -> deterministic analytics (`src/analytics.js`)
            -> public-data adapters (`src/data-sources.js`)
                -> FAA enplanement workbook (XLSX)
                -> OurAirports reference coordinates (CSV)
```

The application uses Node's built-in HTTP server and browser APIs. ExcelJS parses FAA workbooks, and `csv-parse` handles OurAirports CSV. The server binds to loopback by default; no user account or write API is needed.

## Scoring Methodology

For each airport with both years present, FAA supplies annual enplanements and year-over-year change. We filter to primary or commercial-service airports (`P`/`CS`) with at least 100,000 annual enplanements in Connecticut, Maine, Massachusetts, New Hampshire, Rhode Island, and Vermont. The 100,000 threshold is an explicit screening choice to keep very small facilities from dominating on volatile growth rates. Each signal is min-max scaled against eligible airports in that peer set to a 0-100 range; if every airport has the same value, each receives 50 for that dimension.

```text
screen score = 0.65 * growth percentile + 0.35 * passenger-volume percentile
```

Growth receives the larger weight because expansion screening should reward positive momentum, while volume captures the scale of the existing operation. The score is relative to the selected peer set, not a probability of success. Airports missing either metric are omitted; ties are ordered by FAA location identifier. The result is a shortlist for diligence, not evidence of constrained terminal capacity, unserved demand, or positive project ROI.

Other deterministic calculations:

- **LAX/SNA congestion:** delayed operations divided by total operations for the same period. Current displayed inputs are synthetic demonstrations.
- **ANC long-haul share:** frequency-weighted flights on routes at least 3,000 great-circle miles divided by all listed demonstration flights. Coordinates are fetched from OurAirports when available; route frequencies remain synthetic.
- **SFO pressure screen:** 55% capped load-factor signal + 30% capped delay-rate signal + 15% capped cancellation-rate signal. Caps are 95%, 20%, and 5% respectively. This is an indicator score, never a count of unmet travelers.

## AI Use

When `OPENAI_API_KEY` is configured, the LLM may map varied user wording and contextual follow-ups to one of four supported intent IDs. It cannot supply metrics, choose score weights, call arbitrary tools, or override the calculation functions. The local rules-based router is the fallback when no key is configured or the model call fails. All arithmetic, filters, rankings, distance calculations, and caveats are handled in deterministic JavaScript and returned as structured results.

## Key Tradeoffs and Next Steps

- The FAA XLSX is an official, current, easy-to-audit source for enplanements, but the newest year is preliminary and the dataset does not provide terminal capacity or project costs.
- Keeping the server dependency-light makes the one-day demo easy to run and explain; a production service would add stronger request validation, observability, persistent cache, and deployment controls.
- Synthetic operational inputs make all four workflows demonstrable without presenting them as facts. The next data integration should replace these fixtures with matched-period BTS airport on-time and route records, retain dataset vintage, and add coverage tests before removing the `DEMO` badge.
- OurAirports is community-maintained public-domain reference data, so coordinates should be checked against an authoritative source before high-stakes use.
