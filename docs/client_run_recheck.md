# Client run transcript (claude_cli, claude-fable-5-1)

## INV-01: Which airports in New England are strong candidates for terminal expansion?
*Purpose:* PDF question 1: ranked screen with method and caveats

*mode=llm tools=['rank_airports'] latency=36.5s confidence=['high'] warnings=[]*

**Boston Logan (BOS) is the clear New England standout (Expansion Opportunity Score 69.9), with Portland ME (PWM, 55.2), Burlington (BTV, 53.1) and New Haven (HVN, 52.0) forming a distant second tier.** All 10 New England airports above the 100,000-enplanement floor were scored against a 233-airport national universe.

**Evidence**

| Rank | Airport | Score | Growth | Momentum | Cap. pressure | Scale | Enplanements CY2025 | YoY | TAF 10-yr CAGR | Arrivals delayed 15+ min |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | BOS | 69.9 | 74.5 | 34.1 | 73.6 | 93.5 | 21.0M | -0.3% | 2.38% | 25.9% |
| 2 | PWM | 55.2 | 53.2 | 64.6 | 48.0 | 59.5 | 1.29M | +5.3% | 1.98% | 20.9% |
| 3 | BTV | 53.1 | 59.7 | 40.3 | 58.7 | 47.4 | 0.71M | +5.9% | 2.09% | 24.4% |
| 4 | HVN | 52.0 | 39.0 | 89.1 | 43.2 | 47.8 | 0.74M | +25.2% | 1.77% | n/a |
| 5 | BGR | 51.7 | 64.9 | 56.5 | 46.2 | 35.3 | 0.44M | +16.1% | 2.18% | 21.9% |
| 6 | PVD | 51.7 | 30.3 | 75.8 | 45.4 | 69.4 | 2.12M | +6.7% | 1.54% | 23.6% |
| 7 | BDL | 44.3 | 27.3 | 28.1 | 50.5 | 76.7 | 3.28M | -0.1% | 1.47% | 23.5% |

MHT (35.5), ACK (37.1) and ORH (25.1) round out the region. Sources: FAA enplanements (CY2025 preliminary), FAA TAF 2025, BTS delay causes (Aug 2025–Jul 2026), OurAirports, FAA Slot Administration.

**Why**
- **BOS** combines national-top-decile scale with the region's highest forecast growth and capacity pressure: 80,268 operations per qualifying runway, forecast operations already 1.08× its demonstrated peak, and 42% of delays attributed to NAS (volume/flow) causes. Its weak spot is flat recent demand (-0.3% YoY).
- **PWM, BTV, BGR** score on growth/momentum rather than binding capacity; forecast operations sit at 0.57–0.83× their peaks, so pressure is modest.
- **HVN** is a pure momentum story (+25% YoY, recovery ratio ~12× vs 2019 from a very low base) with weaker long-run forecast growth.
- **PVD and BDL** have scale but rank low on TAF forecast growth (1.5% CAGR), dragging their scores.

**Assumptions & uncertainty**
- Scores are relative national percentiles for screening, not return estimates; they exclude project cost, terminal/gate capacity and financing.
- CY2025 enplanements are preliminary; TAF actuals run through 2024 and forecasts are unconstrained (assume capacity is provided).
- BTS delay data is domestic, arrivals-based, trailing 12 months; HVN, ACK and ORH have no BTS delay coverage, so their capacity-pressure scores rest on structural factors only.
- Runway counts are an airfield proxy, not terminal capacity. Confidence: high for all 10.

**Suggested follow-ups**
- "Why is BOS's unmet demand so high — what's the demand-pressure breakdown?"
- "Re-rank New England with less weight on scale to see the smaller-airport picture."

## INV-05: Compare LA and Santa Ana airport congestion levels.
*Purpose:* PDF question 2: congestion comparison

*mode=llm tools=['compare_congestion', 'resolve_airports'] latency=38.1s confidence=['high', 'high'] warnings=[]*

