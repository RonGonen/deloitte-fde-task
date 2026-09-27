# Client-side run report: an investment manager's session

**Persona.** Managing director at a fund that invests in US airport modernization (terminal expansion, capacity
upgrades). I need to shortlist airports where demand growth meets binding capacity, compare specific airports, understand
*why* an airport ranks where it does, and know exactly what the evidence does and does not cover before I put a name in
front of the investment committee.

**Setup.** Local server (`uvicorn`, 127.0.0.1:8000), Claude Fable 5.1 through the Claude Code CLI login, live FAA/BTS/
OurAirports pulls plus committed snapshots (TAF 2025; BTS on-time May-Jul 2026). The same 16-question session was run
twice: LLM mode and rules-only mode. Transcripts: `docs/client_run_transcript.md` (LLM) and
`docs/client_run_rules_transcript.md` (rules). Run date 2026-09-27.

| | LLM mode (Fable 5.1 via CLI) | Rules mode |
|---|---|---|
| Turns answered | 16 / 16, no fallbacks, no errors | 16 / 16 |
| Median latency per turn | ~31 s (range 19-48 s; 1-4 tool calls per turn) | < 1 s |
| Approx. cost | ~$6-8 for the session | $0 |
| Numbers flagged by the grounding check | Before fixes: 12 of 16 turns, almost all false positives (abbreviations like 0.44M, durations like 1h 42m, figures quoted from earlier turns). After fixes, a four-turn re-run (`docs/client_run_recheck.md`: INV-01, 05, 06, 15) produced zero flags | n/a |

## The four questions from the brief

| Question | Answer the tool gave | Verdict |
|---|---|---|
| New England terminal-expansion candidates | BOS 69.9 (clear leader, still #1 without scale), then PWM 55.2, BTV 53.1, HVN 52.0, BGR/PVD 51.7, BDL 44.3; 233-airport national universe; weights, floor and confidence disclosed | Usable shortlist with reasoning; matches what a regional analyst would expect and explains the surprises (HVN momentum, BDL's size-dependence) |
| LA vs Santa Ana congestion | LAX 55.8 vs SNA 47.5; both below national median on delays/cancellations but 98th percentile on ops per runway; LAX Level 2; "LA" interpreted as LAX with the basin offered as alternative | Correct nuance: neither is delay-heavy, both are structurally saturated |
| % long-haul flights out of Anchorage | 7.7% at 3,000 mi (22.8% at 2,500; 43.0% at 1,500), 6,653 departures, top/longest routes, avg stage 1,626 mi; explicitly domestic-passenger only, cargo/international excluded, confidence medium | Honest answer; the threshold sensitivity and the cargo gap are exactly what I needed to hear |
| Unmet demand at SFO and why | Indicator 76.5/100 with six drivers: 31.6% arrivals delayed (median 21.7%), 54.7% NAS-attributed (median 21.1%), forecast 2035 ops 12% above the 2018 peak, Level 2, 90% of 2019, below-median up-gauging; states plainly that seats/load factors are unavailable so this is pressure, not a passenger count | Best answer of the session; the "why" is deterministic and each reason carries the national median for context |

## Good

- **Every number traced to a named public source with its period.** FAA CY2025 (preliminary) enplanements, TAF 2025
  actuals/forecast, BTS Aug 2025-Jul 2026 delay causes, BTS May-Jul 2026 routes, OurAirports runways, FAA slot page
  (2026-08-11). The sources panel under each answer lists them; the data panel shows the raw tool payload.
- **Deterministic core, LLM narration.** Identical questions produce identical scores in both modes; the LLM never
  recomputed or re-weighted. When I asked to ignore scale it re-ran the tool with `scale=0` and showed the renormalized
  weights (37.5/37.5/25) rather than eyeballing a new order.
- **Follow-ups worked across 16 turns:** "the second one", "add SFO to that comparison", "which of these are slot
  constrained?" (answered from context, no tool call), "why is the first ranked above the second?" (LLM pulled scores,
  two demand-pressure profiles and the methodology and produced a component-by-component comparison).
- **Ambiguity is stated, not hidden.** "LA" -> LAX with the alternative offered; slot Level 2 explained as facilitation
  rather than a hard cap; "demonstrated peak" labelled as a 1998/2018 operations count, not engineered capacity.
- **Data gaps handled the way an IC member wants.** ROI (INV-12) and cargo (INV-09) produced no invented figures, a clear
  "out of scope" statement, and a table of the demand-side evidence that *is* available. The uncertainty question
  (INV-11) returned a component-by-component list of what would move the SFO indicator and named the T-100 gap as the
  difference between "pressure" and "unmet demand".
- **Generalization.** Texas top 5 with a 1M floor (AUS 66.1, DFW 57.4, IAH 57.0, HOU 52.5, SAT 39.8) and Boston vs
  Providence by city name both worked first time; the PVD answer correctly diagnosed "imported" late-aircraft delays vs
  BOS's structural NAS-attributed delays.
