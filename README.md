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
cp .env.example .env            # optional, non-secret settings; see "LLM providers"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The first start fetches the FAA workbook (150 KB) and the BTS delay-cause file (~1 MB) into
`.cache/`; everything else (TAF, routes, airports and runways) comes from the committed snapshots, so startup is about
two seconds and works offline with `OFFLINE=1`.

### Security

- The server is meant to run on loopback. Requests from any non-loopback client are refused (403) unless `APP_TOKEN`
  is set; with it set, every `/api/*` request must send `Authorization: Bearer <token>` (the UI asks for it once).
- Provide `APP_TOKEN` and `ANTHROPIC_API_KEY` through the shell environment for the session
  (`export APP_TOKEN=$(openssl rand -hex 24)`), not in `.env` or any other file.
- All inputs are validated; responses carry a same-origin Content-Security-Policy and standard security headers; there
  is no CORS. Internal error details stay in the server log.

The page has two parts: the chat, and an analyst side panel with the top expansion candidates (switchable by region
and volume floor; click a row to ask about that airport), live FAA airport status, data vintages and the score weights.
Voice: the microphone button uses the browser's Web Speech API (Chrome) and the speaker button reads answers aloud.

## LLM providers

| `LLM_PROVIDER` | What it uses | Needs |
|---|---|---|
| `auto` (default) | `anthropic` if `ANTHROPIC_API_KEY` is set, else `rules`. A logged-in Claude CLI is never used implicitly | - |
| `claude_cli` | Headless Claude Code CLI (`claude -p`) with the account you are logged into; opt-in only | Claude Code installed and logged in; set `LLM_PROVIDER=claude_cli` |
| `anthropic` | Anthropic API via the official SDK, native tool use | `ANTHROPIC_API_KEY` exported in the shell environment (never stored in a file) |
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
warnings, session_id}`. `GET /api/rank?region=&states=&min_enplanements=&limit=` returns the same deterministic
ranking the chat uses (it powers the side panel, so panel and chat never disagree for the same scope);
`GET /api/live` returns nationwide FAA NAS status; `GET /api/regions` lists region names; `GET /api/methodology`
returns the scoring formulas; `GET /api/docs` is the OpenAPI UI.

## Tests and data refresh

```bash
.venv/bin/pytest -q                       # 101 offline tests on real-data fixture slices
.venv/bin/pytest -q -m network            # opt-in live-source checks
.venv/bin/python scripts/refresh_data.py --ontime 2026-05 2026-06 2026-07   # rebuild data/snapshots (TAF, OurAirports, delay causes, routes)
.venv/bin/python scripts/client_run.py    # replay the investor acceptance session against a running server
```

## Documents

- [DESIGN.md](DESIGN.md): architecture, scoring methodology, key tradeoffs, where/how AI is used, assumptions and scope.
- [docs/OVERVIEW.md](docs/OVERVIEW.md): plain-language overview of the same material for non-technical readers.
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
