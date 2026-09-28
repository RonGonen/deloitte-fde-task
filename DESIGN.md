# Design and Architecture

Airport Investment Intelligence Agent, built for the Deloitte FDE take-home. The firm invests in US airport
modernization; the agent helps analysts find airports where terminal/capacity expansion is most likely to pay off
because demand growth and binding capacity coincide.

## 1. What the agent does

It answers questions such as the four in the brief, conversationally, from public data only:

| Question | Deterministic tool behind it | Public sources |
|---|---|---|
| Which airports in New England are strong candidates for terminal expansion? | `rank_airports` -> Expansion Opportunity Score | FAA enplanements, FAA TAF, BTS delay causes, OurAirports runways, FAA slot list |
| Compare LA and Santa Ana airport congestion levels | `compare_congestion` -> Congestion Index + raw metrics | BTS delay causes, BTS on-time snapshot, TAF operations, runways, live FAA NAS status |
| What is the percentage of long haul flights out of Anchorage? | `long_haul_share` | BTS on-time flight records (distance), TAF international share |
| What is the unmet flight demand in SFO and why? | `demand_pressure` -> Unmet Demand Indicator + reasons | TAF forecast vs demonstrated peak operations, BTS delays, slot status, runways |

Follow-ups ("the second one", "add SFO", "what if I ignore scale?") are resolved against the session's last result.

## 2. Architecture

```
Browser UI: chat + analyst side panel (static HTML/JS, Web Speech API for voice in/out)
   -> FastAPI  POST /api/chat   GET /api/rank  GET /api/live  GET /api/health  GET /api/methodology   (127.0.0.1:8000)
      -> Orchestrator: Session memory -> LLM adapter (claude_cli | anthropic) or rules router
           -> tools.dispatch(...)  8 deterministic tools, one result envelope
               -> kpi/  scoring, congestion, long_haul, demand, normalize   (pure functions on one metrics table)
                   -> Engine: builds one metrics row per airport from
                        sources/  FAA enplanements (live), TAF (snapshot), BTS delay cause (live), BTS on-time (snapshot),
                                  OurAirports (live), FAA NAS status (live), FAA slot list (reference)
```

Design rules:

- **Numbers come from code, words come from the model.** Every tool returns `{data, sources, caveats, confidence, method}`.
  The LLM only chooses tools and narrates. The UI renders sources/caveats from the structured payload, not from prose.
- **Grounding check.** After each LLM answer the orchestrator extracts every number in the text and checks that it appears
  in a tool result (with rounding/percent tolerance). Untraceable numbers are surfaced as a warning in the UI.
- **One canonical airport record** keyed by FAA location identifier, joined to IATA/ICAO (OurAirports), TAF and the slot list.
  Join gaps are recorded and lower confidence instead of being silently dropped.
- **Degrade, never fabricate.** Each source loads independently; a failed live fetch falls back to a stale cache or a
  committed snapshot with a note. Missing score components are dropped and weights renormalized; nothing is imputed.
- **The side panel is the same engine.** The "top expansion candidates" table calls `GET /api/rank`, which dispatches
  the identical `rank_airports` tool the chat uses, so a panel row and a chat answer for the same scope carry the same
  score (tested). Scores do legitimately change with the scope (region filter, volume floor, weights) because the
  percentile universe changes, so the panel always shows its scope next to the table.
