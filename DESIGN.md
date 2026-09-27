# Design and Architecture

## Product Boundary

This is a general airport-market exploration tool with an optional investment-screening view, not a capital-planning model. It can rank FAA airports by annual enplanements or growth, filter by state/region, compare airports, and return a basic airport profile. Delay, route-frequency, and demand-pressure examples still use bundled synthetic data and are labeled `DEMO` in every answer.

## Architecture

```text
Browser chat
    -> Node HTTP API (`server.js`)
            -> query planner + turn context (`src/agent.js`)
            -> deterministic analytics (`src/analytics.js`)
            -> public-data adapters (`src/data-sources.js`)
                -> FAA enplanement workbook (XLSX)
                -> OurAirports facility reference and coordinates (CSV)
```

The application uses Node's built-in HTTP server and browser APIs. ExcelJS parses FAA workbooks, and `csv-parse` handles OurAirports CSV. The browser keeps a bounded recent-turn history and structured result context for follow-ups; nothing is persisted. The server binds to loopback by default; no user account or write API is needed.

## Query Coverage and Data Quality

The live FAA table is the reusable source of truth for rankings, state/region filters, snapshots, and comparisons. Ordinary rankings sort the selected raw metric directly rather than mixing it with a custom score. The optional investment screen is clearly separated. FAA location identifiers are kept distinct from IATA identifiers; OurAirports is used as a cross-reference only when an airport can be matched. The FAA `S/L` service-level field controls GA filtering; the separate hub-size field is not treated as a service class.

The current BTS catalog entries inspected for airport delay/on-time data resolve to chart/measure assets without accessible row-level fields through the public Socrata endpoint. Therefore the app does not label those responses live: operational examples remain synthetic `DEMO` inputs until a stable BTS download/API adapter and matched-period coverage tests are available. FAA's newest period is preliminary, and enplanements mean passenger boardings, not total passenger journeys or capacity.

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

When `OPENAI_API_KEY` is configured, the LLM may map varied wording and recent conversation context into a constrained query plan (ranking, comparison, airport profile, or one of the operational examples). It cannot supply metrics, choose score weights, call arbitrary tools, or override calculations. A rules-based planner supports the common queries and follow-up references when no key is configured or a model call fails. All arithmetic, filters, rankings, distance calculations, and caveats are deterministic JavaScript returned as structured results.

## Key Tradeoffs and Next Steps

- The FAA XLSX is an official, current, easy-to-audit source for enplanements, but the newest year is preliminary and the dataset does not provide terminal capacity or project costs.
- Keeping the server dependency-light makes the one-day demo easy to run and explain; a production service would add stronger request validation, observability, persistent cache, and deployment controls.
- Synthetic operational inputs make those concepts explorable without presenting them as facts. The next data integration should find a stable row-level BTS on-time/delay endpoint, retain dataset vintage, and add coverage tests before removing the `DEMO` badge.
- OurAirports is community-maintained public-domain reference data, so coordinates should be checked against an authoritative source before high-stakes use.
