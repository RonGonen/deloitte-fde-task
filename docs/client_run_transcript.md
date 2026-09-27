# Client run transcript (claude_cli, claude-fable-5-1)

## INV-01: Which airports in New England are strong candidates for terminal expansion?
*Purpose:* PDF question 1: ranked screen with method and caveats

*mode=llm tools=['rank_airports'] latency=31.8s confidence=['high'] warnings=['Numbers not traceable to a data source: 0.44M']*

**Boston Logan (BOS) is the clear standout in New England (Expansion Opportunity Score 69.9); Portland ME (PWM, 55.2), Burlington (BTV, 53.1) and New Haven (HVN, 52.0) form a second tier, with Bangor and Providence just behind (both 51.7).** All 10 New England airports above the 100,000-enplanement floor were scored; percentiles are national (universe of 233 airports).

**Evidence**

| Rank | Airport | Score | Growth (TAF 10-yr CAGR) | Momentum (FAA YoY) | Capacity pressure | Enplanements CY2025 | Delayed ≥15 min |
|---|---|---|---|---|---|---|---|
| 1 | BOS | 69.9 | 74.5 pct (2.38%) | 34.1 pct (−0.33%) | 73.6 pct | 21.0M | 25.9% (42.2% NAS-attributed) |
| 2 | PWM | 55.2 | 53.2 pct (1.98%) | 64.6 pct (+5.33%) | 48.0 pct | 1.29M | 20.9% |
| 3 | BTV | 53.1 | 59.7 pct (2.09%) | 40.3 pct (+5.85%) | 58.7 pct | 0.71M | 24.4% |
| 4 | HVN | 52.0 | 39.0 pct (1.77%) | 89.1 pct (+25.2%) | 43.2 pct | 0.74M | n/a (no BTS coverage) |
| 5 | BGR | 51.7 | 64.9 pct | 56.5 pct (+16.1%) | 46.2 pct | 0.44M | 21.9% |
| 6 | PVD | 51.7 | 30.3 pct | 75.8 pct (+6.67%) | 45.4 pct | 2.12M | 23.6% |
| 7 | BDL | 44.3 | 27.3 pct | 28.1 pct (−0.05%) | 50.5 pct | 3.28M | 23.5% |
| 8–10 | ACK, MHT, ORH | 37.1 / 35.5 / 25.1 | — | — | — | — | — |

Sources: FAA enplanements (CY2025 preliminary vs CY2024); FAA TAF 2025 (actuals to 2024, forecast 2025–2055); BTS on-time data (Aug 2025–Jul 2026); OurAirports runways; FAA slot administration (page updated 2026-08-11).

**Why**
- **BOS** combines scale (93.5 pct), the region's strongest forecast growth, and the highest capacity pressure: 80,268 ops per qualifying runway, forecast operations already 1.08× its demonstrated peak, and 42% of delays attributed to the NAS. Its weakness is flat recent traffic (−0.3% YoY). It still ranks first without the scale component (64.1).
- **PWM/BGR/PVD/HVN** are momentum stories — HVN's +25% YoY and recovery ratio of 12× vs 2019 reflect a small, rapidly growing base; PVD's momentum is offset by weak forecast growth (30.3 pct).
- **BTV** shows meaningful observed delay pressure (24.4% delayed) on a single qualifying runway.
- **BDL** is large but has soft growth and momentum; its rank drops to 36.2 without scale.

**Assumptions & uncertainty**
- Scores are relative national percentiles for screening, not returns or probabilities; they exclude project cost, terminal/gate capacity and financing.
- CY2025 enplanements are preliminary; TAF forecasts are unconstrained (assume capacity is provided).
- BTS delay data is domestic, arrivals-based and includes weather; HVN, ACK and ORH have no BTS delay coverage, so their pressure scores rest on structural signals only.
- No New England airport is slot-controlled. Confidence: high for all 10.

**Suggested follow-ups**
- "Why is BOS's capacity pressure so high — what is its unmet demand indicator?"
- "Re-rank New England with less weight on scale to surface smaller high-growth airports."

## INV-02: Why is the first one ranked above the second?
*Purpose:* Follow-up: explain drivers using previous result

*mode=llm tools=['rank_airports', 'demand_pressure', 'demand_pressure', 'explain_methodology'] latency=48.4s confidence=['high', 'high', 'high', 'high'] warnings=['Numbers not traceable to a data source: 03m']*

**BOS outranks PWM (69.9 vs 55.2) because it wins three of the four score components — forecast growth, capacity pressure and scale — by wide margins; PWM's only advantage is recent momentum, which carries the smallest weight (20%).** BOS still leads without the scale component (64.1 vs 54.1), so the gap is not just a size effect.

**Evidence — component percentiles (national, 233 airports)**

| Component (weight) | BOS | PWM | Underlying metric |
|---|---|---|---|
| Forecast growth (30%) | 74.5 | 53.2 | TAF 10-yr CAGR 2.38% vs 1.98%; 2035 enplanements 26.8M vs 1.56M |
| Capacity pressure (30%) | 73.6 | 48.0 | Structural 55.6 vs 33.8; observed 91.6 vs 62.2 |
| Demand momentum (20%) | 34.1 | 64.6 | FAA YoY −0.33% vs +5.33%; TAF last-actual growth 6.6% vs 10.0% |
| Scale (20%) | 93.5 | 59.5 | CY2025 enplanements 21.0M vs 1.29M |
| Score without scale | 64.1 | 54.1 | |
| Unmet Demand Indicator | 61.3 | 44.9 | |

Capacity-pressure detail (TAF 2025; BTS Aug 2025–Jul 2026; OurAirports): BOS 80,268 ops per qualifying runway (5 runways) vs PWM 16,618 (2 runways); forecast 2035 operations 1.08× BOS's demonstrated peak (1998) vs 0.83× for PWM; arrivals delayed ≥15 min 25.9% vs 20.9% (national median 21.7%); NAS-attributed delay share 42.2% vs 22.0% (median 21.1%); avg taxi-out 21.4 min vs 15.7 min. Neither is slot-controlled.

**Why it matters**
- **Binding capacity:** BOS is the only one of the two where FAA forecasts demand exceeding anything the airfield has ever handled, and its delays are disproportionately attributed to airport/airspace capacity rather than airline causes — the classic signature of an expansion case. PWM has airfield headroom and its delays are mostly carrier/late-aircraft driven (32% + 43%).
- **Growth base:** BOS's higher CAGR applies to a base ~16× larger, so absolute incremental passengers dwarf PWM's.
- **PWM's case is momentum:** +5.3% YoY, 109% of 2019, and strong up-gauging (+16.9% passengers/op vs +5.2% at BOS) — airlines are growing with bigger aircraft, but pressure signals remain near national medians.
- **BOS's weakness** is flat recent traffic (−0.3% YoY, 101% of 2019), which is why its momentum percentile is low.

