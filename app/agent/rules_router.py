"""Rules-based interpreter: maps analyst questions to tools and narrates results without an LLM.

It is the fallback when no LLM provider is configured or an LLM call fails, and it shares
``tools.dispatch`` and the session memory with the LLM path so both behave the same.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agent import tools as T
from app.agent.prompts import RULES_HELP
from app.agent.session import Session
from app.engine import Engine

ORDINALS = {"first": 1, "1st": 1, "top": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "last": -1}
GAP_RE = re.compile(r"\b(roi|return on investment|irr|npv|payback|project cost|construction cost|capex|how much (would|will|does) it cost|"
                    r"cost to (build|expand|modern)|how much (would|will|does|did) .{0,60}cost|\bcosts?\b|\bprice tag\b|financ\w*|funding|load factors?|gate capacity|terminal capacity|cargo|tonnage|fares?|ticket prices?)\b")
METHOD_RE = re.compile(r"\b(methodolog\w*|how (do|did|does) (you|it|the tool) (score|rank|calculate|compute|work)|how (is|are) .{0,40}(calculated|computed|scored|derived)|"
                       r"weights?|formula|what does the score mean|scoring (method|logic)|explain the (score|index|indicator))\b")
CONFIDENCE_RE = re.compile(r"\b(how confident|confidence|how sure|how reliable|uncertain\w*|trust (these|those|the) (numbers|results))\b")
LIVE_RE = re.compile(r"\b(right now|currently|live|today|at the moment|ground stop|ground delay|delays? now|nas status)\b")
LONG_HAUL_RE = re.compile(r"long[- ]?haul|stage length|international flights|transcontinental|route lengths?")
DEMAND_RE = re.compile(r"\b(unmet|latent demand|demand pressure|capacity[- ]constrain\w*|constrained|pressure|under-?served|unserved|demand at|demand in|flight demand)\b")
CONGESTION_RE = re.compile(r"congest\w*|\bdelays?\b|delayed|on[- ]time|cancell\w*|taxi|punctual\w*")
ADD_RE = re.compile(r"\b(add|include|also|too|as well|and compare)\b")
SLOT_RE = re.compile(r"\bslot|schedule[- ]facilitat\w*|level [23]\b")
SCALE_OFF_RE = re.compile(r"(ignore|without|drop|remove|exclude|no)\s+(the\s+)?scale|scale\s+(weight\s+)?(to\s+)?(0|zero)")
RANK_RE = re.compile(r"candidate|expansion|opportunit\w*|invest\w*|rank\w*|\btop\b|\bbest\b|strong|promising|which airports|what airports|growing|fastest|screen|shortlist")
PROFILE_RE = re.compile(r"\b(tell me about|profile|overview|snapshot|forecast|history|how big|traffic at|passengers at|about it|its\b|it's\b|that airport)\b")
FLOOR_RE = re.compile(r"(?:at least|over|more than|minimum(?: of)?|min\.?|above|floor of)\s+([\d][\d.,]*)\s*(k|thousand|m|mm|million)?\s*(?:annual\s+)?(?:passengers|enplanements|boardings|pax)")
LIMIT_RE = re.compile(r"\btop\s+(\d{1,2})\b")


@dataclass
class Plan:
    intent: str
    tool: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    note: Optional[str] = None


def _floor(text: str) -> Optional[int]:
    m = FLOOR_RE.search(text.lower())
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit in {"k", "thousand"}:
        value *= 1_000
    elif unit in {"m", "mm", "million"}:
        value *= 1_000_000
    return int(value)


def _ordinal(text: str) -> Optional[int]:
    lowered = text.lower()
    m = re.search(r"(?:#|number\s+|no\.\s*)(\d{1,2})\b", lowered)
    if m:
        return int(m.group(1))
    for word, idx in ORDINALS.items():
        if re.search(r"\b" + word + r"\b(?:\s+(one|airport|ranked|result|candidate))?", lowered) and not re.search(r"\btop\s+\d", lowered):
            if word == "top" and not re.search(r"\btop (one|airport|ranked|result|candidate)\b", lowered):
                continue
            return idx
    return None


def plan(engine: Engine, session: Session, text: str) -> Plan:
    lowered = text.lower()
    resolved = engine.registry.resolve(text)
    codes = resolved["codes"] + resolved["places"]
    states = resolved["states"]
    last = session.last_result or {}
    last_rank = session.last_by_tool.get("rank_airports") if hasattr(session, "last_by_tool") else None
    active = list(session.active_airports)

    if GAP_RE.search(lowered) and not LONG_HAUL_RE.search(lowered):
        return Plan("data_gap", None, {"codes": codes or active})
    if CONFIDENCE_RE.search(lowered) and not codes:
        return Plan("confidence", "explain_methodology", {"topic": "confidence"})
    if METHOD_RE.search(lowered):
        topic = "expansion_score"
        if CONGESTION_RE.search(lowered):
            topic = "congestion_index"
        elif LONG_HAUL_RE.search(lowered):
            topic = "long_haul_share"
        elif DEMAND_RE.search(lowered):
            topic = "unmet_demand"
        elif re.search(r"source|data|where .* from", lowered):
            topic = "data_sources"
        elif re.search(r"limit|can't|cannot|missing|gap", lowered):
            topic = "limitations"
        return Plan("methodology", "explain_methodology", {"topic": topic})
    if LIVE_RE.search(lowered):
        return Plan("live", "live_airport_status", {"codes": codes or active})
    if SLOT_RE.search(lowered):
        targets = codes or (last.get("airports") or active)
        if not targets:
            return Plan("clarify", None, {}, "Which airports should I check for FAA slot or schedule-facilitation status?")
        return Plan("congestion", "compare_congestion", {"codes": targets[:10]}, "Slot status is shown in the 'Qualifying runways / FAA slot level' row (3 = slot-controlled, 2 = schedule-facilitated).")
    if LONG_HAUL_RE.search(lowered):
        target = codes[:1] or active[:1]
        if not target:
            return Plan("clarify", None, {}, "Which airport should I compute the long-haul share for?")
        return Plan("long_haul", "long_haul_share", {"code": target[0]})
    if DEMAND_RE.search(lowered) and not re.search(r"\bcompare\b", lowered):
        target = codes[:1] or active[:1]
        if not target:
            return Plan("clarify", None, {}, "Which airport should I assess for unmet demand?")
        return Plan("demand", "demand_pressure", {"code": target[0]})
    if CONGESTION_RE.search(lowered):
        targets = codes or active
        if ADD_RE.search(lowered) and last.get("tool") == "compare_congestion":
            targets = list(dict.fromkeys(last.get("airports", []) + codes))
        if not targets:
            return Plan("clarify", None, {}, "Which airports should I compare for congestion?")
        return Plan("congestion", "compare_congestion", {"codes": targets})
    if ADD_RE.search(lowered) and codes and last.get("tool") in {"compare_congestion", "rank_airports"}:
        merged = list(dict.fromkeys(last.get("airports", []) + codes))
        if last["tool"] == "compare_congestion":
            return Plan("congestion", "compare_congestion", {"codes": merged})
        return Plan("rank", "rank_airports", {"codes": merged, "min_enplanements": 0, "limit": 0})
    ordinal = _ordinal(text)
    if ordinal is not None and last_rank and not codes and re.search(r"\bwhy\b", lowered) and re.search(r"\b(above|over|higher|ahead|before|beat)\b", lowered):
        airports = last_rank.get("airports", [])
        pair = [a for i, a in enumerate(airports) if i in {0, 1}] if ordinal == 1 else airports[max(0, ordinal - 2):ordinal]
        if len(pair) == 2:
            return Plan("rank", "rank_airports", {"codes": pair, "min_enplanements": 0, "limit": 0},
                        "Side-by-side scores for the two airports; the drivers line explains what separates them.")
    if ordinal is not None and last.get("airports") and not codes:
        airports = last["airports"]
        idx = ordinal - 1 if ordinal > 0 else len(airports) - 1
        if 0 <= idx < len(airports):
            return Plan("profile", "airport_profile", {"code": airports[idx]})
    if SCALE_OFF_RE.search(lowered) and last_rank:
        args = dict(last_rank.get("arguments", {}))
        args.pop("weights", None)
        args["weights"] = {"forecast_growth": 0.30, "demand_momentum": 0.20, "capacity_pressure": 0.30, "scale": 0.0}
        return Plan("rank", "rank_airports", args, "Re-ran the previous screen with the scale weight set to zero.")
    floor = _floor(text)
    limit_match = LIMIT_RE.search(lowered)
    if RANK_RE.search(lowered) or (states and not codes) or len(codes) >= 2 or re.search(r"\bcompare\b|\bvs\.?\b|versus", lowered):
        args: Dict[str, Any] = {}
        if states:
            args["states"] = states
        elif codes:
            args["codes"] = codes
            args["min_enplanements"] = 0
            args["limit"] = 0
        elif re.search(r"national|nationwide|in the (us|u\.s\.|united states|country)|across the (us|country)", lowered):
            pass
        elif last_rank and re.search(r"\b(those|these|them|sort|re-?rank|again|instead)\b", lowered):
            args = dict(last_rank.get("arguments", {}))
        elif not states and not codes and last.get("states"):
            args["states"] = last["states"]
        if floor is not None:
            args["min_enplanements"] = floor
        if limit_match:
            args["limit"] = int(limit_match.group(1))
        return Plan("rank", "rank_airports", args)
    if len(codes) == 1:
        return Plan("profile", "airport_profile", {"code": codes[0]})
    if PROFILE_RE.search(lowered) and active:
        return Plan("profile", "airport_profile", {"code": active[0]})
    return Plan("help", None, {})


# ------------------------------------------------------------------------ narration
def _n(v: Any, digits: int = 0) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def _pct(v: Any, digits: int = 1) -> str:
    return "n/a" if v is None else f"{float(v):.{digits}f}%"


def _signed(v: Any, digits: int = 1) -> str:
    return "n/a" if v is None else f"{float(v):+.{digits}f}%"


def _label(engine: Engine, lid: str) -> str:
    airport = engine.registry.get(lid)
    return f"{airport.name} ({airport.iata or airport.lid})" if airport else lid


def narrate_rank(result: Dict[str, Any], engine: Engine, note: Optional[str] = None) -> str:
    data = result["data"]
    if not data.get("ranked"):
        return data.get("message") or "No airports matched that screen."
    scope = data["scope"]
    if scope.get("codes"):
        scope_label = ", ".join(scope["codes"])
    elif scope.get("states"):
        scope_label = "states " + ", ".join(scope["states"])
    else:
        scope_label = "United States"
    faa = engine.faa
    lines = [f"**Expansion Opportunity screen: {scope_label}**", ""]
    if note:
        lines += [note, ""]
    lines.append(f"Universe: {data['universe_size']} US primary/commercial-service airports with at least {_n(data['min_enplanements'])} annual enplanements "
                 f"(FAA CY{faa.latest_year}{', preliminary' if faa.preliminary else ''}). Scores are national percentiles (0-100); the filter is applied after scoring. "
                 f"Weights: forecast growth {data['weights']['forecast_growth']:.0%}, momentum {data['weights']['demand_momentum']:.0%}, "
                 f"capacity pressure {data['weights']['capacity_pressure']:.0%}, scale {data['weights']['scale']:.0%}.")
    lines += ["", "| # | Airport | Score | Fcst growth | Momentum | Capacity pressure | Scale | Enplanements | Confidence |", "|---|---|---|---|---|---|---|---|---|"]
    for x in data["ranked"]:
        s = x["sub_scores"]
        lines.append(f"| {x['rank']} | {x['name']} ({x['iata'] or x['lid']}), {x['state']} | **{_n(x['score'], 1)}** | {_n(s['forecast_growth'], 0)} | {_n(s['demand_momentum'], 0)} | "
                     f"{_n(s['capacity_pressure'], 0)} | {_n(s['scale'], 0)} | {_n(x['metrics']['enplanements'])} | {x['confidence']} |")
    top = data["ranked"][0]
    m = top["metrics"]
    drivers = "; ".join(f"{d['label'].split(' (')[0]} at the {d['percentile']:.0f}th percentile" for d in top["drivers"])
    lines += ["", f"**Why {top['name']} ranks first:** {drivers}. Key figures: {_n(m['enplanements'])} enplanements ({_signed(m['yoy_pct'])} YoY), "
              f"FAA TAF forecast CAGR {_pct(m['forecast_cagr_pct'])} over ten years, {_n(m['ops_per_runway'])} air-carrier/air-taxi operations per qualifying runway, "
              f"{_pct(m['del15_pct'])} of arrivals delayed 15+ min with {_pct(m['nas_share_pct'])} of delays attributed to the NAS"
              + (f", FAA slot Level {m['slot_level']}" if m["slot_level"] else "") + "."]
    alt = sorted(data["ranked"], key=lambda r: -(r["score_without_scale"] or 0))[:3]
    alt_labels = ", ".join("{} ({})".format(r["iata"] or r["lid"], _n(r["score_without_scale"], 1)) for r in alt)
    lines.append(f"**Sensitivity:** with the scale component removed, the top three would be {alt_labels}.")
    lines += ["", "**Assumptions and limits:** " + " ".join(result["caveats"][:3])]
    return "\n".join(lines)


def narrate_congestion(result: Dict[str, Any], engine: Engine) -> str:
    data = result["data"]
    if not data["airports"]:
        return "None of those airports are in the scored universe (primary/commercial-service, 100k+ enplanements): " + ", ".join(data["not_found"])
    period = engine.delay.period_label if engine.delay else "n/a"
    lines = [f"**Congestion comparison ({period}, BTS arrivals; taxi-out from the {engine.ontime.period_label if engine.ontime else 'n/a'} route snapshot)**", "",
             "| Metric | " + " | ".join(f"{a['name']} ({a['iata'] or a['lid']})" for a in data["airports"]) + " | National median |",
             "|---|" + "---|" * len(data["airports"]) + "---|"]
    med = data["national_medians"]
    rows = [("Congestion Index (0-100)", lambda a: _n(a["congestion_index"], 1), "50"),
            ("Arrivals delayed 15+ min", lambda a: _pct(a["metrics"]["del15_pct"]), _pct(med.get("del15_pct"))),
            ("Delays attributed to NAS (capacity/weather flow)", lambda a: _pct(a["metrics"]["nas_share_pct"]), _pct(med.get("nas_share_pct"))),
            ("... of which weather itself", lambda a: _pct(a["metrics"]["weather_share_pct"]), "n/a"),
            ("Arrivals cancelled", lambda a: _pct(a["metrics"]["cancel_pct"], 2), _pct(med.get("cancel_pct"), 2)),
            ("Average taxi-out (min)", lambda a: _n(a["metrics"]["avg_taxi_out_min"], 1), _n(med.get("avg_taxi_out_min"), 1)),
            ("Air-carrier + air-taxi ops per runway (annual)", lambda a: _n(a["metrics"]["ops_per_runway"]), _n(med.get("ops_per_runway"))),
            ("Qualifying runways / FAA slot level", lambda a: f"{_n(a['metrics']['runways_qualifying'])} / {a['metrics']['slot_level'] or 'none'}", ""),
            ("Arrivals in window", lambda a: _n(a["metrics"]["arr_flights_12m"]), "")]
    for label, fn, medv in rows:
        lines.append(f"| {label} | " + " | ".join(fn(a) for a in data["airports"]) + f" | {medv} |")
    a0 = data["airports"][0]
    verdict = f"**Verdict:** {a0['name']} is the most congested of the set (index {_n(a0['congestion_index'], 1)})."
    if len(data["airports"]) > 1:
        a1 = data["airports"][1]
        verdict += (f" Versus {a1['name']} (index {_n(a1['congestion_index'], 1)}): {_pct(a0['metrics']['del15_pct'])} vs {_pct(a1['metrics']['del15_pct'])} of arrivals delayed, "
                    f"NAS share {_pct(a0['metrics']['nas_share_pct'])} vs {_pct(a1['metrics']['nas_share_pct'])}, taxi-out {_n(a0['metrics']['avg_taxi_out_min'], 1)} vs "
                    f"{_n(a1['metrics']['avg_taxi_out_min'], 1)} min, {_n(a0['metrics']['ops_per_runway'])} vs {_n(a1['metrics']['ops_per_runway'])} operations per runway.")
    lines += ["", verdict]
    live = [f"{a['iata'] or a['lid']}: " + "; ".join(f"{e['type'].replace('_', ' ')} ({e.get('reason', '')}{', avg ' + e['average'] if e.get('average') else ''})" for e in a["live_status"])
            for a in data["airports"] if a["live_status"]]
    lines.append("**Live FAA status:** " + (" | ".join(live) if live else "no active ground delays, ground stops or closures at these airports") +
                 (f" (as of {data['live_status_update_time']})." if data.get("live_status_update_time") else "."))
    if data["not_found"]:
        lines.append(f"Not in the scored universe: {', '.join(data['not_found'])}.")
    lines += ["", "**Assumptions and limits:** " + " ".join(result["caveats"][:3])]
    return "\n".join(lines)


def narrate_long_haul(result: Dict[str, Any], engine: Engine) -> str:
    data = result["data"]
    if "error" in data and "shares_by_threshold" not in data:
        return data["error"]
    a = data["airport"]
    hs = data["shares_by_threshold"]
    lines = [f"**Long-haul share of departures from {a['name']} ({a['iata'] or a['lid']})**", "",
             f"About **{_pct(data['headline_share_pct'])}** of scheduled domestic departures in {', '.join(data['months'])} were long-haul at the 3,000-mile threshold "
             f"({_n(hs['3000']['departures'])} of {_n(data['total_departures'])} departures to {data['destinations']} destinations; average stage length about {_n(data['avg_stage_length_mi'])} miles).",
             "", "| Threshold | Departures | Share |", "|---|---|---|"]
    for key in sorted(hs, key=lambda k: int(k)):
        lines.append(f"| >= {_n(hs[key]['threshold_mi'])} mi | {_n(hs[key]['departures'])} | {_pct(hs[key]['share_pct'])} |")
    lines += ["", "**Top routes:** " + "; ".join(f"{r['dest']} {_n(r['distance_mi'])} mi ({_n(r['departures'])} deps)" for r in data["top_routes"][:6]) + "."]
    lines.append("**Longest routes:** " + "; ".join(f"{r['dest']} {_n(r['distance_mi'])} mi ({_n(r['departures'])})" for r in data["longest_routes"]) + ".")
    taf = data.get("taf_context")
    if taf and taf.get("international_enplanement_share_pct") is not None:
        lines.append(f"**International context (FAA TAF {taf['year']}):** international passengers were {_pct(taf['international_enplanement_share_pct'])} of enplanements; "
                     f"the airport handled {_n(taf['air_carrier_plus_air_taxi_ops'])} air-carrier and air-taxi operations, which include all-cargo flights that are absent from the route data above.")
    lines += ["", "**Assumptions and limits:** " + " ".join(data["caveats"][:2])]
    return "\n".join(lines)


def narrate_demand(result: Dict[str, Any], engine: Engine) -> str:
    data = result["data"]
    a, f = data["airport"], data["facts"]
    lines = [f"**Unmet Demand Indicator for {a['name']} ({a['iata'] or a['lid']}): {_n(data['indicator'], 1)} / 100** (confidence {data['confidence']}; "
             f"mean of six national-percentile pressure signals across {data['universe_size']} airports)", ""]
    lines.append(f"Demand: {_n(f['enplanements_faa'])} enplanements in FAA CY{engine.faa.latest_year} ({_signed(f['yoy_pct'])} YoY); FAA TAF forecasts {_n(f['taf_enpl_forecast_h'])} by "
                 f"{int(f['taf_forecast_end_year']) if f['taf_forecast_end_year'] else 'n/a'} ({_pct(f['forecast_cagr_pct'])} CAGR), unconstrained by capacity.")
    lines += ["", "**Why demand is pressing on capacity:**"] + [f"- {r}" for r in data["reasons"]]
    comps = data["component_percentiles"]
    lines += ["", "Component percentiles: " + ", ".join(f"{data['component_labels'][k].split(' (')[0]} {_n(v, 0)}" for k, v in comps.items() if v is not None) + "."]
    if data.get("live_status", {}).get("events"):
        ev = [e for items in data["live_status"]["events"].values() for e in items]
        if ev:
            lines.append("Live FAA status now: " + "; ".join(f"{e['type'].replace('_', ' ')} ({e.get('reason', '')})" for e in ev) + ".")
    lines += ["", "**What this cannot tell you:** " + data["caveats"][0], "Also: " + data["caveats"][1]]
    return "\n".join(lines)


def narrate_profile(result: Dict[str, Any], engine: Engine) -> str:
    d = result["data"]
    a, faa = d["airport"], d["faa"]
    lines = [f"**{a['name']} ({a['iata'] or a['lid']}), {a['city']}, {a['state']}**", "",
             f"- FAA CY{faa['year']}{' (preliminary)' if faa['preliminary'] else ''}: {_n(faa['enplanements'])} enplanements ({_signed(faa['yoy_pct'])} YoY), "
             f"national rank #{faa['national_rank_by_enplanements']} by enplanements, {faa['service_level']} service level, hub size {faa['hub_size']}.",
             f"- Airfield: {_n(a['runways_qualifying'])} qualifying runways; FAA slot level {a['slot_level'] or 'none'}."]
    if d.get("forecast"):
        fc, ops = d["forecast"], d["operations"]
        lines.append(f"- FAA TAF: {_n(fc['enplanements_end'])} enplanements forecast for {int(fc['end_year'])} ({_pct(fc['cagr_pct'])} CAGR from {int(fc['start_year'])}); "
                     f"recovery vs 2019 {_n((fc['recovery_ratio_vs_2019'] or 0) * 100)}%; international share {_pct(fc['international_share_pct'])}.")
        lines.append(f"- Operations ({int(ops['year']) if ops['year'] else 'n/a'}): {_n(ops['air_carrier_plus_air_taxi'])} air-carrier + air-taxi ops; peak {_n(ops['peak'])} in "
                     f"{int(ops['peak_year']) if ops['peak_year'] else 'n/a'}; forecast {_n(ops['forecast_end_year'])} = {_n((ops['forecast_vs_peak'] or 0) * 100)}% of peak; "
                     f"{_n(ops['ops_per_runway'])} ops per runway; passengers per operation {_signed(ops['passengers_per_op_change_since_2019_pct'])} since 2019.")
    if d.get("delays_12m"):
        dl = d["delays_12m"]
        lines.append(f"- Delays (trailing 12 months, {_n(dl['arrivals'])} arrivals): {_pct(dl['delayed_15_pct'])} delayed 15+ min, {_pct(dl['cancelled_pct'], 2)} cancelled; "
                     f"delay causes: NAS {_pct(dl['nas_share_pct'])}, weather {_pct(dl['weather_share_pct'])}, carrier {_pct(dl['carrier_share_pct'])}, late aircraft {_pct(dl['late_aircraft_share_pct'])}.")
    elif d.get("in_scored_universe"):
        lines.append("- Delays: not enough BTS reporting-carrier arrivals for reliable delay statistics.")
    if d.get("route_snapshot"):
        rs = d["route_snapshot"]
        lines.append(f"- Route snapshot: {_n(rs['departures'])} departures, {_pct(rs['dep_delayed_15_pct'])} departed 15+ min late, average taxi-out {_n(rs['avg_taxi_out_min'], 1)} min.")
    if d.get("expansion_score"):
        es = d["expansion_score"]
        s = es["sub_scores"]
        lines.append(f"- Expansion Opportunity Score: **{_n(es['score'], 1)}** (forecast growth {_n(s['forecast_growth'], 0)}, momentum {_n(s['demand_momentum'], 0)}, "
                     f"capacity pressure {_n(s['capacity_pressure'], 0)}, scale {_n(s['scale'], 0)}; confidence {es['confidence']}).")
    ev = [e for items in d["live_status"].get("events", {}).values() for e in items]
    lines.append("- Live FAA status: " + ("; ".join(f"{e['type'].replace('_', ' ')} ({e.get('reason', '')})" for e in ev) if ev else "no active delay programs") + ".")
    if d.get("taf_history"):
        actual = [h for h in d["taf_history"] if h["kind"] == "actual" and h["year"] >= 2019]
        if actual:
            lines += ["", "TAF enplanements (actual): " + ", ".join(f"{h['year']} {_n(h['enplanements'])}" for h in actual) + "."]
    lines += ["", "**Assumptions and limits:** " + " ".join(result["caveats"][:2])]
    return "\n".join(lines)


def narrate_live(result: Dict[str, Any], engine: Engine) -> str:
    d = result["data"]
    if d.get("error"):
        return f"Live FAA status is unavailable right now ({d['error']})."
    if "events" in d:
        parts = []
        for code, items in d["events"].items():
            parts.append(f"- {code}: " + ("; ".join(f"{e['type'].replace('_', ' ')} ({e.get('reason', '')}{', avg ' + e['average'] if e.get('average') else ''})" for e in items) if items else "no active delay programs"))
        return f"**Live FAA NAS status (as of {d.get('update_time') or 'n/a'})**\n" + "\n".join(parts) + "\n\n" + result["caveats"][0]
    parts = [f"**Live FAA NAS status (as of {d.get('update_time') or 'n/a'})** - {len(d['airports_affected'])} airports with active events."]
    for kind, items in d["by_type"].items():
        parts.append(f"- {kind.replace('_', ' ')}: " + ", ".join(f"{i['airport']} ({i.get('reason', '')})" for i in items))
    return "\n".join(parts) + "\n\n" + result["caveats"][0]


def narrate_methodology(result: Dict[str, Any], engine: Engine, session: Session) -> str:
    d = result["data"]
    text = d.get("text", "")
    if d["topic"] == "data_sources":
        rows = [f"- {s['name']}: {s.get('period')}; vintage {s.get('vintage')}; retrieved {s.get('retrieved_at')}; {s.get('url')}" for s in d["sources"]]
        return "**Data sources**\n" + "\n".join(rows)
    if d["topic"] == "limitations":
        return "**Limitations**\n" + text + "\n\n" + "\n".join(f"- {c}" for c in d["source_caveats"])
    if d["topic"] == "confidence":
        extra = ""
        if session.last_result:
            extra = f"\n\nThe previous result covered {', '.join(session.last_result.get('airports', [])[:10]) or 'no airports'}; its confidence flags are in the sources panel of that answer."
        return "**How confidence is assessed**\n" + text + extra
    weights = d.get("weights")
    return f"**Methodology: {d['topic'].replace('_', ' ')}**\n{text}" + (f"\n\nWeights: {weights}" if weights else "")


def narrate_gap(plan: Plan, engine: Engine) -> str:
    codes = plan.arguments.get("codes") or []
    offer = (f" For {', '.join(codes)} I can show enplanements and growth, the FAA forecast, operations vs demonstrated peak, delay statistics, runway counts and slot status, "
             f"which together indicate where capacity is binding." if codes else
             " I can rank expansion candidates, compare congestion, compute long-haul shares and explain unmet-demand pressure from FAA and BTS data.")
    return "**Not available in this tool.** " + T.GAP_STATEMENT + offer


def answer(engine: Engine, session: Session, text: str) -> Dict[str, Any]:
    p = plan(engine, session, text)
    if p.intent == "help":
        return {"text": RULES_HELP, "tool_results": [], "intent": p.intent}
    if p.intent == "clarify":
        return {"text": p.note or "Could you name the airport?", "tool_results": [], "intent": p.intent}
    if p.intent == "data_gap":
        return {"text": narrate_gap(p, engine), "tool_results": [], "intent": p.intent}
    result = T.dispatch(engine, p.tool, p.arguments, session)
    if result.get("error"):
        return {"text": f"I could not complete that: {result['error']}", "tool_results": [result], "intent": p.intent}
    if p.tool == "rank_airports":
        text_out = narrate_rank(result, engine, p.note)
    elif p.tool == "compare_congestion":
        text_out = narrate_congestion(result, engine)
        if p.note:
            text_out = p.note + "\n\n" + text_out
    elif p.tool == "long_haul_share":
        text_out = narrate_long_haul(result, engine)
    elif p.tool == "demand_pressure":
        text_out = narrate_demand(result, engine)
    elif p.tool == "airport_profile":
        text_out = narrate_profile(result, engine)
    elif p.tool == "live_airport_status":
        text_out = narrate_live(result, engine)
    else:
        text_out = narrate_methodology(result, engine, session)
    return {"text": text_out, "tool_results": [result], "intent": p.intent}
