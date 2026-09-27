# Airport Investment Intelligence Agent

A conversational airport-market analyst for exploring U.S. airports, comparing passenger markets, and screening infrastructure opportunities. Calculations are deterministic, source periods are explicit, and unsupported data is called out rather than filled with guessed values.

## Run Locally

Requires Node.js 20.6 or newer.

```powershell
npm install
npm start
```

Open `http://127.0.0.1:3000`. Airport rankings, state/region filters, comparisons, and airport snapshots use the FAA's latest annual enplanement workbook, cached for one hour. Airport snapshots can be enriched with OurAirports facility metadata and coordinates. No API key is required for supported questions.

To enable optional LLM-based intent interpretation, copy `.env.example` to `.env` and set `OPENAI_API_KEY`. The model only maps language to a supported question type; all calculations remain deterministic. Keep `.env` local and do not commit it.

## What It Can Answer

- Rank airports nationally or in a state/region by annual enplanements or year-over-year growth.
- Compare named airports, add another airport in a follow-up, or ask for a specific airport snapshot.
- Explore expansion screening with the documented relative growth/scale score.
- Try operational examples for delays, long-haul routes, and demand pressure. Those calculations currently use illustrative inputs and are labeled `DEMO`; they are not observations.

The conversation supports follow-ups such as “sort those by growth,” “what about the second one?”, and “compare BOS too.” Recent turn text and a small structured result context are held in the browser session and sent to the local API; they are not persisted to a database.

## Checks

```powershell
npm test
node scripts/customer-acceptance.js
```

## Sources and Design

- [FAA passenger boarding and enplanement data](https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger)
- [OurAirports open data](https://ourairports.com/data/)
- [BTS Airline On-Time Statistics](https://www.transtats.bts.gov/ONTIME/), identified as the intended source for replacing the operational demo fixtures
- [Design and architecture note](DESIGN.md)
- [Investor customer acceptance plan and results](CUSTOMER_ACCEPTANCE.md)

The scoring formula, tradeoffs, AI boundary, assumptions, and known data gaps are in [DESIGN.md](DESIGN.md).
