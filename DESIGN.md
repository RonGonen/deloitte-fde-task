# Design and Architecture

Airport Investment Intelligence Agent (Deloitte FDE take-home). The firm invests in US airport modernization; the
agent helps analysts find airports where terminal/capacity expansion is most likely to pay off because demand growth
and binding capacity coincide. Setup and usage: [README](README.md). Investor acceptance run:
[docs/CLIENT_RUN_REPORT.md](docs/CLIENT_RUN_REPORT.md). Plain-language overview: [docs/OVERVIEW.md](docs/OVERVIEW.md).

## 1. Architecture

```
Browser (static HTML/JS): chat + analyst side panel (top-10 table, live FAA status, data vintages, weights), Web Speech voice
   -> FastAPI (127.0.0.1:8000)  POST /api/chat | GET /api/rank /api/live /api/regions /api/health /api/methodology
        security middleware: bearer token (APP_TOKEN) or loopback-only, CSP + security headers, no CORS
      -> Orchestrator: Session (in-memory, 1 h TTL, per-tool memory) -> LLM adapter or rules router -> grounding check
           -> tools.dispatch(): 8 deterministic tools, one envelope {data, sources, caveats, confidence, method}
               -> kpi/: normalize, scoring, congestion, long_haul, demand   (pure functions over one metrics table)
                   -> Engine: one metrics row per FAA primary/commercial-service airport (515), built from
                        sources/: FAA enplanements (live + fallback), TAF (snapshot), BTS delay causes (live + fallback),
                                  BTS on-time (snapshot), OurAirports (snapshot), FAA NAS status (live), FAA slot list (reference)
```

Design rules:

- **Numbers come from code, words come from the model.** Tools compute; the LLM selects tools, sets parameters and
  narrates. The UI renders sources/caveats/confidence from the tool envelope, never from prose.
- **One canonical airport record** keyed by FAA LID, joined to IATA/ICAO (OurAirports), TAF and the slot list. Join gaps
  are recorded per airport and lower confidence instead of dropping the airport.
- **Degrade, never fabricate.** Sources load independently; a failed live fetch falls back to a stale cache or committed
  snapshot with a note. Missing score inputs are dropped and weights renormalized; nothing is imputed.
- **Panel = chat.** `GET /api/rank` dispatches the same `rank_airports` tool as the chat, so identical scope gives
  identical scores (tested). Scores change with scope (floor, region, weights) because the percentile universe changes;
  the panel prints its scope.
- **Grounding check.** Every number in an LLM answer is matched against the numeric pool of this turn's and the last
  three turns' tool results (rounding-precision tolerance, x100 / /100 and ratio-minus-one variants, M/K suffixes).
  Untraceable numbers are returned as a warning and shown in the UI.

## 2. Data sources and vintages

| Source | Content | Access in this build |
|---|---|---|
| FAA Passenger Boarding workbook | Enplanements CY2025 (preliminary) vs CY2024, service level, hub size, ~1,700 airports | Live (link discovered on the FAA page), 24 h cache, committed fallback copy |
| FAA Terminal Area Forecast 2025 | Actual enplanements/operations 1990-2024 by category; forecast 2025-2055 | `scripts/refresh_data.py` -> `data/snapshots/taf_compact.csv` (from the 15 MB zip) |
| BTS Airline On-Time Statistics and Delay Causes | Monthly arrivals, delayed >=15 min, cancellations, cause split per airport | Live trailing 12 months (2025-08 to 2026-07), 24 h cache, snapshot fallback. Download URL carries a +13 rotation over `[0-9A-Za-z]` with month key `year*12+month`, reproduced and unit-tested |
| BTS Reporting Carrier On-Time Performance | Flight-level origin, destination, distance, taxi-out, departure delay | `refresh_data.py` downloads monthly 33 MB files (2026-05..07) -> `routes_by_origin.csv`, `ontime_origin_metrics.csv` |
| OurAirports | LID/IATA/ICAO codes, coordinates, runways (length, surface, open) | Compact snapshot of the 1,633 airports / 2,947 runways that join to FAA airports (~0.25 MB); live 17 MB pull only if missing |
| FAA NAS Status feed | Live ground delay programs, ground stops, closures | Live, 5 min cache, 60 s failure back-off; annotation only |
| FAA Slot Administration page | Level 3: JFK, LGA, DCA; Level 2: ORD, LAX, EWR, SFO | Reference JSON with URL and verification date (2026-09-27) |

