# Investor Customer Acceptance Test Plan

## Customer Lens

I am an analyst at a U.S. airport-modernization investment firm. I use the tool to shortlist markets, compare target airports, understand what a screen does and does not show, and decide which opportunities deserve diligence. Passenger growth is useful evidence, but it is not itself proof of constrained capacity or a positive investment return.

## Test Setup

- Run `npm install` and `npm start`, then open `http://127.0.0.1:3000`.
- Run the repeatable API checks with `node scripts/customer-acceptance.js`.
- The live FAA test period in this run was calendar 2024 to 2025; the 2025 FAA workbook was preliminary.
- LLM mode was not configured. These scenarios test the rules-based planner, real data adapters, and browser-style history/context payload.
- The operational example is expected to say `DEMO`. It is not accepted as evidence about current airport operations.

## Acceptance Scenarios

| ID | Investor workflow | Expected evidence / behavior | Result |
| --- | --- | --- | --- |
| INV-01 | Rank busiest airports nationally | Live FAA enplanements, clear period, top airports and source link | PASS: ATL, DFW, ORD, DEN, LAX returned for preliminary 2025 |
| INV-02 | Re-sort prior list by growth | Same five airports retained; order changes to growth without losing context | PASS |
| INV-03 | Find California growth, minimum 100,000 passengers | Every result is CA and meets the stated scale floor; cutoff is repeated in answer | PASS |
| INV-04 | Find New England expansion candidates | Six-state scope and the 65/35 expansion screen are disclosed; limitations avoid claiming proven capacity need | PASS |
| INV-05 | Compare BOS and SEA | Same FAA period and metric; identifiers map correctly despite `SEA` also being a state code | PASS |
| INV-06 | Add SFO to the active comparison | Existing BOS/SEA comparison retained and SFO appended | PASS |
| INV-07 | Inspect LAX | FAA traffic plus facility type, scheduled-service flag, and coordinates | PASS |
| INV-08 | Ask for BOS project ROI | No invented return; explicit statement that financial/project/capacity inputs are missing | PASS |
| INV-09 | Compare LAX and SNA congestion | Response is visibly `DEMO` and says values are synthetic | PASS |

All nine API scenarios passed. The browser was also checked at 390px width; the document had no horizontal overflow. Unit tests: 15 passed, 0 failed.

## What Worked

- National, state, and named-airport exploration uses the live FAA annual enplanement workbook. Responses include the source workbook, year pair, preliminary status, growth, and boarding counts.
- Passenger scale can be constrained in natural language, for example “at least 100,000 annual enplanements.” This reduces misleading small-base growth results while leaving the threshold under the user's control.
- Follow-ups reuse the previous ranked airport set, comparison participants, or selected airport. Users can re-sort a result, choose “the second one,” or add another airport.
- Airport identifiers are joined to facility reference data with IATA-over-GPS/local collision precedence. LAX, SFO, and BOS were verified as large scheduled-service airports.
- Unsupported ROI and terminal-capacity questions do not return an unrelated airport profile as though it answered the question.
- Calculations remain deterministic in rules-only mode. The optional LLM is not required to execute the tested workflows.

## Missing

- **Decision-grade capacity:** the FAA enplanement workbook does not include terminal design capacity, hourly throughput, gate utilization, queueing, peak-hour demand, or remaining expansion capacity.
- **Economics:** project scope, modernization/construction costs, capital plan, airport financials, funding, operating costs, and project-specific ROI/payback are not integrated.
- **Forecast and demand:** no catchment population, origin-destination demand forecast, airline schedule/frequency trend, fares, leakage to competing airports, or unserved booking/search data.
- **Live operations:** BTS delay/on-time measures, cancellations, and route-frequency measures are still synthetic `DEMO` examples. The public BTS catalog entries found in this pass did not expose dependable row-level airport data through the queried Socrata surfaces.
- **Investment context:** no project pipeline, sponsor/ownership constraints, environmental/community constraints, permitting timeline, or comparable project outcomes.
- **LLM mode:** no configured key was available in this acceptance environment, so broader semantic interpretation is not part of the pass criteria; common intents and tested follow-ups work with rules.

## Changes Made During Testing

- Added an explicit minimum annual-enplanement filter for regional growth screens.
- Prevented the word “And” from being interpreted as FAA airport code `AND` in follow-up comparisons.
- Prioritized named-airport comparisons over state-code and generic passenger-ranking heuristics, avoiding the BOS/SEA collision.
- Made the expansion answer name New England and state its 65% growth / 35% passenger-scale score instead of describing it as a plain passenger sort.
- Added an explicit response for ROI, modernization cost, and terminal-capacity questions when evidence is unavailable.
- Added a reusable acceptance runner and tests for the detected regressions.

## Recommended Next Changes

1. Replace the operational demo fixtures with an audited, matched-period BTS on-time/delay dataset adapter; do not remove `DEMO` until data freshness, airport coverage, delay definitions, and joins are tested.
2. Add airport financial and project-capacity datasets, then design an explicit investment case with sensitivity ranges rather than equating passenger growth to ROI.
3. Keep volume floors, time windows, and inclusion rules visible as controls; add sensitivity comparison for investment-score weights.
4. Add airport-pair/catchment competition and scheduled-route trends before making demand or connectivity recommendations.
5. In investment screens, consider returning both absolute growth rate and passenger count prominently; high growth at a small baseline may be strategically interesting but should not obscure scale.
