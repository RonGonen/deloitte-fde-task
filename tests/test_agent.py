"""Agent layer: rules router plans, tool envelopes, grounding check, orchestrator loop with a fake LLM, HTTP API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agent import rules_router
from app.agent import tools as T
from app.agent.llm_claude_cli import AssistantTurn, LLMError, build_prompt
from app.agent.orchestrator import Orchestrator, ground_check
from app.agent.session import Session, SessionStore

NEW_ENGLAND = ["CT", "ME", "MA", "NH", "RI", "VT"]


# ------------------------------------------------------------------ rules router
@pytest.mark.parametrize("text,tool,check", [
    ("Which airports in New England are strong candidates for terminal expansion?", "rank_airports", lambda a: a["states"] == NEW_ENGLAND),
    ("Compare LA and Santa Ana airport congestion levels.", "compare_congestion", lambda a: set(a["codes"]) == {"LAX", "SNA"}),
    ("What is the percentage of long haul flights out of Anchorage airport?", "long_haul_share", lambda a: a["code"] == "ANC"),
    ("What is the unmet flight demand in SFO airport and why?", "demand_pressure", lambda a: a["code"] == "SFO"),
    ("top 5 candidates in Texas with at least 1 million passengers", "rank_airports", lambda a: a["states"] == ["TX"] and a["min_enplanements"] == 1_000_000 and a["limit"] == 5),
    ("tell me about BOS", "airport_profile", lambda a: a["code"] == "BOS"),
    ("any ground stops at SFO right now?", "live_airport_status", lambda a: a["codes"] == ["SFO"]),
    ("how is the expansion score calculated?", "explain_methodology", lambda a: a["topic"] == "expansion_score"),
    ("Compare BOS and SEA passenger traffic", "rank_airports", lambda a: a["codes"] == ["BOS", "SEA"]),
])
def test_plan_routes_canonical_questions(engine, text, tool, check):
    p = rules_router.plan(engine, Session(id="t"), text)
    assert p.tool == tool, p
    assert check(p.arguments), p.arguments


def test_roi_and_cargo_questions_are_data_gaps_without_numbers(engine):
    for text in ("What's the ROI of expanding BOS?", "how much would a new terminal at SFO cost?", "what about cargo at Anchorage?"):
        out = rules_router.answer(engine, Session(id="t"), text)
        assert out["intent"] == "data_gap" and out["tool_results"] == []
        assert "Not available" in out["text"]


def test_follow_ups_use_session_context(engine):
    session = Session(id="t")
    first = rules_router.answer(engine, session, "Which airports in New England are strong candidates for terminal expansion?")
    ranked = [x["lid"] for x in first["tool_results"][0]["data"]["ranked"]]
    second = rules_router.plan(engine, session, "tell me about the second one")
    assert second.tool == "airport_profile" and second.arguments["code"] == ranked[1]
    no_scale = rules_router.plan(engine, session, "what if I ignore scale?")
    assert no_scale.tool == "rank_airports" and no_scale.arguments["weights"]["scale"] == 0.0 and no_scale.arguments["states"] == NEW_ENGLAND
    rules_router.answer(engine, session, "compare LAX and SNA congestion")
    added = rules_router.plan(engine, session, "add SFO too")
    assert added.tool == "compare_congestion" and added.arguments["codes"] == ["LAX", "SNA", "SFO"]
    rules_router.answer(engine, session, "add SFO too")
    slots = rules_router.plan(engine, session, "which of these are slot constrained?")
    assert slots.tool == "compare_congestion" and set(slots.arguments["codes"]) == {"LAX", "SNA", "SFO"}


def test_rank_context_survives_a_profile_follow_up(engine):
    session = Session(id="t")
    rules_router.answer(engine, session, "Which airports in New England are strong candidates for terminal expansion?")
    rules_router.answer(engine, session, "tell me about the second one")
    p = rules_router.plan(engine, session, "what if I ignore scale?")
    assert p.tool == "rank_airports" and p.arguments["weights"]["scale"] == 0.0 and p.arguments["states"] == NEW_ENGLAND
    why = rules_router.plan(engine, session, "Why is the first one ranked above the second?")
    assert why.tool == "rank_airports" and len(why.arguments["codes"]) == 2 and why.arguments["codes"][0] == "BOS"


def test_ambiguous_follow_up_asks_for_clarification(engine):
    out = rules_router.answer(engine, Session(id="t"), "what is the long haul share?")
    assert out["intent"] == "clarify" and out["tool_results"] == []


def test_rules_answers_contain_key_numbers(engine):
    session = Session(id="t")
    out = rules_router.answer(engine, session, "What is the unmet flight demand in SFO airport and why?")
    assert "76." in out["text"] or "Unmet Demand Indicator" in out["text"]
    assert "Level 2" in out["text"] and "National Airspace System" in out["text"]
    out = rules_router.answer(engine, session, "What is the percentage of long haul flights out of Anchorage airport?")
    assert "3,000-mile" in out["text"] and "SEA" in out["text"]


# ------------------------------------------------------------------------ tools
@pytest.mark.parametrize("name,args", [
    ("resolve_airports", {"query": "Boston and Santa Ana"}),
    ("rank_airports", {"region": "New England"}),
    ("airport_profile", {"code": "SFO"}),
    ("compare_congestion", {"codes": ["LAX", "SNA"]}),
    ("long_haul_share", {"code": "ANC"}),
    ("demand_pressure", {"code": "SFO"}),
    ("live_airport_status", {"codes": ["SFO"]}),
    ("explain_methodology", {"topic": "unmet_demand"}),
])
def test_every_tool_returns_the_envelope(engine, name, args):
    result = T.dispatch(engine, name, args, Session(id="t"))
    assert result.get("error") is None, result.get("error")
    for key in ("tool", "arguments", "data", "sources", "caveats", "confidence", "method"):
        assert key in result
    assert result["sources"] and all({"name", "url", "period", "retrieved_at"} <= set(s) for s in result["sources"])
    assert result["confidence"]["level"] in {"high", "medium", "low"}


def test_tool_errors_are_returned_not_raised(engine):
    assert "Unknown tool" in T.dispatch(engine, "nope", {})["error"]
    assert "Unknown airport" in T.dispatch(engine, "demand_pressure", {"code": "ZZZZ"})["error"]
    assert "Unknown region" in T.dispatch(engine, "rank_airports", {"region": "Narnia"})["error"]
    assert "codes is required" in T.dispatch(engine, "compare_congestion", {})["error"]


def test_rank_tool_region_and_session_memory(engine):
    session = Session(id="t")
    result = T.dispatch(engine, "rank_airports", {"region": "new england", "limit": 3}, session)
    assert result["data"]["scope"]["states"] == NEW_ENGLAND and len(result["data"]["ranked"]) == 3
    assert session.last_result["tool"] == "rank_airports" and session.active_airports == [x["lid"] for x in result["data"]["ranked"]]
    assert any("percentiles" in c.lower() for c in result["caveats"])


def test_tool_specs_are_valid_json_schemas():
    names = {t["name"] for t in T.TOOL_SPECS}
    assert names == set(T.HANDLERS)
    for spec in T.TOOL_SPECS:
        assert spec["input_schema"]["type"] == "object" and spec["description"]


# --------------------------------------------------------------- grounding check
def test_ground_check_flags_only_numbers_absent_from_tool_results():
    results = [{"data": {"score": 55.83, "enplanements": 36497303, "pct": 0.197, "year": 2035}, "arguments": {}}]
    text = "LAX scores 55.8 with 36,497,303 enplanements; 19.7% of arrivals delayed; forecast to 2035. Bogus figure 123.4% and 999 flights."
    check = ground_check(text, results)
    assert check["ungrounded"] == ["123.4", "999"]
    assert check["checked"] == 6  # small integers are ignored


def test_ground_check_handles_abbreviations_durations_and_recent_turns():
    results = [{"data": {"enplanements": 437108, "ratio": 1.122, "floor": 100000, "max": "1 hour and 42 minutes"}, "arguments": {}, "method": "scale 0-100"}]
    text = "About 0.44M enplanements (100k floor), 12% above peak, ground delay max 1h 42m, in the Lower-48, index 0-100."
    assert ground_check(text, results)["ungrounded"] == []
    assert ground_check("SFO index 85.5 from before", [])["ungrounded"] == ["85.5"]
    assert ground_check("SFO index 85.5 from before", [], extra_pool={85.5})["ungrounded"] == []


# ---------------------------------------------------------------- orchestrator
class FakeLLM:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def complete(self, system, messages, tools, session_context=None):
        self.calls.append({"messages": messages, "context": session_context})
        if isinstance(self.turns[0], Exception):
            raise self.turns.pop(0)
        return self.turns.pop(0)


def test_orchestrator_llm_loop_dispatches_tools_and_grounds_answer(engine):
    fake = FakeLLM([
        AssistantTurn(None, [{"name": "compare_congestion", "arguments": {"codes": ["LAX", "SNA"]}}]),
        AssistantTurn("LAX is more congested than SNA; SFO would be far worse at 99.9% delayed.", []),
    ])
    orch = Orchestrator(engine, SessionStore(), llm_factory=lambda provider: fake)
    response = orch.chat("Compare LA and Santa Ana congestion", provider_override="claude_cli")
    assert response.mode == "llm" and [t["tool"] for t in response.tool_results] == ["compare_congestion"]
    assert response.sources and response.caveats
    assert any("99.9" in w for w in response.warnings)
    # the tool result was fed back to the model as a tool_result block
    second_call = fake.calls[1]["messages"]
    assert second_call[-1]["content"][0]["type"] == "tool_result"
    assert '"congestion_index"' in second_call[-1]["content"][0]["content"]
    # session memory carried the airports for follow-ups
    session = orch.sessions.get_or_create(response.session_id)
    assert session.active_airports == ["LAX", "SNA"] and len(session.messages) == 2


def test_orchestrator_falls_back_to_rules_when_llm_fails(engine):
    orch = Orchestrator(engine, SessionStore(), llm_factory=lambda provider: FakeLLM([LLMError("boom")]))
    response = orch.chat("What is the unmet flight demand in SFO airport and why?", provider_override="anthropic")
    assert response.mode == "rules" and response.tool_results[0]["tool"] == "demand_pressure"
    assert any("LLM unavailable" in w for w in response.warnings)


def test_orchestrator_passes_session_context_to_llm(engine):
    fake = FakeLLM([AssistantTurn("First answer.", []), AssistantTurn("Second answer.", [])])
    orch = Orchestrator(engine, SessionStore(), llm_factory=lambda provider: fake)
    first = orch.chat("Which airports in New England are strong candidates for terminal expansion?", provider_override="rules")
    orch.chat("and the second one?", first.session_id, provider_override="claude_cli")
    assert fake.calls[0]["context"] and "rank_airports" in fake.calls[0]["context"]
    assert fake.calls[0]["messages"][0]["role"] == "user"  # prior turns included as text history


def test_cli_prompt_renders_tool_blocks():
    messages = [{"role": "user", "content": "hi"},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "c1", "name": "airport_profile", "input": {"code": "SFO"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "name": "airport_profile", "content": "{\"x\": 1}"}]}]
    prompt = build_prompt(messages, T.TOOL_SPECS, "Previous tool: none")
    assert "airport_profile {\"code\":\"SFO\"}" in prompt and "[tool result for airport_profile]" in prompt and "Conversation state" in prompt


# -------------------------------------------------------------------------- API
@pytest.fixture()
def client(engine, monkeypatch):
    from app import main
    monkeypatch.setitem(main._state, "orchestrator", Orchestrator(engine, SessionStore()))
    monkeypatch.setitem(main._state, "engine", engine)
    return TestClient(main.app)


def test_api_health_and_methodology(client):
    health = client.get("/api/health")
    assert health.status_code == 200 and health.json()["status"] == "ready" and health.json()["universe_size"] > 10
    method = client.get("/api/methodology")
    assert method.status_code == 200 and "expansion_score" in method.json()
    assert client.get("/api/tools").json()["tools"]


def test_api_chat_rules_mode_and_validation(client):
    response = client.post("/api/chat", json={"message": "Compare LAX and SNA congestion", "provider": "rules"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "rules" and body["tool_results"][0]["tool"] == "compare_congestion" and body["session_id"]
    follow = client.post("/api/chat", json={"message": "add SFO too", "provider": "rules", "session_id": body["session_id"]})
    assert follow.status_code == 200 and {a["lid"] for a in follow.json()["tool_results"][0]["data"]["airports"]} == {"LAX", "SNA", "SFO"}
    assert client.post("/api/chat", json={"message": "x" * 2001}).status_code == 422
    assert client.post("/api/chat", json={"message": "hi", "session_id": "not-a-uuid"}).status_code == 422
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    assert client.post("/api/chat", json={"message": "hi", "provider": "openai"}).status_code == 422


def test_index_is_served(client):
    response = client.get("/")
    assert response.status_code == 200 and "<html" in response.text.lower()


# ------------------------------------------------------------ side-panel endpoints
def test_api_rank_matches_the_chat_ranking_exactly(client):
    """The side panel and the chat must never disagree: both call the same rank_airports tool."""
    panel = client.get("/api/rank", params={"region": "new england", "min_enplanements": 100000, "limit": 10}).json()
    chat = client.post("/api/chat", json={"message": "Which airports in New England are strong candidates for terminal expansion?", "provider": "rules"}).json()
    chat_ranked = chat["tool_results"][0]["data"]["ranked"]
    assert [(x["lid"], x["score"]) for x in panel["data"]["ranked"]] == [(x["lid"], x["score"]) for x in chat_ranked]
    assert panel["data"]["scope"]["states"] == ["CT", "ME", "MA", "NH", "RI", "VT"]
    assert panel["sources"] and panel["caveats"] and panel["confidence"]["level"] in {"high", "medium", "low"}


def test_api_rank_validates_parameters(client):
    assert client.get("/api/rank", params={"region": "narnia"}).status_code == 422
    assert client.get("/api/rank", params={"states": "CA,not-a-code"}).status_code == 422
    assert client.get("/api/rank", params={"limit": 0}).status_code == 422
    assert client.get("/api/rank", params={"limit": 26}).status_code == 422
    assert client.get("/api/rank", params={"min_enplanements": -1}).status_code == 422
    ok = client.get("/api/rank", params={"states": "ca, tx", "limit": 5, "min_enplanements": 1000000}).json()
    assert ok["data"]["scope"]["states"] == ["CA", "TX"] and len(ok["data"]["ranked"]) <= 5
    assert all(x["metrics"]["enplanements"] >= 1000000 for x in ok["data"]["ranked"])


def test_api_regions_and_live(client):
    regions = client.get("/api/regions").json()
    assert "new england" in regions["regions"] and regions["states"]["MA"] == "Massachusetts"
    live = client.get("/api/live").json()
    assert "by_type" in live["data"] and live["data"]["by_type"]["ground_delay"][0]["airport"] == "SFO"
    assert live["sources"][0]["name"].startswith("FAA NAS")


# ------------------------------------------------------------- review follow-ups
def test_api_rank_honours_zero_floor_and_rejects_unknown_states(client):
    zero = client.get("/api/rank", params={"min_enplanements": 0, "limit": 5}).json()
    default = client.get("/api/rank", params={"limit": 5}).json()
    assert zero["data"]["scope"]["min_enplanements"] == 0 and default["data"]["scope"]["min_enplanements"] == 100000
    assert zero["data"]["universe_size"] > default["data"]["universe_size"]
    assert client.get("/api/rank", params={"states": "ZZ"}).status_code == 422


def test_api_regions_collapses_aliases(client):
    names = client.get("/api/regions").json()["regions"]
    assert len(names) == len(set(names)) and not ({"mid atlantic", "mid-atlantic"} <= set(names))


def test_security_headers_present(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert "Content-Security-Policy" in client.get("/").headers


def test_token_auth_when_configured(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings, "app_token", "correct-horse")
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/health", headers={"Authorization": "Bearer correct-horse"}).status_code == 200
    assert client.get("/").status_code == 200  # static shell stays reachable; data does not


def test_remote_clients_are_refused_without_token(engine, monkeypatch):
    from app import main
    monkeypatch.setitem(main._state, "orchestrator", Orchestrator(engine, SessionStore()))
    monkeypatch.setattr(main.settings, "app_token", "")
    remote = TestClient(main.app, client=("203.0.113.9", 4242))
    assert remote.get("/api/health").status_code == 403
    local = TestClient(main.app, client=("127.0.0.1", 4242))
    assert local.get("/api/health").status_code == 200


def test_rank_tool_default_floor_and_excluded_codes(engine):
    from app.kpi.scoring import DEFAULT_MIN_ENPLANEMENTS
    session = Session(id="t")
    out = rules_router.answer(engine, session, "Compare BOS and SEA passenger traffic")
    data = out["tool_results"][0]["data"]
    assert data["scope"]["min_enplanements"] == DEFAULT_MIN_ENPLANEMENTS and [x["lid"] for x in data["ranked"]] == ["BOS", "SEA"]
    below = T.dispatch(engine, "rank_airports", {"codes": ["BOS", "IAN"]}, None)  # IAN is a tiny CS airport in the fixture
    assert below["data"]["excluded_below_floor"] == ["IAN"] and any("below the" in c for c in below["caveats"])
    assert "must be >= 0" in T.dispatch(engine, "rank_airports", {"limit": 99})["error"]


def test_expansion_scores_cache_returns_independent_copies(table):
    from app.kpi.scoring import expansion_scores
    first = expansion_scores(table, states=["MA"], limit=0)
    second = expansion_scores(table, states=["MA"], limit=0)
    assert first["ranked"][0]["rank"] == 1 and first == second
    first["ranked"][0]["score"] = -1
    assert expansion_scores(table, states=["MA"], limit=0)["ranked"][0]["score"] != -1
    assert "_expansion_score_cache" in table.attrs


def test_cache_backs_off_after_a_failed_download(monkeypatch, tmp_path):
    import httpx
    from app.sources import cache
    monkeypatch.setattr(cache.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(cache.settings, "offline", False)
    calls = {"n": 0}

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, *args, **kwargs):
            calls["n"] += 1
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(cache.httpx, "Client", FailingClient)
    cache._last_failure.clear()
    with pytest.raises(cache.SourceUnavailable):
        cache.fetch_bytes("https://example.invalid/x", "unit_test_source.bin", 60)
    with pytest.raises(cache.SourceUnavailable):
        cache.fetch_bytes("https://example.invalid/x", "unit_test_source.bin", 60)
    assert calls["n"] == 1  # second attempt short-circuited by the back-off
    cache._last_failure.clear()