Not available: BTS T-100 (seats, load factors, international/cargo segments); its TranStats postback could not be
scripted. Every affected tool states the gap.

## 3. Scoring methodology

Universe: FAA `S/L in {P, CS}` airports with >= 100,000 enplanements (233 in CY2025; the floor is a parameter). Each raw
signal is winsorized at p5/p95, then rank-transformed to a **national percentile 0-100** (average ranks for ties, constant
series -> 50). Filters (states/region/codes) are applied *after* scoring so small peer sets do not degenerate. Weighted
composites use `weighted_score`, which drops missing components and renormalizes the remaining weights.

### Expansion Opportunity Score

| Component | Weight | Signal(s) |
|---|---|---|
| Forecast growth | 0.30 | TAF enplanement CAGR, first forecast year + 10 (2025 -> 2035), unconstrained forecast |
| Demand momentum | 0.20 | Mean of percentiles: FAA CY24->CY25 YoY; TAF 2023->2024 actual growth |
| Capacity pressure | 0.30 | Mean of *structural* (mean of: air-carrier + air-taxi ops per qualifying runway [open, paved, >= 5,000 ft]; slot status 100/50/0; TAF 2035 ops / peak annual ops since 1990) and *observed* (mean of: % arrivals delayed >= 15 min; NAS share of delays; cancellation %), observed requires >= 2,000 arrivals |
| Scale | 0.20 | log10 enplanements |

Outputs per airport: score, `score_without_scale` (sensitivity), sub-scores, structural/observed pressure, top-3 drivers
(`(percentile - 50) x weight`), raw metrics, `missing_components`, `data_gaps`, confidence. Weights and floor are tool
parameters, so the analyst can re-run with e.g. `scale = 0` or `min_enplanements = 1,000,000`. Scored rows are memoized
per `(floor, weights)` on the table; filtering is applied on copies. Codes below the floor are returned in
`excluded_below_floor` rather than silently dropped.

**Confidence**: `high` when all components and sub-inputs are present; `medium` for one gap; `low` for two or more or
a join gap. Gaps counted: no BTS delay coverage (< 2,000 arrivals), no qualifying-runway data, no TAF record, missing
component. Confidence measures data completeness, not the strength of the case.

Rationale for weights: growth signals (0.50 combined) and binding capacity (0.30) are the investment thesis; scale
(0.20) is disclosed explicitly and removable rather than hidden in a cutoff.

### Congestion Index

`0.35 * del15% + 0.20 * NAS share + 0.15 * cancellation% + 0.15 * avg taxi-out + 0.15 * ops per runway`, each a national
percentile; observed inputs need >= 2,000 arrivals. Raw metrics, national medians and the weather share (BTS "weather" =
extreme weather; "NAS" includes non-extreme weather flow restrictions) are returned alongside. Live NAS status is
attached, never scored.

### Long-haul share

`departures with distance >= T / all scheduled departures` over the snapshot months, departure-weighted, T = 3,000 mi
headline with 1,500 and 2,500 mi for sensitivity; top and longest routes; TAF international enplanement share as
complement. Coverage caveat: domestic flights of reporting carriers only (no international, no all-cargo).

### Unmet Demand Indicator

Mean of six national percentiles: TAF 2035 ops / demonstrated peak ops; % arrivals delayed; NAS share; slot status;
inverse recovery ratio (2024 / 2019 enplanements); passengers-per-operation growth since 2019 (up-gauging). Each driver
is rendered as a sentence with the airport's value vs the national median. Explicit statement: no seats/load factors,
so this is pressure, not a passenger gap.

## 4. Where and how AI is used

- **Role**: interpret the question and conversation state, choose tools and parameters, narrate. The system prompt fixes
  the answer shape (direct answer, evidence with periods/sources, reasoning, assumptions/uncertainty, follow-ups),
  forbids numbers absent from tool results, requires ambiguity to be stated ("LA" -> LAX) and general knowledge to be
  labelled, and lists out-of-scope topics (ROI, costs, gate capacity, load factors, cargo).