**LAX is moderately more congested than Santa Ana (Congestion Index 55.8 vs 47.5), but both sit in the middle of the national range: their delay and cancellation rates are actually *below* the national median, and their scores are driven by very high runway utilisation and NAS-attributed delays.** I interpreted "LA" as LAX (Los Angeles International); if you meant the wider LA basin (BUR, LGB, ONT) I can add those.

**Evidence** (BTS delay causes Aug 2025–Jul 2026; taxi-out snapshot May–Jul 2026; TAF 2025 operations; OurAirports runways)

| Metric | LAX | SNA | National median |
|---|---|---|---|
| Congestion Index (0–100) | 55.8 | 47.5 | — |
| Arrivals delayed 15+ min | 19.7% (28th pctl) | 18.3% (21st pctl) | 21.7% |
| Departures delayed 15+ min | 23.7% | 24.2% | — |
| Delays attributed to NAS (volume/flow) | 25.2% (81st pctl) | 23.4% (73rd pctl) | 21.1% |
| Arrivals cancelled | 1.02% | 0.91% | 1.81% |
| Avg delay per delayed arrival | 67.3 min | 54.5 min | — |
| Avg taxi-out | 18.2 min (80th pctl) | 16.3 min (56th pctl) | 15.8 min |
| Ops per qualifying runway | 141,795 (4 runways) | 122,269 (1 runway) | 17,332 |
| Slot status | Level 2 (schedule-facilitated) | Not slot-controlled | — |
| Arrivals, trailing 12 months | 194,369 | 45,961 | — |
| Enplanements CY2025 (prelim.) | 36.5M | 5.5M | — |

Live FAA status: no active delay programs at either airport (checked 27 Sep 2026, 16:21 GMT).

**Why it matters**
- Both airports are in the **98th percentile for operations per runway**, meaning the airfield is intensively used; the 8-point gap comes mainly from LAX's longer taxi-outs (80th vs 56th pctl) and higher NAS share.
- SNA's single-runway utilisation (~122k ops on one runway) is a structural constraint; LAX has more runways but spreads ~567k annual operations across them.
- Because on-time performance at both is better than the median, congestion here is a story of *system saturation* (NAS causes, taxi times, runway load) rather than chronic unreliability—relevant to whether terminal expansion would be airfield-constrained.

**Assumptions & uncertainty**
- The Congestion Index is a relative national percentile composite (233 airports ≥100k enplanements), not a capacity measure.
- BTS data covers domestic reporting carriers only, arrivals-based; LAX's large international operation is not in the delay or taxi-out figures, so its congestion is likely understated relative to SNA.
- TAF operations are 2024 actuals; runway counts are an airfield proxy, not terminal/gate capacity. Confidence: high for both.

**Suggested follow-ups**
- "What's the unmet-demand breakdown for SNA given its single runway?"
- "Add BUR, LGB and ONT to see the full LA basin."

## INV-06: Add SFO to that comparison.
*Purpose:* Follow-up: extend comparison set

*mode=llm tools=['compare_congestion'] latency=39.0s confidence=['high'] warnings=[]*

**SFO is in a different league: Congestion Index 85.5 versus 55.8 for LAX and 47.5 for SNA.** It ranks in the top 3% nationally on arrival delays, NAS-attributed delays and taxi-out time, and it currently has an active ground delay program (low ceilings, ~49 min average, 1 h 42 min max).

**Evidence** (BTS delay causes Aug 2025–Jul 2026; taxi-out snapshot May–Jul 2026; TAF 2025 operations; OurAirports runways)

