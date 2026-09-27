# Airport Investment Intelligence Agent

A compact analyst workspace for screening U.S. airport infrastructure opportunities. Built for the Deloitte Forward Deployed Engineer home task, with deterministic calculations, source visibility, and explicit data limitations.

## Run Locally

Requires Node.js 20.6 or newer.

```powershell
npm install
npm start
```

Open `http://127.0.0.1:3000`. The New England shortlist fetches the FAA's latest annual enplanement workbook on first query and caches it for one hour. Public-source outages produce a clearly marked demonstration result. No API key is required for the rules-based experience.

To enable optional LLM-based intent interpretation, copy `.env.example` to `.env` and set `OPENAI_API_KEY`. The model only maps language to a supported question type; all calculations remain deterministic. Keep `.env` local and do not commit it.

## Benchmark Questions

- New England terminal-expansion shortlist: live FAA passenger enplanement volume and year-over-year growth, scored relative to the six New England states.
- LAX vs. SNA congestion: same-period delayed-operation rate comparison. Current inputs are synthetic and marked `DEMO`.
- ANC long-haul share: great-circle route distance with a 3,000-mile threshold. Current flight counts are synthetic; coordinates are fetched from OurAirports when available.
- SFO unmet demand: a capacity-pressure indicator, not an estimate of missed bookings. Current inputs are synthetic and marked `DEMO`.

## Checks

```powershell
npm test
```

## Sources and Design

- [FAA passenger boarding and enplanement data](https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger)
- [OurAirports open data](https://ourairports.com/data/)
- [BTS Airline On-Time Statistics](https://www.transtats.bts.gov/ONTIME/), identified as the intended source for replacing the operational demo fixtures
- [Design and architecture note](DESIGN.md)

The scoring formula, tradeoffs, AI boundary, assumptions, and known data gaps are in [DESIGN.md](DESIGN.md).
