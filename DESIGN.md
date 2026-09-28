# Airport Investment Intelligence Agent: Design Document

*Deloitte Forward Deployed Engineer take-home. Companion to the [README](README.md) (how to run it) and the
[client-side run report](docs/CLIENT_RUN_REPORT.md) (what an investment manager found when using it).*

## 1. What this is for

The firm invests in modernizing US airports. Before committing capital to a terminal expansion, an analyst wants
to know where passenger demand is growing *and* where the airport is already struggling to handle it, because that
is where added capacity is most likely to be used and paid for.

This agent lets an analyst ask those questions in plain English and get an answer that is:

- **calculated, not improvised** - every ranking, comparison and percentage is produced by fixed formulas over public
  government data, and the AI is only allowed to explain those results;
- **traceable** - every answer lists the sources, the time period of each figure, and what the data cannot show;
- **conversational** - follow-ups such as "why is the first one above the second?", "add SFO to that comparison" or
  "what if I ignore scale?" work, because the agent remembers what it just showed.

The four questions in the brief, and what the agent answers today:

| Question from the brief | The agent's answer (September 2026 data) |
|---|---|
| Which airports in New England are strong candidates for terminal expansion? | A ranked list of the 10 New England airports above 100,000 yearly boardings. Boston Logan leads with a score of 69.9 out of 100; Portland (ME), Burlington and New Haven follow in the mid-50s. Each row shows why: growth outlook, recent momentum, capacity pressure and size. |
| Compare LA and Santa Ana airport congestion levels. | LAX 55.8 vs Santa Ana 47.5 on the Congestion Index. Both have *fewer* delays than the national median, but both run their runways at roughly seven times the typical load, and LAX has formal FAA schedule facilitation. The agent notes it read "LA" as LAX and offers the wider LA basin. |
| What is the percentage of long haul flights out of Anchorage airport? | 7.7% of scheduled domestic departures are 3,000 miles or longer (22.8% at 2,500 miles, 43% at 1,500 miles). The agent warns that international and cargo flights are not in the data, which understates a cargo hub like Anchorage. |
| What is the unmet flight demand in SFO airport and why? | An Unmet Demand Indicator of 76.5 out of 100, with six reasons: a third of arrivals delayed, more than half of delays attributed to airport and airspace capacity, forecast traffic above anything the airfield has ever handled, FAA schedule facilitation, traffic still below 2019, and limited use of bigger aircraft. It states plainly that seat and load-factor data are unavailable, so this is a pressure indicator, not a count of turned-away passengers. |

## 2. What the analyst sees

The application is a single web page served on the analyst's own machine.

- **The chat** (right). Ask a question, or click one of the suggested questions. Each answer opens with the direct
  answer, then the evidence with periods and sources, then the reasoning, then assumptions and uncertainty, then one or
  two suggested follow-ups. Under every answer are two fold-out panels: *Sources & caveats* (which datasets, which
  periods, what they leave out, the confidence level) and *Data returned by the analysis tools* (the raw numbers the
  answer was written from). A small badge shows whether the AI or the rules-based fallback wrote the answer, and how
  long it took.
- **The analyst panel** (left). A top-10 table of expansion candidates, switchable by region and by minimum airport
  size; clicking a row asks the chat about that airport. Below it: live FAA airport status (ground stops and delay
  programs right now), the vintage of each dataset in use, and the score weights. The table is produced by the very
  same calculation the chat uses, so a panel row and a chat answer for the same scope always carry the same number.
- **Voice**. A microphone button dictates a question and a speaker button reads answers aloud (in Chrome).

## 3. How an answer is produced

Think of it as an analyst with a very disciplined research assistant:

1. **Understand the question.** The AI (Claude) reads the question together with what was discussed earlier in the
   session and decides which of eight fixed analyses are needed and with which settings: which states or airports,
   which volume floor, which weights. If a word is ambiguous ("LA", "Washington") it picks the usual reading and says so.
2. **Run the analyses.** Each analysis is ordinary code that reads the government data and computes a result. The AI
   cannot change a formula or a weight; it can only ask for an analysis with different parameters.