| Metric | SFO | LAX | SNA | National median |
|---|---|---|---|---|
| Congestion Index (0–100) | **85.5** | 55.8 | 47.5 | — |
| Arrivals delayed 15+ min | 31.6% (98th pctl) | 19.7% (28th) | 18.3% (21st) | 21.7% |
| Departures delayed 15+ min | 34.5% | 23.7% | 24.2% | — |
| Delays attributed to NAS | 54.7% (98th pctl) | 25.2% (81st) | 23.4% (73rd) | 21.1% |
| Extreme-weather share of delays | 2.0% | 3.4% | 2.5% | — |
| Arrivals cancelled | 1.11% | 1.02% | 0.91% | 1.81% |
| Avg delay per delayed arrival | 66.1 min | 67.3 min | 54.5 min | — |
| Avg taxi-out | 25.1 min (98th pctl) | 18.2 min (80th) | 16.3 min (56th) | 15.8 min |
| Ops per qualifying runway | 92,969 (4 rwys, 90th pctl) | 141,795 (4 rwys, 98th) | 122,269 (1 rwy, 98th) | 17,332 |
| Slot status | Level 2 | Level 2 | Not slot-controlled | — |
| Arrivals, trailing 12 months | 150,816 | 194,369 | 45,961 | — |
| Enplanements CY2025 (prelim.) | 26.3M | 36.5M | 5.5M | — |
| Live FAA status (27 Sep 2026, 16:21 GMT) | Ground delay program, low ceilings | None | None | — |

**Why it matters**
- SFO's congestion is overwhelmingly a **flow/airspace problem**: over half of its delay minutes are NAS-attributed (volume and non-extreme weather flow restrictions such as low ceilings), versus roughly a quarter at LAX and SNA. Today's ground delay program for low ceilings is a live example of that pattern.
- Unlike LAX and SNA, whose on-time performance is *better* than the national median, SFO's arrival and departure delay rates are near the top of the country, and its 25-minute taxi-outs point to surface and departure-queue saturation.
- Notably, SFO has *lower* operations per runway than LAX or SNA, so its congestion is less about raw runway load and more about how usable the airfield is under adverse ceilings. General knowledge, not from the data: SFO's closely spaced parallel runways lose arrival capacity in low-visibility conditions, which is consistent with the NAS-heavy profile.
- For an expansion thesis, this suggests SFO's binding constraint is airfield/airspace throughput rather than terminal space, which would need to be weighed against any terminal investment.

**Assumptions & uncertainty**
- The Congestion Index is a relative national percentile composite across 233 airports with ≥100k enplanements; it is not a capacity measure.
- BTS figures are domestic reporting-carrier arrivals only; SFO and LAX both have large international operations not captured, so absolute congestion is likely understated at both.
- TAF operations are 2024 actuals; runway counts are an airfield proxy, not terminal or gate capacity. Live status is a point-in-time snapshot. Confidence: high for all three.

**Suggested follow-ups**
- "What's SFO's unmet-demand breakdown — is forecast demand already above its demonstrated peak?"
- "Rank SFO, LAX and SNA as expansion candidates to see how congestion trades off against growth and scale."

## INV-15: Any delays at SFO right now?
*Purpose:* Live status

*mode=llm tools=['live_airport_status'] latency=28.2s confidence=['high'] warnings=[]*

**Yes — SFO currently has an active FAA ground delay program due to low ceilings, with average delays of 49 minutes and a maximum of 1 hour 42 minutes.** No ground stop or closure is in effect.

**Evidence** (FAA NAS Status, live; updated Sun 27 Sep 2026 16:21 GMT, retrieved 16:21:49 GMT)

| Item | SFO |
|---|---|
| Event type | Ground delay program |
| Reason | Low ceilings |
| Average delay | 49 minutes |
| Maximum delay | 1 hour 42 minutes |
| Ground stop / closure | None reported |

**Why it matters**
- This is a live example of the structural pattern in SFO's trailing-12-month data: 54.7% of its delay minutes are NAS-attributed (volume and flow restrictions, including non-extreme weather such as low ceilings), and it sits in the 98th percentile nationally for arrival delays and taxi-out time.
- Today's program reinforces the earlier read that SFO's binding constraint is airfield/airspace throughput under adverse ceilings rather than terminal space — relevant to how a terminal investment thesis would be framed.

**Assumptions & uncertainty**
- Live status is a point-in-time operational snapshot; it says nothing about structural capacity and is never used in the Congestion Index or Expansion Opportunity Score.
- Conditions can change within minutes; re-check before relying on this figure. Confidence: high for the snapshot itself.

**Suggested follow-ups**
- "What's SFO's unmet-demand breakdown — how often are its delays NAS-attributed versus carrier or weather?"
- "Are there any nationwide FAA delay programs active right now?"
