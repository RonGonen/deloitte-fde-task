# Airport Investment Intelligence Agent

A conversational analyst for a firm that invests in US airport modernization. It ranks and compares airports on
deterministic, fully sourced KPIs (FAA enplanements and forecasts, BTS delay statistics, runway and slot data) and uses
Claude only to interpret questions and explain results. Every answer shows its sources, data vintages, assumptions and
what the data cannot tell you.

Example questions (from the brief):

- Which airports in New England are strong candidates for terminal expansion?
- Compare LA and Santa Ana airport congestion levels.
- What is the percentage of long haul flights out of Anchorage airport?
- What is the unmet flight demand in SFO airport and why?

Follow-ups work: "the second one", "add PVD to that comparison", "what if I ignore scale?", "how confident are you?".

## Quick start

Requires Python 3.9 or newer (tested on 3.9.6) and internet access for the live FAA/BTS/OurAirports pulls
(everything also runs offline from the committed snapshots with `OFFLINE=1`).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # optional; see "LLM providers"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The first start fetches the FAA workbook (150 KB), the BTS delay-cause file (~1 MB) and
the OurAirports tables (~17 MB) into `.cache/`; later starts take about two seconds.

Voice: the microphone button uses the browser's Web Speech API (Chrome) and the speaker button reads answers aloud.

## LLM providers

| `LLM_PROVIDER` | What it uses | Needs |
|---|---|---|
| `auto` (default) | `anthropic` if `ANTHROPIC_API_KEY` is set, else `claude_cli` if the `claude` CLI is installed, else `rules` | - |
| `claude_cli` | Headless Claude Code CLI (`claude -p`) with the account you are logged into | Claude Code installed and logged in |
| `anthropic` | Anthropic API via the official SDK, native tool use | `ANTHROPIC_API_KEY` in `.env` (git-ignored, never committed) |
| `rules` | Deterministic rules-based interpreter and narrator, no LLM | nothing |

`LLM_MODEL` defaults to `claude-fable-5-1`; `claude-sonnet-5` is faster and cheaper. The rules path is also the
automatic fallback when an LLM call fails, and every response carries a `mode` badge so you know which path answered.

## API

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s -X POST http://127.0.0.1:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"message": "Compare LAX and SNA congestion", "provider": "rules"}'
```

`POST /api/chat` takes `{message, session_id?, provider?}` and returns `{text, mode, tool_results, sources, caveats,
warnings, session_id}`. `GET /api/methodology` returns the scoring formulas; `GET /api/docs` is the OpenAPI UI.

## Tests and data refresh

```bash
.venv/bin/pytest -q                       # 88 offline tests on real-data fixture slices
.venv/bin/pytest -q -m network            # opt-in live-source checks
.venv/bin/python scripts/refresh_data.py --ontime 2026-05 2026-06 2026-07   # rebuild data/snapshots (slow BTS downloads)
.venv/bin/python scripts/client_run.py    # replay the investor acceptance session against a running server
```

## Documents

- [DESIGN.md](DESIGN.md): architecture, scoring methodology, where/how AI is used, tradeoffs, assumptions and scope.
- [docs/CLIENT_RUN_REPORT.md](docs/CLIENT_RUN_REPORT.md): findings from a client-side run as an investment manager
  (what worked, what is missing, what needs improvement).

## Layout

```
app/main.py              FastAPI app and static UI
app/engine.py            loads sources, builds the per-airport metrics table
app/sources/             FAA enplanements, TAF, BTS delay causes, BTS on-time, OurAirports, NAS status, disk cache
app/model/airports.py    canonical airport registry and text resolution (codes, cities, states, regions)
app/kpi/                 normalize, scoring (expansion), congestion, long_haul, demand
app/agent/               tools, orchestrator, session, prompts, rules router, Claude CLI and Anthropic adapters
app/web/                 chat UI (HTML/CSS/JS, voice)
data/snapshots/          committed compact snapshots + manifest.json (vintages)
scripts/                 refresh_data.py, client_run.py
tests/                   pytest suite with fixtures carved from the real data
```