3. **Package the evidence.** Every analysis returns the same bundle: the numbers, the sources with their periods, the
   caveats, a confidence level, and a description of the method.
4. **Write the answer.** The AI turns those bundles into prose, under a strict rule: every number in the text must
   appear in one of the bundles. General aviation knowledge that is not in the data must be labelled as such.
5. **Check the answer.** Before the answer is shown, a checker scans the text for numbers and confirms each one can be
   traced to an analysis result from this or the last few turns. Anything untraceable is flagged in the UI.

If the AI is unavailable, or misbehaves, a rules-based interpreter takes over. It recognizes the common question
patterns, runs the same analyses and writes a plainer answer; the badge on the answer says which path produced it.

The eight analyses: find airports from names or codes; rank expansion candidates; profile one airport; compare
congestion; long-haul share; unmet-demand pressure; live FAA status; explain the methodology.

## 4. The data

All sources are public and free. None requires an account.

| Source | What it tells us | Freshness in this build |
|---|---|---|
| **FAA passenger boardings** (enplanements) | How many passengers boarded at each of ~1,700 US airports, this year vs last; whether the airport is a primary/commercial-service airport; hub size | Calendar 2025 (preliminary) vs 2024. Pulled live when the app starts, cached for a day, with a saved copy as fallback |
| **FAA Terminal Area Forecast** | The FAA's own history (back to 1990) and forecast (to 2055) of boardings and aircraft operations per airport, including international share | 2025 edition. Converted once into a compact table shipped with the app |
| **BTS airline delay causes** | For each airport and month: arrivals, share delayed 15+ minutes, cancellations, and *why* (airline, weather, air-traffic system, security, late inbound aircraft) | Trailing 12 months, August 2025 to July 2026. Pulled live, cached for a day, saved copy as fallback |
| **BTS flight-level on-time records** | Every domestic flight: origin, destination, distance, taxi-out time, departure delay | May to July 2026 (three monthly files of ~33 MB each), summarized into a small table shipped with the app |
| **OurAirports** (open data) | Airport codes, coordinates, and runways with length, surface and open/closed status | Compact extract of the 1,633 airports and 2,947 runways that match FAA airports, shipped with the app |
| **FAA airport status feed** | Live ground stops, ground delay programs and closures | Real time, refreshed every five minutes; shown for context, never scored |
| **FAA slot administration** | Which airports the FAA slot-controls (JFK, LGA, DCA) or schedule-facilitates (ORD, LAX, EWR, SFO) because runway capacity is constrained | FAA page as of August 2026, verified September 2026 |

A single script refreshes all of the shipped tables from the original downloads, so the data can be brought up to
date at any time without changing code.

**What we could not get.** The BTS "T-100" dataset (seats offered, passengers carried per route, international and
cargo flights) would be the best evidence for unmet demand and long-haul share. Its download form could not be
automated reliably within the time available. Every answer that would have used it says so.

## 5. Scoring methodology

### The idea

Rather than trust any single statistic, each airport is measured on several signals and each signal is expressed as a
**national percentile**: where the airport sits among all 233 US primary and commercial-service airports with at least
100,000 boardings a year. A percentile of 90 on "delays" means only 10% of comparable airports have more delays. This
makes very different quantities (a growth rate, a delay share, a passenger count) comparable, and it makes a score of
80 mean the same thing everywhere in the country.

Two details keep this honest. Extreme values are trimmed to the 5th and 95th percentile before ranking so one outlier
cannot distort the scale. And regional questions ("New England") are answered by scoring nationally first and filtering
afterwards, so a region with only ten airports does not collapse into ranks of 0, 50 and 100. The panel and every
answer state the scope they used.

### Expansion Opportunity Score (0-100)

The main ranking. An expansion is most attractive where demand is growing *and* capacity is already binding, at an
airport large enough to monetize the investment.

| Component | Weight | What goes in |
|---|---|---|
| **Forecast growth** | 30% | The FAA's forecast growth rate in boardings over the next ten years (2025 to 2035) |
| **Demand momentum** | 20% | Recent actual growth: last year's change in FAA boardings, blended with the latest year of FAA-recorded growth |
| **Capacity pressure** | 30% | Half *structural*: aircraft operations per usable runway, FAA slot or schedule-facilitation status, and forecast operations compared with the most the airfield has ever handled. Half *observed*: share of arrivals delayed 15+ minutes, share of delays attributed to airport and airspace capacity, cancellation rate over the last 12 months |
| **Scale** | 20% | Size of the passenger base (logarithm of boardings) |