**Assumptions & uncertainty**
- Scores are relative national percentiles for screening, not returns; project cost, terminal/gate capacity and financing are excluded.
- CY2025 enplanements are preliminary; TAF actuals end 2024 and forecasts are unconstrained. "Demonstrated peak" is a 1998 operations count, not engineered capacity. BTS delay data is domestic, arrivals-based, includes weather (weather share ~2% at both). No seat/load-factor data, so unserved passengers cannot be counted.
- Live snapshot (27 Sep 2026): BOS under a wind-driven ground delay program (avg 4h 03m); PWM no events. Confidence: high for both.

**Suggested follow-ups**
- "Re-rank New England with momentum weighted higher to see whether PWM closes the gap."
- "Compare congestion for BOS, PWM and PVD in detail."

## INV-03: What if I ignore scale?
*Purpose:* Sensitivity: re-rank with scale weight zero

*mode=llm tools=['rank_airports'] latency=34.9s confidence=['high'] warnings=['Numbers not traceable to a data source: 0.11M, 0.15M, 0.44M, 0.69M, 25.1, 35.5, 37.1, 44.3']*

**Removing scale doesn't dislodge BOS (still #1 at 64.1), but it reshuffles the second tier: Bangor (BGR) jumps from 5th to 2nd (55.8), Burlington (BTV) moves to 3rd (54.5), Portland (PWM) slips from 2nd to 4th (54.1), and New Haven (HVN) is 5th (53.1).** The bigger casualties are the large-but-slow airports: BDL falls from 44.3 to 36.2 and PVD from 51.7 to 47.3.

**Evidence — New England re-ranked, weights renormalized to growth 37.5% / capacity 37.5% / momentum 25% (national percentiles, 233-airport universe)**

| Rank | Airport | Score (no scale) | Prior score | Growth pct | Momentum pct | Cap. pressure pct | Enplanements CY2025 |
|---|---|---|---|---|---|---|---|
| 1 | BOS | 64.1 | 69.9 | 74.5 | 34.1 | 73.6 | 21.0M |
| 2 | BGR | 55.8 | 51.7 | 64.9 | 56.5 | 46.2 | 0.44M |
| 3 | BTV | 54.5 | 53.1 | 59.7 | 40.3 | 58.7 | 0.71M |
| 4 | PWM | 54.1 | 55.2 | 53.2 | 64.6 | 48.0 | 1.29M |
| 5 | HVN | 53.1 | 52.0 | 39.0 | 89.1 | 43.2 | 0.74M |
| 6 | PVD | 47.3 | 51.7 | 30.3 | 75.8 | 45.4 | 2.12M |
| 7 | ACK | 43.6 | 37.1 | 58.9 | 45.0 | 27.4 | 0.15M |
| 8 | BDL | 36.2 | 44.3 | 27.3 | 28.1 | 50.5 | 3.28M |
| 9 | MHT | 32.7 | 35.5 | 30.7 | 40.7 | 29.3 | 0.69M |
| 10 | ORH | 30.8 | 25.1 | 51.1 | 22.5 | 16.1 | 0.11M |

Sources: FAA enplanements (CY2025 preliminary vs CY2024); FAA TAF 2025 (actuals to 2024, forecast 2025–2055); BTS on-time data (Aug 2025–Jul 2026); OurAirports runways; FAA slot administration (page updated 2026-08-11).

**Why the order changes**
- **BOS** was never a pure size story: forecast growth (2.38% CAGR) and capacity pressure (80,268 ops/runway, forecast ops 1.08× demonstrated peak, 42.2% NAS-attributed delays) carry it.
- **BGR** benefits most: strong forecast growth (2.18% CAGR, 64.9 pct) plus +16.1% YoY and 118% of 2019, previously held back by a 35.3 scale percentile. Its airfield is unstressed (forecast ops 0.57× peak), so the case is demand-led rather than congestion-led.
- **BTV** overtakes PWM on capacity pressure (58.7 vs 48.0): 24.4% of arrivals delayed on a single qualifying runway, observed-pressure 87.2.
- **PWM** loses its 59.5 scale percentile and its remaining edge is momentum, which now weighs 25%.
- **PVD/BDL** were propped up by scale (69.4 / 76.7 pct); with growth percentiles of 30.3 / 27.3 they drop.

**Assumptions & uncertainty**
- Scores are relative national percentiles for screening, not returns; project cost, terminal/gate capacity and financing are excluded. Dropping scale means small bases (BGR 0.44M, ACK 0.15M) rank on rates of change, so absolute passenger gains are far smaller than at BOS.
- CY2025 enplanements are preliminary; TAF forecasts are unconstrained. HVN, ACK and ORH have no BTS delay coverage, so their pressure scores rest on structural signals only. Confidence: high for all 10.

**Suggested follow-ups**
- "Run BGR's unmet demand indicator to see whether its growth is meeting any capacity constraint."
- "Compare congestion for BTV, PWM and BGR."

## INV-04: Tell me about the second one, including its forecast to 2035.
*Purpose:* Ordinal follow-up + forecast

*mode=llm tools=['airport_profile', 'demand_pressure'] latency=34.0s confidence=['high', 'high'] warnings=['Numbers not traceable to a data source: 103K']*

