# Airport Investment Intelligence Agent

A conversational analyst for a firm that invests in US airport modernization. It ranks and compares airports on
deterministic, fully sourced KPIs (FAA passenger boardings and forecasts, BTS delay statistics, runway and slot data)
and uses an AI model only to interpret questions and explain results. Every answer shows its sources, data vintages,
assumptions, and what the data cannot tell you.

Example questions (from the brief):

- Which airports in New England are strong candidates for terminal expansion?
- Compare LA and Santa Ana airport congestion levels.
- What is the percentage of long haul flights out of Anchorage airport?
- What is the unmet flight demand in SFO airport and why?

Follow-ups work: "the second one", "add PVD to that comparison", "what if I ignore scale?", "how confident are you?".

## Run it locally

**Prerequisites:** Python 3.9 or newer (developed and tested on 3.9.6; the pinned dependencies publish wheels for
3.9 through 3.13) and `git`. Nothing else: no accounts, no API keys, no database. Internet access is optional (see
"Offline mode").

macOS / Linux:

```bash
git clone https://github.com/RonGonen/deloitte-fde-task.git
cd deloitte-fde-task
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows (PowerShell):

```powershell
git clone https://github.com/RonGonen/deloitte-fde-task.git
cd deloitte-fde-task
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open **http://127.0.0.1:8000** in a browser (Chrome for the voice buttons).

What happens on first start (about 10 seconds):

- It downloads the current FAA passenger-boarding workbook (150 KB) and the latest 12 months of BTS delay statistics
  (about 1 MB) into a local `.cache/` folder. If either site is unreachable, it automatically uses the committed copy of
  the same data and says so in the data-vintages card and in `/api/health`.
- Everything else (FAA forecasts, flight routes, airports and runways) is loaded from small tables shipped in
  `data/snapshots/`, so later starts take about two seconds.

Verify the install at any time:

```bash
.venv/bin/pytest -q                                  # 104 offline tests, ~6 seconds
curl -s http://127.0.0.1:8000/api/health             # "status": "ready", every source "ok": true
```

### What you get out of the box

By default the app answers with its **rules-based interpreter**: the same deterministic calculations, narrated by
templates, in under a second, with no AI model involved. All example questions and follow-ups work in this mode. The
page shows a chat on the right and an analyst panel on the left (top expansion candidates by region and airport size,
live FAA airport status, data vintages, score weights). Each answer has fold-out panels for sources, caveats and the
raw numbers, plus a badge saying which path answered.

### Turning on the AI narrator (optional)

Either option makes Claude interpret questions, choose the analyses and write the explanation. Calculations do not change.

| Option | How | Notes |
|---|---|---|
| Anthropic API | `export ANTHROPIC_API_KEY=...` in the shell you start the server from (PowerShell: `$env:ANTHROPIC_API_KEY="..."`) | Picked automatically when the variable is present. Never put the key in a file |
| Claude Code CLI | Install Claude Code, log in, then set `LLM_PROVIDER=claude_cli` in a `.env` file (see below) | Uses the account you are logged into; opt-in only, never selected implicitly |

`LLM_MODEL` chooses the model (default `claude-fable-5-1`; `claude-sonnet-5` is faster and cheaper). An AI answer takes
20 to 50 seconds because the model makes one to four analysis calls before writing. If the model is unavailable the
rules-based path answers instead, and the badge on the answer says so.

### Configuration

Non-secret settings go in a `.env` file in the project folder (copy `.env.example`; the file is git-ignored). Secrets
(`ANTHROPIC_API_KEY`, `APP_TOKEN`) are read only from the shell environment.

| Setting | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `auto` (Anthropic API if a key is present, else rules), `rules`, `anthropic`, `claude_cli` |
| `LLM_MODEL` | `claude-fable-5-1` | Model used by the AI providers |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Where the server listens; change `PORT` if 8000 is taken |
| `OFFLINE` | `0` | `1` = never download; run entirely from the shipped snapshots |
| `CACHE_DIR` | `.cache` | Where downloaded files are cached |
| `APP_TOKEN` (env only) | unset | Required for any client that is not on the same machine; see Security |