Why these weights: demand (forecast plus momentum) carries half the score, binding capacity almost a third, and size
the rest. Size is deliberately visible rather than hidden in a cutoff: every ranking also shows the score *without*
the size component, so an analyst can see which airports rank on growth and pressure alone. Weights and the volume
floor can be changed in conversation ("what if I ignore scale?", "at least 1 million passengers").

Each ranked airport also carries its four component percentiles, the two or three drivers that moved it most, the
raw figures behind them, and a **confidence level**: *high* when every input was available, *medium* when one was
missing, *low* when two or more were missing. The usual reason for *medium* is a smaller airport whose airlines do not
report enough flights for delay statistics (fewer than 2,000 arrivals a year): its score is computed from the remaining
inputs with the weights rebalanced, the confidence drops, and the answer says why. Nothing is ever estimated to fill a
gap. Among large hubs almost everything is *high*, which is expected: the level describes data completeness, not how
strong the investment case is.

### Congestion Index (0-100)

Used for "compare X and Y". Five national percentiles, weighted: arrivals delayed 15+ minutes (35%), share of delays
attributed to the air-traffic system (20%), cancellations (15%), average taxi-out time (15%) and operations per usable
runway (15%). The raw figures and the national medians are always shown beside the index, weather's own share of
delays is printed next to the system share, and live FAA status is attached for context but never scored.

### Long-haul share

The share of scheduled domestic departures on routes of at least 3,000 statute miles, with 1,500- and 2,500-mile
shares shown because the answer is sensitive to the cutoff, plus the busiest and longest routes. The answer always
states that international and cargo flights are not in the underlying data.

### Unmet Demand Indicator (0-100)

The average of six national percentiles that together describe demand pressing against capacity: forecast operations
versus the airfield's historical peak; share of arrivals delayed; share of delays attributed to capacity; slot status;
how far traffic still lags 2019; and how much airlines have grown by using bigger aircraft rather than more flights
(the classic response at an airport that cannot add departures). Each driver is turned into a plain sentence with the
airport's value next to the national median, which is how the agent answers the "and why?" part of the question.

## 6. Where and how AI is used

**Used for:** understanding the question, choosing which analyses to run and with what settings, keeping track of the
conversation, and writing the explanation in a consistent, decision-oriented shape.

**Not used for:** any calculation, weighting, ranking, forecasting or data lookup. The AI never sees a spreadsheet; it
sees the result bundles and describes them.

**Safeguards:**

- The instructions given to the AI forbid numbers that do not come from an analysis result and require it to label
  general knowledge as such.
- The independent number-check after each answer flags anything untraceable, and the flag is shown to the analyst.
- The rules-based interpreter answers when the AI is unavailable, and every answer is badged with the path that
  produced it.
- Sources, caveats and confidence are displayed from the analysis results themselves, not from the AI's prose.

**The model.** Claude Fable 5.1 by default, chosen for the quality of its reasoning about which analyses to combine
(for example, answering "why is the first ranked above the second?" by pulling both airports' scores, both demand
profiles and the methodology). It can run in two ways: through the Claude Code command-line login already on the
machine, or through the Anthropic API with a key supplied in the shell environment. Without either, the app still works
on the rules-based path.

## 7. Key tradeoffs

- **Shipping data tables vs fetching live.** Small, fast sources are fetched live (with a saved fallback). Large or
  slow ones (the 15 MB FAA forecast, three 33 MB BTS flight files served at dial-up speed, the 17 MB airport reference)
  are summarized into tables shipped with the app. Result: the app starts in about two seconds, works offline, and every
  reviewer sees the same numbers; the cost is that route data is a few months old until the refresh script is run.
- **National percentiles vs regional peer groups.** Regional comparisons feel more intuitive but break down for small
  regions. National normalization is stable, and every answer names the scope it used.