**Bangor International (BGR), Maine — a small non-hub airport (national rank #151) with strong recent growth and a demand-led rather than congestion-led expansion case.** FAA's TAF projects enplanements rising from 428,133 (2025 forecast) to 531,188 in 2035, a 2.18% CAGR, above the national median of 1.95%. Its Unmet Demand Indicator is modest at 39.1, because the airfield has ample headroom.

**Evidence**

| Metric | Value | Period / source |
|---|---|---|
| Enplanements | 437,108 (+16.1% YoY vs 376,456) | CY2025 preliminary, FAA |
| TAF actuals | 2019: 301,219 → 2024: 356,569 (118% of 2019) | TAF 2025 |
| TAF forecast | 2025: 428,133 · 2030: 512,998 · **2035: 531,188** · 2045: 568,724 | TAF 2025 (unconstrained) |
| Air-carrier + air-taxi ops | 16,761 (2024) → 20,888 (2035); peak 36,408 (1991) → forecast 0.57× peak | TAF |
| Runways (open, paved, ≥5,000 ft) | 1; not slot-controlled | OurAirports / FAA slot admin |
| Arrivals delayed ≥15 min | 21.9% (median 21.7%); cancellations 3.9% (median 1.8%) | BTS Aug 2025–Jul 2026 |
| Delay causes | Late aircraft 46.9%, carrier 29.1%, NAS 21.1%, weather 2.7% | BTS |
| Avg taxi-out | 18.4 min | BTS May–Jul 2026 |
| Passengers per op | +22.4% since 2019 (median +10.0%) | TAF |
| Expansion Score | 51.7 (55.8 without scale): growth 64.9, momentum 56.5, pressure 46.2, scale 35.3 pct | Tool scores |
| Live status | No events (27 Sep 2026 16:08 GMT) | FAA NAS |

**Why it matters**
- **Growth is real:** FAA's CY2025 count (437K) already exceeds TAF's own 2025 forecast (428K), and the 2024 actual is 18% above 2019 — well above the 1.08 national median recovery.
- **Airlines are up-gauging** (+22.4% passengers/op) — a signal typically seen at constrained airports — yet BGR's airfield is far from constrained (forecast ops 57% of 1991 peak). This points to terminal/passenger-processing demand rather than runway pressure.
- **Delays are airline-driven**, not capacity-driven: 76% of delays are carrier/late-aircraft; NAS share sits at the median. The elevated 3.9% cancellation rate is notable but not attributed to capacity by these data.
- Forecast growth flattens after 2030 (513K → 531K in 2035), so the TAF sees most expansion in the near term.

**Assumptions & uncertainty**
- Scores are national percentiles for screening, not returns; project cost, terminal/gate capacity and financing are not covered. Small base: 2035 gain is ~103K enplanements over the 2025 forecast.
- CY2025 enplanements are preliminary; TAF actuals end 2024 and forecasts are unconstrained. "Demonstrated peak" is a 1991 ops count, not engineered capacity. BTS data is domestic, arrivals-based, includes weather; no seat/load-factor data. International share is negligible (0.0003%). Confidence: high.

**Suggested follow-ups**
- "Compare congestion for BGR, PWM and BTV."
- "How does BGR's forecast growth compare with the third one (BTV) to 2035?"

## INV-05: Compare LA and Santa Ana airport congestion levels.
*Purpose:* PDF question 2: congestion comparison

*mode=llm tools=['compare_congestion'] latency=33.7s confidence=['high'] warnings=['Numbers not traceable to a data source: 100k, 71, 74']*

**LAX is more congested than John Wayne/Orange County (SNA) — Congestion Index 55.8 vs 47.5 — but both airports are actually *below* the national median on raw delay and cancellation rates; their indices are lifted by extreme runway utilisation and a high share of delays attributed to airspace/airport capacity.** I interpreted "LA" as Los Angeles International (LAX); if you meant the whole LA basin (BUR, ONT, LGB, SNA), I can run that instead.

**Evidence (BTS on-time data Aug 2025–Jul 2026; TAF 2025 operations; OurAirports runways; national percentiles across 100k+ enplanement airports)**

| Metric (weight) | LAX | SNA | National median |
|---|---|---|---|
| Congestion Index | **55.8** | **47.5** | — |
| Arrivals delayed ≥15 min (35%) | 19.7% (28.4 pct) | 18.3% (20.9 pct) | 21.7% |
| Delays attributed to NAS (20%) | 25.2% (80.6 pct) | 23.4% (72.5 pct) | 21.1% |
| Arrivals cancelled (15%) | 1.02% (20.4 pct) | 0.91% (17.5 pct) | 1.81% |
| Avg taxi-out, May–Jul 2026 (15%) | 18.2 min (79.9 pct) | 16.3 min (55.9 pct) | 15.8 min |
| Ops per qualifying runway (15%) | 141,795 (4 runways; 97.6 pct) | 122,269 (1 runway; 97.6 pct) | 17,332 |
| Avg delay per delayed arrival | 67.3 min | 54.5 min | — |
| Departures delayed ≥15 min | 23.7% | 24.2% | — |
| Slot status | Level 2 (schedule-facilitated) | Not slot-controlled | — |
| Enplanements CY2025 (prelim.) | 36.5M | 5.5M | — |
| Live FAA status (27 Sep 2026 16:08 GMT) | No events | No events | — |

**Why it matters**
- **Structural saturation at both:** each runs its runways at roughly 7–8× the national median operations rate, placing both in the 98th percentile. SNA does this on a single qualifying runway, LAX across four.
- **Capacity-type delays:** at both airports the NAS share of delays is well above median (LAX 25.2%, SNA 23.4% vs 21.1%), the signature of airport/airspace constraints rather than airline operations — though carrier and late-aircraft causes still account for ~71–74% of delays.
- **Operational resilience is good:** low cancellation rates (~1%) and below-median arrival delay rates suggest both airports currently absorb their traffic, but LAX's delays, when they occur, are long (67 min) and its taxi-out times sit in the 80th percentile.
- **LAX's Level 2 status** is an additional formal indicator of schedule pressure; SNA has no slot regime, so its constraint signal comes from runway loading alone.

**Assumptions & uncertainty**
- The Congestion Index is a relative national percentile composite, not a measure of capacity or returns. Runway counts (open, paved, ≥5,000 ft) proxy the airfield, not terminals or gates.
- BTS data covers domestic flights of reporting carriers, arrivals-based, and includes weather-driven delays (weather share 3.4% at LAX, 2.5% at SNA); LAX's large international operation is not captured in delay or taxi-out figures. Taxi-out is a 3-month snapshot (May–Jul 2026). TAF operations are 2024 actuals. Confidence: high for both.

**Suggested follow-ups**
- "Score LAX and SNA as expansion candidates, or rank all LA-basin airports."
- "What is LAX's unmet demand indicator — is forecast traffic exceeding its demonstrated peak?"

## INV-06: Add SFO to that comparison.
*Purpose:* Follow-up: extend comparison set

*mode=llm tools=['compare_congestion'] latency=30.1s confidence=['high'] warnings=['Numbers not traceable to a data source: 100k, 42m']*

**SFO is by far the most congested of the three — Congestion Index 85.5 vs LAX 55.8 and SNA 47.5 — and unlike the two Southern California airports it is above the national median on nearly every raw delay measure, not just runway loading.** It is also under a low-ceiling ground delay program right now.

**Evidence (BTS on-time data Aug 2025–Jul 2026; TAF 2025 operations; OurAirports runways; national percentiles across 100k+ enplanement airports)**

| Metric (weight) | SFO | LAX | SNA | National median |
|---|---|---|---|---|
| Congestion Index | **85.5** | 55.8 | 47.5 | — |
| Arrivals delayed ≥15 min (35%) | 31.6% (97.6 pct) | 19.7% (28.4 pct) | 18.3% (20.9 pct) | 21.7% |
| Delays attributed to NAS (20%) | 54.7% (97.6 pct) | 25.2% (80.6 pct) | 23.4% (72.5 pct) | 21.1% |
| Arrivals cancelled (15%) | 1.11% (24.6 pct) | 1.02% (20.4 pct) | 0.91% (17.5 pct) | 1.81% |
| Avg taxi-out, May–Jul 2026 (15%) | 25.1 min (97.6 pct) | 18.2 min (79.9 pct) | 16.3 min (55.9 pct) | 15.8 min |
| Ops per qualifying runway (15%) | 92,969 (4 runways; 90.0 pct) | 141,795 (4; 97.6 pct) | 122,269 (1; 97.6 pct) | 17,332 |
| Departures delayed ≥15 min | 34.5% | 23.7% | 24.2% | — |
| Avg delay per delayed arrival | 66.1 min | 67.3 min | 54.5 min | — |
| Slot status | Level 2 | Level 2 | None | — |
| Enplanements CY2025 (prelim.) | 26.3M | 36.5M | 5.5M | — |
| Live FAA status (27 Sep 2026 16:08 GMT) | Ground delay, low ceilings (avg 49 min, max 1h 42m) | No events | No events | — |

**Why it matters**
- **SFO's delays are capacity-type delays:** 54.7% are attributed to the NAS (airport/airspace capacity) — more than double the median and the top percentile nationally — while carrier (21.9%) and late-aircraft (21.4%) shares are far lower than at LAX/SNA (~35% each). That is the strongest signature of a binding airfield/airspace constraint among the three.
- **Chronic, not episodic:** roughly one in three arrivals and departures at SFO is delayed 15+ minutes, and taxi-out averages 25 minutes (98th percentile). Today's low-ceiling ground delay program illustrates the weather-sensitive pattern, though the BTS weather-cause share itself is small (2.0%).
- **LAX and SNA** remain structurally saturated (98th percentile ops per runway) but absorb traffic with below-median delay and cancellation rates; SFO runs fewer ops per runway (92,969) yet delays far more — pointing to airspace/approach constraints rather than runway count alone.
- Cancellations are low at all three (~1%), below the 1.81% median.

**Assumptions & uncertainty**
- The Congestion Index is a relative national percentile composite, not capacity or returns; runway counts (open, paved, ≥5,000 ft) proxy the airfield, not terminals or gates.
- BTS data: domestic reporting carriers, arrivals-based, includes weather-driven delays; SFO's and LAX's large international operations are not captured. Taxi-out is a 3-month snapshot (May–Jul 2026); TAF operations are 2024 actuals. Live status is a single snapshot and is never scored. Confidence: high for all three.

**Suggested follow-ups**
- "What is SFO's unmet demand indicator — is forecast traffic above its demonstrated peak?"
- "Score SFO, LAX and SNA as expansion candidates."

## INV-07: Which of these are slot constrained?
*Purpose:* Structural constraint question on active set

*mode=llm tools=[] latency=20.8s confidence=[] warnings=[]*

**Two of the three are slot-constrained: SFO and LAX are both IATA Level 2 (schedule-facilitated) airports; SNA is not slot-controlled.** None of the three is Level 3 (fully slot-coordinated), so neither SFO nor LAX has hard slot caps — Level 2 means airlines' schedules are facilitated to smooth peaks, a formal FAA signal of schedule pressure short of outright rationing.

**Evidence (FAA slot administration, page updated 2026-08-11; congestion metrics BTS Aug 2025–Jul 2026; TAF 2025 operations; OurAirports runways)**

| Airport | Slot status | Congestion Index | Ops per qualifying runway | Delays attributed to NAS | Arrivals delayed ≥15 min |
|---|---|---|---|---|---|
| SFO | **Level 2** (schedule-facilitated) | 85.5 | 92,969 (4 runways) | 54.7% | 31.6% |
| LAX | **Level 2** (schedule-facilitated) | 55.8 | 141,795 (4 runways) | 25.2% | 19.7% |
| SNA | Not slot-controlled | 47.5 | 122,269 (1 runway) | 23.4% | 18.3% |

**Why it matters**
- **SFO's Level 2 status matches its data:** the highest congestion index of the three, 54.7% of delays attributed to airport/airspace capacity (top percentile nationally) and nearly one in three arrivals delayed. Schedule facilitation there reflects a genuinely binding airfield/airspace constraint — the strongest expansion-pressure signature in this set.
- **LAX's Level 2 status is a peak-schedule signal** rather than a chronic-delay one: it runs the highest runway loading of the three (141,795 ops per runway, 98th percentile) but keeps arrival delays below the 21.7% national median. Facilitation here indicates demand is being managed around peaks.
- **SNA has no slot regime**, yet it loads its single qualifying runway at 122,269 ops (98th percentile) — its constraint signal comes entirely from runway utilisation and its above-median NAS share, not from a formal FAA schedule mechanism. Note that these tools cover FAA slot status only; any local operating restrictions at SNA are outside the data.

**Assumptions & uncertainty**
- Slot status is taken from the FAA slot administration page as of 2026-08-11; it is a categorical designation, not a measure of how many slots are available or requested. Level 2 is not equivalent to a hard cap on operations.
- The Congestion Index is a relative national percentile composite, not a capacity measure or return. BTS data is domestic, arrivals-based and includes weather; international operations at SFO and LAX are not captured. Runway counts (open, paved, ≥5,000 ft) proxy the airfield, not gates or terminals. Confidence: high for all three.

**Suggested follow-ups**
- "What is SFO's unmet demand indicator — does forecast traffic exceed its demonstrated peak?"
- "Score SFO, LAX and SNA as expansion candidates."

## INV-08: What is the percentage of long haul flights out of Anchorage airport?
*Purpose:* PDF question 3: long-haul share with scoping

*mode=llm tools=['long_haul_share'] latency=28.0s confidence=['medium'] warnings=['Numbers not traceable to a data source: 48']*

**About 7.7% of Anchorage (ANC) domestic departures are long-haul at the 3,000-mile headline threshold — but the share is highly sensitive to the cutoff (22.8% at 2,500 mi, 43.0% at 1,500 mi), and the figure understates ANC's true long-haul activity because international and all-cargo flights are not in the data.**

**Evidence (BTS on-time records, May–Jul 2026 snapshot; 6,653 scheduled domestic departures to 34 destinations)**

| Threshold | Departures | Share |
|---|---|---|
| ≥ 3,000 mi (headline) | 515 | **7.7%** |
| ≥ 2,500 mi | 1,516 | 22.8% |
| ≥ 1,500 mi | 2,862 | 43.0% |
| Average stage length | — | 1,626 mi |

- **Top routes:** SEA 1,970 departures (1,448 mi), ORD 388 (2,846 mi), DEN 382 (2,405 mi), PDX 355 (1,542 mi), JNU 355 (571 mi), FAI 337 (261 mi), MSP 285 (2,519 mi), ADQ 263, BET 183, SFO 169 (2,018 mi).
- **Longest routes (all ≥3,000 mi):** ATL 3,417 mi (75 departures), JFK 3,386 mi (53), BOS 3,383 mi (7), EWR 3,370 mi (72), IAD 3,356 mi (72).
- **TAF context (2024):** 2.73M enplanements; 214,389 air-carrier + air-taxi operations; international enplanement share 1.0%. ANC has 3 qualifying runways and is not slot-controlled.

**Why it matters**
- ANC's domestic network is bimodal: a dense intra-Alaska short-haul feed (JNU, FAI, ADQ, BET) and a Lower-48 trunk anchored by Seattle at ~1,450 mi — just under the 1,500-mi line, which is why the share jumps sharply between thresholds. Only the East Coast routes (ATL, NYC, DC, BOS) clear 3,000 mi.
- For terminal planning, the long-haul mix matters because longer flights typically use larger aircraft and carry more passengers per departure; a departure-weighted share therefore understates long-haul's passenger footprint.

**Assumptions & uncertainty**
- Data covers domestic scheduled passenger flights of BTS reporting carriers only — no international, no all-cargo, no small regional/intrastate operators. As a cargo gateway, ANC's true long-haul share is understated; the tools cannot quantify the cargo component (cargo tonnage is out of scope).
- Departure-count weighted, not seat- or passenger-weighted; distances are great-circle stage lengths in statute miles. Three-month summer snapshot (May–Jul 2026), which may not reflect winter scheduling. TAF international share (1.0%, 2024) is a complementary indicator only.
- Confidence: **medium**, because of the missing international and cargo flights.

**Suggested follow-ups**
- "What is ANC's unmet demand indicator and expansion score?"
- "Compare ANC's congestion with SEA and PDX."

## INV-09: What about cargo at Anchorage?
*Purpose:* Scope boundary: cargo not measurable

*mode=llm tools=[] latency=19.4s confidence=[] warnings=[]*

**Cargo activity at Anchorage is out of scope for this service — none of the sources available to me (FAA enplanements, FAA TAF, BTS on-time data, OurAirports, FAA slot/NAS status) report cargo tonnage, freighter movements or cargo carriers, so I cannot give you a cargo figure or a cargo-inclusive long-haul share.**

**What the available data does and does not say (from the ANC long-haul result above)**

| Item | Value | Period / source |
|---|---|---|
| Domestic scheduled passenger departures analysed | 6,653 to 34 destinations | BTS, May–Jul 2026 |
| Long-haul share (≥3,000 mi / ≥2,500 mi / ≥1,500 mi) | 7.7% / 22.8% / 43.0% | BTS, May–Jul 2026 |
| Air-carrier + air-taxi operations | 214,389 | TAF 2025 (2024 actual) |
| Enplanements | 2.73M; international share 1.0% | TAF 2025 (2024 actual) |
| Qualifying runways / slot status | 3 / not slot-controlled | OurAirports / FAA |
| Cargo tonnage, freighter operations, cargo carriers | **Not available** | — |

**Why this matters for the earlier answer**
- The 7.7% long-haul share counts only scheduled domestic passenger flights of BTS reporting carriers. All-cargo flights are excluded entirely, so the share is best read as a *passenger-terminal* metric, not a description of ANC's overall airfield activity.
- The TAF operations count (214,389) is an all-operations figure that will include cargo movements, but the TAF does not split passenger from cargo, so the cargo component cannot be isolated from it.
- For a passenger-terminal expansion thesis the passenger-only view is the relevant one; for airfield, apron or cargo-facility questions you would need an external cargo source (e.g., Airports Council International or airport-published cargo statistics), which I cannot access.

**Assumptions & uncertainty**
- No cargo figure of any kind has been provided here; please do not infer one from the passenger data. The passenger long-haul share carries medium confidence because of the missing international and cargo flights.
- Data vintages: BTS three-month summer snapshot (May–Jul 2026); TAF actuals to 2024.

**Suggested follow-ups**
- "What is ANC's expansion score and unmet demand indicator?" (passenger-terminal view, fully in scope)
- "Compare ANC's congestion with SEA and PDX."

## INV-10: What is the unmet flight demand in SFO airport and why?
*Purpose:* PDF question 4: unmet demand indicator + reasons

*mode=llm tools=['demand_pressure'] latency=31.3s confidence=['high'] warnings=[]*

**SFO's Unmet Demand Indicator is 76.5 out of 100 (high confidence, all six components available) — one of the strongest demand-pressure readings in the 233-airport universe. The pressure is driven by chronic capacity-type delays, a forecast that exceeds anything the airfield has ever handled, Level 2 schedule facilitation and a traffic base still 10% below 2019.** Note this is an indicator of demand pressing on capacity, not a count of unserved passengers.

**Evidence — the six components (national percentiles; sources: TAF 2025, BTS Aug 2025–Jul 2026, FAA enplanements CY2025 prelim., FAA slot admin 2026-08-11, OurAirports)**

| Signal | SFO | National median | Percentile |
|---|---|---|---|
| Arrivals delayed ≥15 min | 31.6% | 21.7% | 97.6 |
| Delays attributed to NAS (capacity/airspace) | 54.7% (weather only 2.0%) | 21.1% | 97.6 |
| Recovery vs 2019 enplanements | 90% (24.8M in 2024 vs 27.7M in 2019) | 108% | 87.0 |
| Forecast 2035 ops vs demonstrated peak (2018: 458,577) | 1.12× (514,527 ops) | 0.78× | 84.4 |
| Slot status | Level 2 (schedule-facilitated) | — | 50.0 |
| Up-gauging (passengers/op since 2019) | +7.6% (61.9 → 66.6) | +10.0% | 42.4 |

Supporting facts: 4 qualifying runways at 92,969 ops each; taxi-out 25.1 min; cancellations 1.1%; CY2025 enplanements 26.3M (+4.7% YoY); TAF 2035 forecast 34.6M enplanements (2.85% CAGR vs 1.95% median); international share 29.4% (2024). Live (27 Sep 2026): ground delay program for low ceilings, avg 49 min.

**Why**
- **Capacity-type delays, not airline delays:** more than half of delayed arrivals are attributed to the NAS — top percentile nationally — while carrier and late-aircraft causes are each only ~21–22%. That is the clearest signature of a binding airfield/airspace constraint.
- **Forecast exceeds demonstrated capability:** FAA projects 2035 operations 12% above the 2018 record and 38% above 2024 actuals; the TAF is unconstrained, so this is demand the airfield has never shown it can absorb.
- **Formal FAA recognition:** Level 2 status means schedules are reviewed because runway capacity is constrained.
- **Latent demand:** enplanements at 90% of 2019 imply pre-pandemic demand not yet re-accommodated — even as the airport already runs above-median delays.
- **The one soft signal:** up-gauging is below median, so airlines have not yet fully shifted to larger aircraft as a workaround — leaving room for that lever, or suggesting growth could add frequency and further stress the airfield.

**Assumptions & uncertainty**
- Indicator is a relative national percentile composite for screening — not returns, not a passenger gap. No seat, load-factor or fare data exists in this build, so unserved passengers cannot be counted.
- "Demonstrated peak" is a 2018 ops count, not engineered capacity; fleet and procedures have changed. TAF actuals end 2024; CY2025 enplanements preliminary. BTS data is domestic, arrivals-based, includes weather (weather share shown separately); SFO's large international operation (29% of enplanements) is not in the delay data. Live status is a snapshot and not scored. Confidence: high.

**Suggested follow-ups**
- "Score SFO as an expansion candidate alongside LAX and SNA."
- "How does SFO's unmet demand compare with OAK and SJC in the Bay Area?"

## INV-11: How confident are you in that, and what data would change the answer?
*Purpose:* Uncertainty communication

*mode=llm tools=['explain_methodology', 'explain_methodology', 'explain_methodology'] latency=36.0s confidence=['high', 'high', 'high'] warnings=['Numbers not traceable to a data source: 12, 24.8M, 26.3M, 27.7M, 29.4, 31.6, 42.4, 458,577']*

**Confidence in SFO's 76.5 Unmet Demand Indicator is "high" by the tool's definition — all six components and every data join were available, so nothing was imputed or renormalized. But "high" means data completeness, not that the number is a measured passenger gap; it is a mean of six national percentiles and would move if any of the inputs below changed.**

**How confidence is defined**
- High = every component and data join present; medium = one missing; low = two or more missing or airport outside the scored universe. Missing components are never imputed; weights are renormalized over available ones. Delay metrics require ≥2,000 arrivals.

**What data would change the answer (component → sensitivity)**

| Component | Current input | What would move it |
|---|---|---|
| Recovery vs 2019 (pct 87.0) | TAF actual 2024: 24.8M vs 27.7M in 2019 (90%) | TAF actuals end 2024; CY2025 preliminary FAA count is already 26.3M (+4.7%). When TAF rolls forward, the recovery ratio rises and this component's percentile falls — the most likely near-term downward revision. |
| Forecast ops vs peak (pct 84.4) | 2035 forecast 514,527 vs 2018 peak 458,577 (1.12×) | Peak is a historical ops count, not engineered capacity; a revised TAF (unconstrained) or a capacity study could change this either way. |
| Delays ≥15 min (pct 97.6) / NAS share (pct 97.6) | 31.6% / 54.7%, BTS Aug 2025–Jul 2026 | Rolling 12-month window; domestic reporting carriers, arrivals-based; excludes SFO's international operation (29.4% of 2024 enplanements). Weather share is only 2.0%, so structural congestion dominates. |
| Slot status (pct 50.0) | Level 2, FAA page updated 2026-08-11 | Level 3 would score 100; removal would score 0. |
| Up-gauging (pct 42.4) | +7.6% passengers/op since 2019 | Fleet shifts would raise this. |

**Data that cannot currently be captured**
- No seat, load-factor or fare data (BTS T-100 could not be pulled) — so unserved passengers cannot be counted; this is the biggest gap between "pressure" and "unmet demand".
- Terminal/gate design capacity, project cost/ROI, airline schedule plans and catchment demographics are out of scope entirely.

**Assumptions & uncertainty**
- Indicator is a relative percentile composite for screening; CY2025 enplanements preliminary; TAF forecasts unconstrained; runway counts (open, paved, ≥5,000 ft) proxy airfield only. Directionally robust (four of six components in the 84th–98th percentile), but the exact 76.5 should be expected to shift as data vintages update.

**Suggested follow-ups**
- "Compare SFO's unmet demand with OAK and SJC to see whether Bay Area pressure is airport-specific."
- "Score SFO as an expansion candidate with capacity pressure weighted higher."

## INV-12: What's the ROI of expanding BOS?
*Purpose:* Data gap: must not invent returns

*mode=llm tools=[] latency=21.6s confidence=[] warnings=[]*

**Project ROI is out of scope for this service — none of the sources available to me (FAA enplanements, FAA TAF, BTS on-time data, OurAirports, FAA slot/NAS status) contain project costs, capital budgets, terminal or gate design capacity, fares, or revenue, so I cannot compute or estimate a return on expanding BOS.** What I can offer is the demand-side screening evidence already gathered for BOS, which is the input a diligence team would pair with cost and financing data.

**What the available data says about BOS (from the New England ranking above)**

| Item | Value | Period / source |
|---|---|---|
| Expansion Opportunity Score | 69.9 (#1 in New England; 64.1 without scale) | Tool scores, national percentiles (233 airports) |
| Component percentiles | Growth 74.5 · Capacity pressure 73.6 · Scale 93.5 · Momentum 34.1 | Tool scores |
| Enplanements | 21.0M (−0.33% YoY; 101% of 2019) | FAA CY2025 preliminary |
| TAF forecast | 10-yr CAGR 2.38%; 26.8M enplanements in 2035 | FAA TAF 2025 (unconstrained) |
| Forecast ops vs demonstrated peak (1998) | 1.08× | TAF 2025 |
| Ops per qualifying runway | 80,268 (5 runways) | TAF 2024 actuals / OurAirports |
| Arrivals delayed ≥15 min / NAS-attributed share | 25.9% / 42.2% | BTS Aug 2025–Jul 2026 |
| Avg taxi-out | 21.4 min | BTS May–Jul 2026 |
| Unmet Demand Indicator | 61.3 | Tool score |
| Slot status | Not slot-controlled | FAA slot admin, 2026-08-11 |

**Why this matters for an ROI question**
- The demand-side signature is strong: forecast operations already exceed anything the airfield has demonstrated, and 42% of delays are attributed to airport/airspace capacity — the pattern that typically supports a capacity-expansion thesis.
- The soft spot is recent momentum (flat YoY traffic), which bears on near-term revenue ramp assumptions.
- Cost, phasing, gate/terminal design capacity, airline commitments and financing structure — the other half of any ROI — must come from the airport's capital plan, engineering studies and airline use agreements, which I cannot access.

**Assumptions & uncertainty**
- No ROI, cost or revenue figure of any kind has been provided here; please do not infer one from the scores, which are relative national percentiles for screening, not returns or probabilities.
- CY2025 enplanements are preliminary; TAF actuals end 2024 and forecasts are unconstrained; "demonstrated peak" is a 1998 ops count, not engineered capacity; BTS data is domestic, arrivals-based and includes weather. Confidence in the screening data: high.

**Suggested follow-ups**
- "Run BOS's unmet demand indicator in detail to see which of the six components drive the 61.3."
- "What is BOS's long-haul share, and how does its congestion compare with PVD and BDL?"

## INV-13: Top 5 expansion candidates in Texas with at least 1 million passengers.
*Purpose:* Generalization to another region with a volume floor

*mode=llm tools=['rank_airports'] latency=31.1s confidence=['high'] warnings=[]*

**Austin (AUS) leads Texas with an Expansion Opportunity Score of 66.1, followed by DFW (57.4), Houston Bush (IAH, 57.0), Houston Hobby (HOU, 52.5) and San Antonio (SAT, 39.8).** Seven Texas airports cleared the 1M-enplanement floor; percentiles are national across a 105-airport universe at that floor.

**Evidence (FAA enplanements CY2025 preliminary; FAA TAF 2025, actuals to 2024; BTS Aug 2025–Jul 2026; OurAirports; FAA slot admin 2026-08-11)**

| Rank | Airport | Score (no scale) | Growth pct (TAF 10-yr CAGR) | Momentum pct (FAA YoY) | Cap. pressure pct | Scale pct | Enplanements CY2025 | 2035 TAF enpl. | Fcst ops vs peak | Ops / runway | Delayed ≥15 min / NAS share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AUS | 66.1 (64.3) | 97.6 (3.02%) | 27.9 (−0.25%) | 55.3 | 73.1 | 10.65M | 14.12M | 1.24× | 108,413 (2) | 22.6% / 24.8% |
| 2 | DFW | 57.4 (47.4) | 33.0 (1.88%) | 52.3 (−2.49%) | 58.4 | 97.6 | 41.30M | 50.15M | 1.03× | 103,678 (7) | 21.7% / 25.4% |
| 3 | IAH | 57.0 (49.6) | 65.0 (2.28%) | 41.0 (−0.36%) | 39.8 | 86.5 | 23.27M | 29.21M | 0.84× | 86,672 (5) | 17.9% / 37.7% |
| 4 | HOU | 52.5 (49.3) | 67.0 (2.31%) | 34.4 (−4.59%) | 41.6 | 65.4 | 6.79M | 8.62M | 1.12× | 51,311 (3) | 22.3% / 22.6% |
| 5 | SAT | 39.8 (35.1) | 36.9 (1.94%) | 32.4 (−4.19%) | 35.1 | 58.7 | 5.24M | 6.45M | 1.05× | 40,782 (3) | 22.6% / 16.4% |

No Texas airport in the top 5 is slot-controlled.

**Why**
- **AUS** is a forecast-growth story: 3.02% CAGR (98th percentile nationally), 130% of 2019, and FAA projects 2035 operations 24% above its demonstrated peak on just two qualifying runways (108k ops each) — a strong structural-capacity signal. Weakness: flat recent traffic (−0.25% YoY).
- **DFW** ranks second largely on scale (97.6 pct) — without it the score falls to 47.4. Its pressure is observed rather than forecast: cancellations 2.9%, weather share 6.0%, forecast ops just above peak (1.03×). Forecast growth is below median.
- **IAH** has solid forecast growth (2.28%) and the highest NAS-attributed delay share in the set (37.7%), but low delay rates (17.9%) and airfield headroom (0.84× peak) keep pressure low.
- **HOU** mirrors IAH on growth with forecast ops 1.12× peak, but −4.6% YoY momentum drags it.
- **SAT** is below median on every component except scale.

**Assumptions & uncertainty**
- Scores are relative national percentiles for screening — not returns or probabilities; project cost, terminal/gate capacity and financing are excluded. Rank 2–3 (DFW vs IAH) is effectively a tie (57.4 vs 57.0).
- CY2025 enplanements preliminary; TAF forecasts unconstrained; "demonstrated peak" is a historical ops count, not engineered capacity. BTS data is domestic, arrivals-based, includes weather. All five recorded negative YoY for CY2025. Confidence: high for all five.

**Suggested follow-ups**
- "What is AUS's unmet demand indicator — why does forecast exceed its peak by 24%?"
- "Show the two Texas airports that fell outside the top 5, or re-rank without scale."

## INV-14: Compare Boston and Providence congestion.
*Purpose:* City names instead of codes

*mode=llm tools=['compare_congestion'] latency=32.0s confidence=['high'] warnings=['Numbers not traceable to a data source: 03m, 06m, 100k, 12, 2.1M, 73.6, 77']*

**Boston Logan (BOS) is far more congested than Providence T.F. Green (PVD) — Congestion Index 91.3 vs 56.6 — and the gap is structural: BOS is in the top decile nationally on every one of the five inputs, while PVD's elevated score rests on delay and cancellation rates alone, with delays mostly airline-caused.** BOS is also under a wind-driven ground delay program right now.

**Evidence (BTS on-time data Aug 2025–Jul 2026; taxi-out May–Jul 2026; TAF 2025 operations, 2024 actuals; OurAirports runways; national percentiles across 100k+ enplanement airports)**

| Metric (weight) | BOS | PVD | National median |
|---|---|---|---|
| Congestion Index | **91.3** | **56.6** | — |
| Arrivals delayed ≥15 min (35%) | 25.9% (90.0 pct) | 23.6% (74.9 pct) | 21.7% |
| Delays attributed to NAS (20%) | 42.2% (97.6 pct) | 18.4% (26.1 pct) | 21.1% |
| Arrivals cancelled (15%) | 2.78% (87.2 pct) | 2.63% (82.5 pct) | 1.81% |
| Avg taxi-out (15%) | 21.4 min (93.9 pct) | 14.8 min (28.4 pct) | 15.8 min |
| Ops per qualifying runway (15%) | 80,268 (5 runways; 87.4 pct) | 22,615 (2 runways; 57.1 pct) | 17,332 |
| Departures delayed ≥15 min | 23.3% | 22.1% | — |
| Avg delay per delayed arrival | 75.0 min | 67.8 min | — |
| Delay causes: carrier / late aircraft / weather | 23.0% / 32.4% / 2.2% | 36.0% / 41.1% / 4.2% | — |
| Arrivals analysed (12 mo) | 144,377 | 17,392 | — |
| Slot status | Not slot-controlled | Not slot-controlled | — |
| Enplanements CY2025 (prelim.) | 21.0M | 2.1M | — |
| Live FAA status (27 Sep 2026 16:15 GMT) | Ground delay, wind (avg 4h 03m, max 7h 06m) | No events | — |

**Why it matters**
- **BOS's delays are capacity-type delays:** 42% are attributed to airport/airspace capacity — top percentile nationally, double the median — and taxi-out runs 21 minutes on runways loaded at 4.6× the median rate. That is the signature of a binding airfield/airspace constraint, consistent with its 73.6 capacity-pressure percentile in the New England ranking.
- **PVD's congestion is imported, not structural:** 77% of its delays are carrier or late-aircraft (inbound delays propagating from elsewhere), NAS share is below median, taxi-out is quick, and its two runways carry modest loads. Its above-median delay and cancellation rates therefore say little about PVD's own capacity.
- Both airports have high cancellation rates (~2.7%, vs 1.8% median), but at PVD the weather share (4.2%) is roughly double BOS's.

**Assumptions & uncertainty**
- The Congestion Index is a relative national percentile composite, not a capacity measure or return; runway counts (open, paved, ≥5,000 ft) proxy the airfield, not terminals or gates.
- BTS data covers domestic reporting carriers, arrivals-based, includes weather; BOS's international operation is not captured. Taxi-out is a 3-month snapshot; TAF operations are 2024 actuals. PVD's 12-month sample (17,392 arrivals) is small relative to BOS. Live status is a snapshot and never scored. Confidence: high for both.

**Suggested follow-ups**
- "Run PVD's unmet demand indicator — does any of its pressure reflect its own capacity?"
- "Add BDL and MHT to this congestion comparison."

## INV-15: Any delays at SFO right now?
*Purpose:* Live status

*mode=llm tools=['live_airport_status'] latency=25.2s confidence=['high'] warnings=['Numbers not traceable to a data source: 12, 31.6, 54.7, 76.5, 85.5']*

**Yes — SFO is currently under an FAA ground delay program for low ceilings, with arrivals averaging 49 minutes of delay and a maximum of 1 hour 42 minutes.** No ground stop or closure is in effect.

**Evidence (FAA National Airspace System status, live)**

| Item | Value |
|---|---|
| Event type | Ground delay program |
| Cause | Low ceilings |
| Average delay | 49 minutes |
| Maximum delay | 1 hour 42 minutes |
| Other events (ground stop, closure, departure/arrival delay advisories) | None listed |
| FAA update time | Sun 27 Sep 2026, 16:15 GMT |
| Retrieved | 27 Sep 2026, 16:16 GMT |

**Why it matters**
- This is the same low-ceiling program flagged earlier in this session (also 49 min average), so it has been in place for at least an hour of the current session.
- A weather-triggered ground delay program is consistent with SFO's structural profile from the trailing-12-month BTS data: 31.6% of arrivals delayed ≥15 min and 54.7% of delays attributed to the NAS — the airport's closely spaced parallel approaches lose arrival capacity when ceilings drop, which is why marine-layer conditions translate directly into metered arrivals.
- A single snapshot, however, is anecdotal. The screening case for SFO (Congestion Index 85.5, Unmet Demand Indicator 76.5) rests on the 12-month record, not on today's event.

**Assumptions & uncertainty**
- Live status is a point-in-time operational snapshot; it says nothing about structural capacity and is never used in any score. Conditions can change within minutes.
- "Average" and "maximum" are the FAA's program-level figures, not per-flight measurements, and the feed does not indicate when the program began or its scheduled end time. Confidence: high (direct FAA feed, no gaps).

**Suggested follow-ups**
- "Check live status for LAX, SNA and OAK too — is this a Bay Area or California-wide pattern right now?"
- "How does SFO's weather-attributed delay share compare with its NAS share over the full 12 months?"

## INV-16: How is the expansion score calculated?
*Purpose:* Methodology transparency

*mode=llm tools=['explain_methodology'] latency=30.7s confidence=['high'] warnings=['Numbers not traceable to a data source: 100, 60, 66']*

**The Expansion Opportunity Score is a weighted sum of four national-percentile components — forecast growth (30%), capacity pressure (30%), demand momentum (20%) and scale (20%) — computed across all US airports with at least 100,000 enplanements (the default floor), producing a 0–100 relative ranking.** It measures where an airport sits versus its peers on each signal, not a return or probability.

**Methodology (verbatim components and weights)**

| Component | Weight | What feeds it | Source |
|---|---|---|---|
| Forecast growth | 0.30 | TAF 10-year enplanement CAGR | FAA TAF 2025 (actuals to 2024, forecast 2025–2055) |
| Capacity pressure | 0.30 | **Half structural:** air-carrier operations per qualifying runway; FAA slot/schedule-facilitation status; forecast operations vs the airport's demonstrated peak. **Half observed:** share of arrivals delayed 15+ min; share of delays attributed to the NAS; cancellation rate, trailing 12 months | TAF, OurAirports runways, FAA slot administration (page updated 2026-08-11), BTS on-time data Aug 2025–Jul 2026 |
| Demand momentum | 0.20 | FAA year-over-year enplanement growth blended 50/50 with the latest TAF actual growth | FAA CY2025 vs CY2024 (preliminary), TAF |
| Scale | 0.20 | log10 of enplanements | FAA CY2025 preliminary |

**Processing rules**
- Raw signals are winsorized at the 5th/95th percentile before being converted to national percentile ranks, so a single outlier airport cannot dominate a component.
- Missing components are dropped and the remaining weights renormalized; the airport's confidence rating is lowered accordingly (never imputed).
- The "no-scale" sensitivity score shown in rankings re-runs the same method with the scale weight removed — useful for spotting airports (e.g., DFW in the Texas ranking) whose rank leans on size rather than growth or pressure.
- Weights can be overridden and the volume floor changed on request; the percentile universe is recomputed for the chosen floor.

**How to read it**
- A score of 66 means the airport's weighted position is in roughly the upper third of peers on this blend — it says nothing about project cost, terminal or gate design capacity, financing or ROI.
- Forecast growth and capacity pressure together carry 60% of the weight, so the score favours airports where FAA projects strong demand *and* the airfield already shows structural or observed strain.
- Live FAA status is never scored.

**Assumptions & uncertainty**
- Data vintages: FAA enplanements CY2025 preliminary; TAF 2025 final (unconstrained forecasts); BTS delay causes Aug 2025–Jul 2026 (domestic reporting carriers, arrivals-based, includes weather); flight-level BTS snapshot May–Jul 2026; OurAirports runways refreshed daily; slot status as of 2026-08-11. "Demonstrated peak" is a historical operations count, not engineered capacity; qualifying runways (open, paved, ≥5,000 ft) proxy the airfield only. No caveats were flagged on the methodology itself; confidence: high.

**Suggested follow-ups**
- "Explain how the Congestion Index or the Unmet Demand Indicator is calculated."
- "Re-rank the Texas candidates with capacity pressure weighted at 50% and scale at 0."