- **Three LLM adapters, one interface** (`complete(system, messages, tools) -> AssistantTurn`):
  `claude_cli` (headless Claude Code CLI, uses the machine's logged-in account, structured JSON output),
  `anthropic` (official SDK, native tool use, when `ANTHROPIC_API_KEY` is set), and `rules` (no LLM). The rules router
  is also the automatic fallback when an LLM call fails, and it shares the same tools and session memory.

## 3. Data sources and vintages

| Source | Content | Refresh |
|---|---|---|
| FAA Passenger Boarding data (CY2025 preliminary / CY2024 final workbook) | Enplanements, YoY, service level, hub size for ~1,700 airports | Live, discovered from the FAA page, 24 h cache, committed fallback copy |
| FAA Terminal Area Forecast 2025 | Actual enplanements and operations 1990-2024 by category; FAA forecast 2025-2055 | `scripts/refresh_data.py` builds `data/snapshots/taf_compact.csv` from the 15 MB FAA zip |
| BTS Airline On-Time Statistics and Delay Causes | Monthly arrivals, delayed >=15 min, cancellations, delay-cause split, by airport and carrier | Live trailing 12 months (2025-08 to 2026-07 at build time), 24 h cache, committed snapshot fallback |
| BTS Reporting Carrier On-Time Performance (flight level) | Origin, destination, distance, taxi-out, departure delay | `refresh_data.py` downloads 33 MB monthly files (May-Jul 2026) and writes `routes_by_origin.csv`, `ontime_origin_metrics.csv` |
| OurAirports (public domain) | IATA/ICAO/FAA codes, coordinates, runways (length, surface, open) | Compact committed snapshot (airports and runways that join to an FAA airport, ~0.4 MB) built by `refresh_data.py`; live 17 MB download only when the snapshot is missing |
| FAA NAS Status feed | Live ground delay programs, ground stops, closures | Live, 5 min cache; annotation only |
| FAA Slot Administration page (verified 2026-09-27) | Level 3 slot-controlled: JFK, LGA, DCA; Level 2 schedule-facilitated: ORD, LAX, EWR, SFO | Reference file with source URL and dates |

The BTS delay-cause download endpoint takes an obfuscated SQL fragment (a +13 rotation over `[0-9A-Za-z]`, month key
`year*12+month`); the adapter reproduces the encoding the BTS page itself emits and is unit-tested against it.

## 4. Scoring methodology

All raw signals are winsorized at the 5th/95th percentile, then converted to **national percentiles (0-100)** across the
universe of FAA primary and commercial-service airports with at least 100,000 annual enplanements (233 airports in
CY2025). Region filters are applied *after* scoring so a small peer set (six New England states) does not collapse
into 0/50/100 ranks. A constant signal maps to 50. A missing component is dropped, weights are renormalized, and
confidence is lowered; nothing is imputed.

### Expansion Opportunity Score

| Component | Weight | Inputs |
|---|---|---|
| Forecast growth | 0.30 | FAA TAF enplanement CAGR 2025-2035 (unconstrained forecast) |
| Demand momentum | 0.20 | Mean of FAA CY2024-CY2025 YoY percentile and TAF 2023-2024 actual growth percentile |
| Capacity pressure | 0.30 | Half **structural**: air-carrier + air-taxi operations per qualifying runway (open, paved, >= 5,000 ft), FAA slot status (Level 3 = 100, Level 2 = 50, none = 0), TAF 2035 operations / highest annual operations since 1990. Half **observed** (needs >= 2,000 reporting-carrier arrivals): % arrivals delayed >= 15 min, share of delays attributed to the NAS, cancellation rate |
| Scale | 0.20 | log10 enplanements (revenue base to monetize an expansion) |

The tool also returns a **no-scale sensitivity score**, sub-scores, the top drivers (component percentile x weight),
raw metrics, missing components and a confidence level per airport. Weights and the volume floor are parameters an
analyst can change in conversation.

Why these weights: an expansion pays off when demand is growing (forecast + momentum, 0.50 combined) *and* capacity is
already binding (0.30); scale (0.20) keeps very small airports with volatile growth from dominating and is disclosed
explicitly (with the no-scale variant) rather than hidden in a threshold.

### Congestion Index (comparisons)

0.35 arrivals delayed >= 15 min + 0.20 NAS share of delays + 0.15 cancellation rate + 0.15 average taxi-out minutes
+ 0.15 operations per qualifying runway, each a national percentile. Raw metrics and the national medians are always
shown next to the index, weather's own share of delays is printed beside the NAS share, and live FAA status is
attached but never scored.

### Long-haul share

Departures on routes >= 3,000 statute miles / all scheduled departures in the snapshot months (departure-count
weighted); 1,500 and 2,500 mile shares are shown for sensitivity, with the top and longest routes. The tool states that
the BTS rows cover domestic flights of reporting carriers only (no international, no all-cargo), which materially
understates Anchorage, and complements them with the TAF international enplanement share and operations count.

### Unmet Demand Indicator

Mean of six national percentiles: TAF 2035 operations vs demonstrated peak annual operations; % arrivals delayed;
NAS share of delays; slot status; inverse recovery ratio vs 2019; growth in passengers per operation since 2019
(up-gauging is how airlines grow where they cannot add flights). Each driver is rendered as a plain-language reason
with the airport's value against the national median. The tool says explicitly that seats and load factors are not
available, so unserved passengers cannot be counted: this is a pressure indicator, not a passenger gap.

## 5. Where and how AI is used

- **Interpretation and narration only.** Claude (default `claude-fable-5-1`, configurable) reads the analyst's question
  and the conversation state, decides which tools to call and with which parameters (states, codes, weights, floors),
  and writes the answer in a fixed shape: direct answer, evidence with periods and sources, reasoning, assumptions and
  uncertainty, suggested follow-ups. The system prompt forbids numbers that are not in a tool result.
- **Not used for**: any calculation, weighting, ranking, forecasting, or data retrieval. The model cannot change
  weights except by calling `rank_airports` with explicit parameters, which the tool records in the response.
- **Safety net**: the grounding check flags untraceable numbers; the rules router answers when the LLM is unavailable;
  every response carries a `mode` badge (LLM vs rules) so the analyst knows which path produced it.
- **Two ways to run Claude**: through the local Claude Code CLI login (no API key file on disk) or the Anthropic API
  with `ANTHROPIC_API_KEY` from `.env` (git-ignored). Evaluators without either get the rules-based path.

## 6. Key tradeoffs

- **Snapshots vs live pulls.** Small, fast sources (FAA workbook, BTS delay causes, OurAirports, NAS status) are fetched
  live with disk caching; the two large or slow sources (15 MB TAF zip, 33 MB/month BTS flight files served at ~60 KB/s)
  are turned into compact committed snapshots by `scripts/refresh_data.py`. This keeps `npm install`-style setup at
  under a minute and makes results reproducible, at the cost of route data being three months old.
- **T-100 is missing.** BTS T-100 segment data (seats, load factors, international and cargo routes) would be the best
  evidence for unmet demand and long-haul share, but its TranStats download is an ASP.NET postback that could not be
  scripted reliably in the time available. The methodology says so wherever it matters.
- **National percentiles over regional peer sets.** Regional peer sets are more intuitive but degenerate for small
  regions; national normalization is stable and the region filter is stated in every answer.
- **Weather inside delay statistics.** BTS NAS-attributed delays include weather flow restrictions. Splitting structural
  from observed pressure, printing the weather share, and using slot status and operations-per-runway keeps a
  bad-weather airport from being mistaken for a capacity-constrained one.
- **Claude Fable 5.1 by default.** Best interpretation quality for a demo; each turn takes 20-40 s and roughly $0.30-0.60
  through the CLI. `LLM_MODEL=claude-sonnet-5` is a faster, cheaper alternative.
- **Single-analyst security model.** The server binds to loopback; non-loopback clients are refused unless `APP_TOKEN`
  is set, in which case every API call needs a bearer token (constant-time compared). Secrets come from the shell
  environment, never from files. Responses carry a same-origin CSP and security headers, there is no CORS, inputs are
  validated at the boundary, and internal error text stays in the log. Sessions are in-memory; a multi-user deployment
  would add per-user identity, persistent sessions, request logging and rate limits.

## 7. Assumptions, uncertainty and scope

- Enplanements are FAA passenger boardings, not total passengers; CY2025 is preliminary.
- TAF forecasts are the FAA's unconstrained demand forecasts; TAF actuals end in 2024.
- BTS delay metrics cover domestic flights of carriers above the DOT reporting threshold, arrivals-based, trailing 12
  months, and include weather.
- "Demonstrated peak operations" is historical throughput, not engineered capacity; runway counts are an airfield proxy,
  not terminal or gate capacity.
- Scores are relative screening percentiles for diligence, not probabilities or returns. Out of scope: project costs,
  ROI, financing, gate/terminal design capacity, seats and load factors, cargo tonnage, fares, catchment demographics,
  airline schedule plans, non-US airports.

## 8. Testing

`pytest` runs 101 offline tests on real-data fixture slices: source parsers (including the BTS URL cipher), the airport
registry and its text-resolution collisions (`AND`, `SEA` vs Washington, "LA", "Washington state"), normalization,
each KPI (determinism, weights, sensitivity, missing data), the rules router and follow-ups, tool envelopes, the
grounding check, the orchestrator with a fake LLM (tool loop and fallback), and the HTTP API including input
validation. Network-dependent checks are opt-in (`-m network`). `scripts/client_run.py` replays an investor's session
against the running server and writes the transcript used for `docs/CLIENT_RUN_REPORT.md`.