- **Weather inside the delay data.** BTS attributes weather-driven flow restrictions to the "air-traffic system"
  category, so an airport with bad weather can look capacity-constrained. Splitting structural signals (runway load,
  slot status, forecast vs peak) from observed delays, and printing the weather share, keeps the two apart.
- **A reasoning-grade model for a chat tool.** Fable 5.1 gives the best explanations but takes 20 to 50 seconds and
  costs roughly $0.30 to $0.60 per answer. A faster model can be selected with one setting; the rules-based path
  answers instantly.
- **Missing seat data.** Without the T-100 dataset, "unmet demand" is measured as pressure, not as passengers not
  served. The alternative, estimating load factors, would have meant inventing numbers, which the whole design avoids.
- **A single-analyst tool, secured accordingly.** The server runs on the analyst's machine and only accepts local
  connections unless an access token is configured, in which case every request must present it. Secrets are provided
  through the shell environment for the session, never stored in files. Pages carry a strict content-security policy,
  inputs are validated, and internal error details stay in the server log. A shared, multi-user deployment would add
  individual logins, saved sessions, audit logging and rate limits.

## 8. Assumptions, uncertainty and scope

- Passenger figures are FAA *boardings* (departing passengers), not total passengers; calendar 2025 figures are
  preliminary and may be revised.
- FAA forecasts assume capacity will be provided; they describe demand, not what the airport can handle.
- Delay statistics cover domestic flights of the larger US airlines, are based on arrivals, cover the trailing
  12 months, and include weather effects.
- "Highest operations ever handled" is a historical fact, not an engineered capacity; runway counts describe the
  airfield, not terminals or gates.
- Scores are relative screening percentiles meant to shortlist airports for diligence. They are not probabilities of
  success and not investment returns.
- Out of scope: project costs and returns, financing, terminal and gate capacity, seats and load factors, cargo,
  fares, catchment demographics, airline network plans, and airports outside the United States. When asked about these,
  the agent says so and offers the evidence it does have.

## 9. Quality and evidence that it works

- **Automated tests.** 101 tests run offline in about five seconds on slices of the real data: the data readers, the
  matching of names and codes to airports (including traps like "AND" or "SEA" being read as codes), every score
  (determinism, weights, sensitivity, missing data), the question interpreter and follow-ups, the number-check, the AI
  loop with a stand-in model, and the web API including input validation and access control.
- **Client-side run.** A 16-question session was run as an investment manager, once with the AI and once on the
  rules-based path. All 16 questions were answered in both modes with identical figures; the findings, including what
  an investor would still need (seat data, terminal capacity, project economics) and what was improved as a result, are
  in the [client-side run report](docs/CLIENT_RUN_REPORT.md).
- **Independent code review.** A review of the final version led to authentication, security headers, input
  validation, a fix for a silent default-floor bug, and a lighter startup.

## 10. What we would build next

1. Add the BTS T-100 route data (seats, passengers, international and cargo) to measure load factors and true long-haul
   share, turning the Unmet Demand Indicator from pressure into a passenger gap.
2. Add terminal and gate inventories and FAA runway capacity benchmarks, so capacity is measured directly rather than
   through proxies.
3. Add airport financials and capital plans, the other half of an investment case.
4. Stream answers and show progress while the AI works; charts of history and forecast; export of shortlists.

## Glossary

- **Enplanements / boardings**: passengers boarding a flight at an airport; the FAA's standard traffic measure.
- **TAF (Terminal Area Forecast)**: the FAA's official per-airport forecast of passengers and operations.
- **Operations**: aircraft takeoffs and landings.
- **NAS (National Airspace System) delays**: delays the airlines attribute to the air-traffic system: airport and
  airspace volume and weather-related flow restrictions, as opposed to airline, security or late-aircraft causes.
- **Slot control / schedule facilitation (Level 3 / Level 2)**: FAA regimes that cap or review airline schedules at
  airports whose runways cannot absorb unconstrained demand.
- **Percentile**: the share of comparable airports with a lower value; 90 means higher than 90% of them.
- **Up-gauging**: airlines carrying more passengers per flight by using larger aircraft, typical where they cannot
  add flights.
