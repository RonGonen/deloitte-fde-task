# Airport Investment Intelligence Agent

A conversational airport-market analyst for exploring U.S. airports, comparing passenger markets, and screening infrastructure opportunities. Calculations are deterministic, source periods are explicit, and unsupported data is called out rather than filled with guessed values.

## Run Locally

Requires Node.js 20.6 or newer.

```powershell
npm install
npm start
```

Open `http://127.0.0.1:3000`. The server reads `.env` on startup. Airport rankings, state/region filters, comparisons, airport snapshots, and timeframe answers use the FAA's latest annual enplanement workbook, cached for one hour. Airport snapshots can be enriched with OurAirports facility metadata and coordinates.

To enable the AI-driven chat assistant, copy `.env.example` to `.env`, set `OPENAI_API_KEY`, and restart the server. `OPENAI_MODEL` selects the model; `OPENAI_BASE_URL` can point to an OpenAI-compatible provider. Never paste the key into chat or commit `.env`. Without a key the app explicitly reports rules-only mode; it can answer built-in airport screens and the timeframe follow-up, but it is not full AI chat.

## What It Can Answer

- Rank airports nationally or in a state/region by annual enplanements or year-over-year growth.
- Compare named airports, add another airport in a follow-up, or ask for a specific airport snapshot.
- Explore expansion screening with the documented relative growth/scale score.
- Try operational examples for delays, long-haul routes, and demand pressure. Those calculations currently use illustrative inputs and are labeled `DEMO`; they are not observations.

With AI configured, the agent reads recent conversation turns, calls the FAA/airport data tools when it needs evidence, then writes a natural-language response. This allows follow-ups such as “What timeframe is that?”, “sort those by growth,” and “what about the second one?” without hardcoded answer templates. Recent turn text and structured result context remain in the browser session and are sent to the local API; they are not persisted to a database. The model cannot invent capacity, project cost, or ROI data that the tools do not provide. A mocked-provider test covers the tool-call and follow-up loop; live provider behavior requires your local key.

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