- **Not used for**: calculations, weights, ranking, forecasting, data access. The model changes weights only by calling
  `rank_airports` with explicit parameters, which the tool echoes in its result.
- **Loop**: up to 4 tool rounds per turn; tool results are returned as `tool_result` blocks (the full assistant content,
  including thinking blocks, is replayed unchanged); if rounds are exhausted the rules narrator summarizes the last result.
- **Adapters** (`complete(system, messages, tools) -> AssistantTurn`): `claude_cli` (headless Claude Code CLI, the
  machine's logged-in account, structured JSON output via `--json-schema`, built-in tools disabled, list-form
  subprocess arguments); `anthropic` (official SDK, native tool use, `ANTHROPIC_API_KEY` from the shell environment);
  `rules` (regex/word-list intents + deterministic narration). `LLM_PROVIDER=auto` picks in that order; the rules path
  is also the automatic fallback on any LLM error. Default model `claude-fable-5-1` (`LLM_MODEL` overrides).
- **Guardrails**: grounding check on every LLM answer; `mode` badge (llm/rules) and model on every response; session
  memory is server-side and per tool so follow-ups ("the second one", "add SFO", "ignore scale") resolve identically in
  both paths; input validated at the boundary (message length, UUID session id, provider enum).

## 5. Key tradeoffs

- **Snapshots vs live.** Small sources are live with disk cache and fallback; large/slow ones (TAF zip, 33 MB monthly BTS
  files at ~60 KB/s, 17 MB OurAirports) are compact committed snapshots refreshed by one script. Startup ~0.2 s, works
  offline, reproducible; route data ages until refreshed.
- **National percentiles vs regional peer sets.** Regional sets are intuitive but degenerate for small regions;
  national normalization is stable and the scope is stated in every answer and on the panel.
- **Weather inside delay data.** NAS-attributed delays include weather flow restrictions. Splitting structural from
  observed pressure and printing the weather share prevents reading a bad-weather airport as capacity-constrained.
- **Fable 5.1 by default.** Best tool-selection and explanation quality; 20-50 s and ~$0.30-0.60 per turn via the CLI.
  `claude-sonnet-5` is the cheaper setting; the rules path answers in milliseconds.
- **No T-100.** Unmet demand is measured as pressure, not unserved passengers; estimating load factors would mean
  inventing numbers.
- **Single-analyst security model.** Loopback by default; non-loopback clients refused unless `APP_TOKEN` is set, then
  bearer auth with constant-time comparison on all `/api/*` routes. Secrets only from the shell environment. Same-origin
  CSP and security headers, no CORS, generic client errors with details in the log, atomic cache writes with per-source
  locks and failure back-off. A multi-user deployment would add identity, persistent sessions, audit logging, rate limits.

## 6. Assumptions, uncertainty and scope

Enplanements are boardings, not passengers; CY2025 is preliminary. TAF forecasts are unconstrained; actuals end 2024.
BTS delay metrics: domestic reporting carriers, arrivals-based, trailing 12 months, include weather. "Demonstrated
peak" is historical throughput, not engineered capacity; runway counts proxy the airfield, not terminals or gates.
Scores are relative screening percentiles for diligence, not probabilities or returns. Out of scope: project costs,
ROI, financing, gate/terminal capacity, seats and load factors, cargo, fares, catchment demographics, airline schedule
plans, non-US airports.

## 7. Validation

101 offline pytest tests on real-data fixture slices: parsers (incl. the BTS URL cipher), registry joins and
text-resolution collisions (`AND`, `SEA`, "LA", "Washington state"), normalization, each KPI (determinism, weights,
sensitivity, missing data, confidence), rules router and follow-ups, tool envelopes, grounding check, orchestrator with
a fake LLM (tool loop, fallback), HTTP API (validation, auth, headers, panel/chat consistency), cache back-off.
`scripts/client_run.py` replayed a 16-turn investor session in LLM and rules modes (all answered; findings and fixes in
the client run report). An independent code review of the final version produced the auth, validation, sanitization
and performance changes above.