- **Live operations context.** The FAA NAS feed showed SFO's low-ceiling ground delay program and BOS's wind program during
  the session; the tool kept them out of the scores and said so.
- **Rules mode is a real fallback**, not a stub: all 16 turns answered with the same numbers in under a second, including
  follow-ups, sensitivity and data-gap answers.

## Missing (what I would still need before an investment decision)

1. **Seat capacity and load factors** (BTS T-100). Without them "unmet demand" is a pressure indicator, not a count of
   passengers turned away or a yield signal. The T-100 download could not be scripted in the time available.
2. **Terminal and gate capacity**: gates, peak-hour passengers, level-of-service metrics, security/customs throughput.
   Every score today proxies capacity with runways, slots and delays; a terminal expansion thesis needs terminal data.
3. **Economics**: project costs, capital plans (ACIP), airport financials (CAFR: revenues, debt, cost per enplanement),
   AIP/PFC funding, airline use agreements, rates and charges. ROI cannot be approached without them.
4. **Cargo**: tonnage and freighter movements, material for Anchorage and Memphis-type theses; also absent from long-haul.
5. **International route detail**: BTS on-time data is domestic only; SFO's 29% international enplanement share is
   invisible in delay and route metrics.
6. **Competition and catchment**: MSA population/income growth, leakage to nearby airports (SNA vs LAX/ONT/LGB), airline
   network plans. Forecast growth today is only the FAA TAF.
7. **Trend visuals and export**: no charts of the TAF history/forecast, no CSV/Excel export of a shortlist, no way to
   save or annotate a shortlist between sessions (sessions are in-memory, one hour).
8. **Peer-set choice in the UI**: national percentiles are the right default but I could not ask for "vs New England
   only" or "vs medium hubs" and see how the ranking changes.

## Needs improvement

1. **Latency and cost per turn.** 20-48 s and roughly $0.30-0.60 per answer on Fable 5.1 through the CLI. Streaming the
   answer, showing which tool is running, or defaulting to `claude-sonnet-5` for routine turns would make the chat feel
   responsive. The rules path answers instantly and could be shown first while the LLM narrates.
2. **Grounding check false positives.** The first run flagged 0.44M, "1h 42m", "Lower-48", "100k" and numbers quoted from
   the previous turn. Fixed during this pass (displayed-precision tolerance for abbreviations, lowercase m/b treated as
   units, hyphen lookbehind, method text and a three-turn rolling pool included). Remaining known gap: numbers the model
   derives arithmetically (e.g. "carrier + late aircraft = 71%") are still flagged; a derived-value allowance is future work.
3. **General knowledge leaking into answers.** In the live-status answer the model explained SFO's low-ceiling sensitivity
   by its closely spaced parallel runways. Correct, but not from the data. The system prompt now requires such
   statements to be labelled "general knowledge, not from the data".
4. **NAS vs weather wording.** BTS "NAS" delays include non-extreme weather flow restrictions; only extreme weather is
   in the "weather" bucket. Early answers implied a 2% weather share meant weather was irrelevant. Caveat text in the
   congestion and demand tools now says this explicitly.
5. **Rules-mode conversation memory** lost the ranking context after a profile follow-up (INV-03 fell back to help text)
   and answered "why is #1 above #2" with a profile. Fixed: per-tool memory and a why-comparison intent; covered by tests.
6. **Airport names.** FAA legal names ("General Edward Lawrence Logan International") clutter tables in rules mode; the
   LLM already says "Boston Logan". A common-name alias table would help both modes.
7. **Ops-per-runway saturates** at the top (LAX, SNA and SFO all ~98th percentile) so it separates small from large
   airports better than large from large; a log or capped transform, or FAA-published runway capacity benchmarks, would
   sharpen comparisons among hubs.
8. **Voice** was not exercised in this run (no browser automation available); it uses the browser Web Speech API and
   needs a manual check in Chrome.

## Fixes applied during the run

- Per-tool session memory; "why is X ranked above Y" intent; slot-status intent; broader cost/ROI detection.
- Grounding check: abbreviation precision, duration/unit suffixes, hyphenated numbers, method text, rolling three-turn pool.
- Caveat text on NAS vs weather; system-prompt rule for labelling general knowledge.
- Congestion results now expose the universe size and floor so "100k+" is traceable.

## Recommended next steps (priority order)

1. Pull BTS T-100 segment data (seats, passengers, international, cargo) via an authenticated or scheduled download and
   add load factor and cargo tonnage to the demand and long-haul tools.
2. Add terminal/gate inventory and FAA runway capacity benchmarks (Airport Capacity Profiles) as structural inputs.
3. Add airport financials (FAA CATS operating and financial summary) and ACIP project lists to move from "pressure" to an
   investment case with cost per enplanement and capital plan context.
4. Stream answers and surface tool progress; make the model configurable per turn (Fable for analysis, Sonnet for chat).
5. Charts (TAF history/forecast, delay trend) and CSV export of shortlists.