### Offline mode

`OFFLINE=1 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000` runs with no network at all, using the shipped
snapshots (FAA CY2025 preliminary boardings, TAF 2025 forecast, BTS delay causes Aug 2025 to Jul 2026, routes May to
Jul 2026, airports and runways). Only the live FAA status card is empty.

### Security

- The server is meant to run on your own machine. Requests from any other machine are refused (403) unless `APP_TOKEN`
  is set; with it set, every `/api/*` request must send `Authorization: Bearer <token>` and the web UI asks for the
  token once.
- Generate and provide the token in the shell for the session (`export APP_TOKEN=$(openssl rand -hex 24)`), never in a
  file.
- All inputs are validated; responses carry a same-origin Content-Security-Policy and standard security headers; there
  is no CORS. Internal error details stay in the server log.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `Address already in use` | Another program uses port 8000: start with `--port 8010` (and open that URL) |
| `pip` fails on an old Python | Check `python3 --version`; 3.9 or newer is required |
| Behind a corporate proxy | Set `HTTPS_PROXY=http://proxy:port` in the shell; downloads honour it. Or use `OFFLINE=1` |
| A source shows `"ok": false` in `/api/health` | The site is down and no snapshot exists for it (only possible for the live FAA status feed). Everything else falls back to snapshots automatically |
| Voice buttons disabled | Use Chrome and allow microphone access |
| `403 remote access requires APP_TOKEN` | You are calling from another machine; set `APP_TOKEN` as described in Security |
| AI answers are slow | Expected (20 to 50 s on Fable 5.1). Use `LLM_MODEL=claude-sonnet-5` or the default rules mode |

## API

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s -X POST http://127.0.0.1:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"message": "Compare LAX and SNA congestion", "provider": "rules"}'
```

`POST /api/chat` takes `{message, session_id?, provider?}` and returns `{text, mode, tool_results, sources, caveats,
warnings, session_id}`. `GET /api/rank?region=&states=&min_enplanements=&limit=` returns the same deterministic
ranking the chat uses (it powers the side panel, so panel and chat never disagree for the same scope);
`GET /api/live` returns nationwide FAA status; `GET /api/regions` lists region names; `GET /api/methodology`
returns the scoring formulas; `GET /api/docs` is the OpenAPI UI.

## Tests, data refresh, acceptance run

```bash
.venv/bin/pytest -q                       # 104 offline tests on real-data fixture slices
.venv/bin/pytest -q -m network            # opt-in checks against the live public sources
.venv/bin/python scripts/refresh_data.py --ontime 2026-05 2026-06 2026-07   # rebuild data/snapshots from the original downloads
.venv/bin/python scripts/client_run.py --provider rules                    # replay the 16-question investor session (server must be running)
```

## Documents

- [DESIGN.md](DESIGN.md): architecture, scoring methodology, key tradeoffs, where/how AI is used, assumptions and scope.
- [docs/OVERVIEW.md](docs/OVERVIEW.md): plain-language overview of the same material for non-technical readers.
- [docs/CLIENT_RUN_REPORT.md](docs/CLIENT_RUN_REPORT.md): findings from a client-side run as an investment manager
  (what worked, what is missing, what needs improvement), with transcripts alongside.

## Layout

```
app/main.py              FastAPI app, security middleware, static UI
app/engine.py            loads sources, builds the per-airport metrics table
app/sources/             FAA enplanements, TAF, BTS delay causes, BTS on-time, OurAirports, NAS status, disk cache
app/model/airports.py    canonical airport registry and text resolution (codes, cities, states, regions)
app/kpi/                 normalize, scoring (expansion), congestion, long_haul, demand
app/agent/               tools, orchestrator, session, prompts, rules router, Claude CLI and Anthropic adapters
app/web/                 chat UI and analyst panel (HTML/CSS/JS, voice)
data/snapshots/          committed compact data tables + manifest.json (vintages)
scripts/                 refresh_data.py, client_run.py
tests/                   pytest suite with fixtures carved from the real data
```
