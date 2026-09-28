"""Deterministic tools exposed to the agent (and to the rules-based router).

Every tool returns the same envelope::

    {"tool": name, "arguments": {...}, "data": {...}, "sources": [...], "caveats": [...],
     "confidence": {"level": "high|medium|low", ...}, "method": "..."}

The LLM only narrates these envelopes; it never computes numbers itself.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from app.engine import Engine
from app.agent.session import Session
from app.kpi import congestion, demand, long_haul, scoring

TOPICS = ["expansion_score", "congestion_index", "long_haul_share", "unmet_demand", "data_sources", "limitations", "confidence"]

TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "resolve_airports",
        "description": "Resolve free text (airport codes, airport or city names, metro nicknames like 'LA', US states or regions like 'New England') to airports and state codes. Use when unsure what an airport reference means.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
    },
    {
        "name": "rank_airports",
        "description": "Deterministic Expansion Opportunity Score ranking (0-100 national percentiles) for terminal/capacity expansion candidates. Filter by US states, a named region, or explicit airport codes. Returns sub-scores, drivers, raw metrics, a no-scale sensitivity score and confidence per airport.",
        "input_schema": {
            "type": "object",
            "properties": {
                "states": {"type": "array", "items": {"type": "string"}, "description": "Two-letter state codes"},
                "region": {"type": "string", "description": "Named region, e.g. 'New England', 'Pacific Northwest'"},
                "codes": {"type": "array", "items": {"type": "string"}, "description": "Airport codes to score/compare"},
                "min_enplanements": {"type": "integer", "description": "Volume floor, default 100000"},
                "limit": {"type": "integer", "description": "Max rows, default 10"},
                "weights": {"type": "object", "description": "Override weights: forecast_growth, demand_momentum, capacity_pressure, scale (renormalized)",
                            "properties": {"forecast_growth": {"type": "number"}, "demand_momentum": {"type": "number"},
                                           "capacity_pressure": {"type": "number"}, "scale": {"type": "number"}}, "additionalProperties": False},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "airport_profile",
        "description": "Full profile of one airport: FAA enplanements and growth, TAF history and forecast, operations, runways, slot status, delay statistics, route snapshot, live FAA status.",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False},
    },
    {
        "name": "compare_congestion",
        "description": "Compare congestion for two or more airports: Congestion Index plus raw delay, cancellation, delay-cause, taxi-out and operations-per-runway metrics, with live FAA NAS status.",
        "input_schema": {"type": "object", "properties": {"codes": {"type": "array", "items": {"type": "string"}, "minItems": 1}}, "required": ["codes"], "additionalProperties": False},
    },
    {
        "name": "long_haul_share",
        "description": "Share of departures that are long-haul for one airport (default headline threshold 3,000 statute miles; 1,500 and 2,500 shown), top routes with distances, and coverage caveats.",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}, "thresholds_mi": {"type": "array", "items": {"type": "integer"}}},
                         "required": ["code"], "additionalProperties": False},
    },
    {
        "name": "demand_pressure",
        "description": "Unmet Demand Indicator (0-100) for one airport with the deterministic reasons behind it: forecast vs demonstrated peak operations, delay and NAS-attribution rates, slot status, recovery vs 2019, up-gauging.",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False},
    },
    {
        "name": "live_airport_status",
        "description": "Current FAA National Airspace System status (ground delay programs, ground stops, departure/arrival delays, closures) for given airports, or nationwide if none given.",
        "input_schema": {"type": "object", "properties": {"codes": {"type": "array", "items": {"type": "string"}}}, "additionalProperties": False},
    },
    {
        "name": "explain_methodology",
        "description": "Return the exact methodology text (weights, formulas, data sources, vintages, limitations) so it can be quoted accurately.",
        "input_schema": {"type": "object", "properties": {"topic": {"type": "string", "enum": TOPICS}}, "required": ["topic"], "additionalProperties": False},
    },
]

SCORE_CAVEAT = ("Scores are relative national percentiles (0-100) for screening, not probabilities of success or investment returns; "
                "they do not include project costs, terminal/gate capacity or financing.")
GAP_STATEMENT = ("Not available in this tool: project costs and ROI, terminal or gate design capacity, seat capacity and load factors, "
                 "cargo tonnage, fares, catchment demographics and airline schedule plans. Answers on those topics would be speculation.")


class ToolError(ValueError):
    pass


def _clean(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _codes(values: Optional[Sequence[str]]) -> List[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(v).strip().upper() for v in values if str(v).strip()]


def source_caveats(engine: Engine, keys: Sequence[str]) -> List[str]:
    out: List[str] = []
    if "faa" in keys:
        out.append(f"FAA enplanements count passenger boardings (not total passengers); the latest year (CY{engine.faa.latest_year}) is "
                   f"{'preliminary' if engine.faa.preliminary else 'final'}.")
    if "taf" in keys and engine.taf:
        out.append(f"FAA TAF actuals run through {engine.taf.last_actual_year}; TAF forecasts are unconstrained (they assume capacity is provided).")
    if "delay" in keys and engine.delay:
        out.append(f"BTS delay statistics cover domestic flights of reporting carriers, arrivals-based, {engine.delay.period_label}. "
                   "'NAS' causes include airport/airspace volume and non-extreme weather flow restrictions (low ceilings, wind); the 'weather' category is extreme weather only.")
    if "ontime" in keys and engine.ontime:
        out.append(f"Route/taxi-out snapshot months: {engine.ontime.period_label}; domestic reporting carriers only (no international, no all-cargo flights).")
    if "ourairports" in keys and engine.reference:
        out.append("Runway counts (open, paved, 5,000 ft or longer) are a physical airfield proxy, not terminal or gate capacity; coordinates and runways come from community-maintained OurAirports data.")
    return out


def _live_events(engine: Engine, codes: Sequence[str]) -> Dict[str, Any]:
    status = engine.nas_status()
    events = status.get("events", {})
    wanted = {}
    for c in codes:
        airport = engine.registry.get(c)
        key = (airport.iata if airport else c) or c
        wanted[key] = events.get(key, [])
    return {"update_time": status.get("update_time"), "retrieved_at": status.get("retrieved_at"), "events": wanted, "error": status.get("error")}


# ------------------------------------------------------------------------ handlers
def resolve_airports(engine: Engine, args: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query is required")
    resolved = engine.registry.resolve(query)
    matches = []
    for lid in resolved["codes"] + resolved["places"]:
        airport = engine.registry.airports.get(lid)
        if airport:
            row = engine.faa.frame[engine.faa.frame["lid"] == lid]
            d = airport.to_dict()
            d["enplanements"] = _clean(row["enplanements"].iloc[0]) if not row.empty else None
            matches.append(d)
    if not matches and not resolved["states"]:
        matches = [a.to_dict() for a in engine.registry.search(query)]
    return {
        "data": {"matches": matches, "states": resolved["states"], "explicit_codes": resolved["codes"], "place_matches": resolved["places"]},
        "sources": engine.sources("faa", "ourairports"), "caveats": [],
        "confidence": {"level": "high" if matches or resolved["states"] else "low"},
        "method": "Exact code match, metro/city alias table, FAA city names, state names and region definitions.",
    }


def rank_airports(engine: Engine, args: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    states = [s.upper() for s in _codes(args.get("states"))]
    region = args.get("region")
    if region:
        region_states = engine.registry.states_for_region(str(region))
        if not region_states:
            found = engine.registry.states_in_text(str(region))
            if not found:
                raise ToolError(f"Unknown region '{region}'. Use two-letter state codes instead.")
            region_states = found
        states = list(dict.fromkeys(states + region_states))
    codes = _codes(args.get("codes"))
    codes = [engine.registry.get(c).lid for c in codes if engine.registry.get(c)]
    min_raw, limit_raw = args.get("min_enplanements"), args.get("limit")
    min_enpl = scoring.DEFAULT_MIN_ENPLANEMENTS if min_raw is None else int(min_raw)
    limit = 10 if limit_raw is None else int(limit_raw)  # 0 = no cap
    if min_enpl < 0 or not (0 <= limit <= 50):
        raise ToolError("min_enplanements must be >= 0 and limit between 0 and 50")
    weights = args.get("weights") or None
    if weights:
        weights = {k: float(v) for k, v in weights.items() if k in scoring.DEFAULT_WEIGHTS}
    result = scoring.expansion_scores(engine.metrics_table(), states or None, codes or None, min_enpl, weights, limit)
    ranked = result["ranked"]
    levels = [x["confidence"] for x in ranked]
    caveats = [SCORE_CAVEAT, "Percentiles are computed nationally across the universe; the state/region filter is applied after scoring."]
    if result.get("excluded_below_floor"):
        caveats.append(f"Not scored because they are below the {min_enpl:,.0f}-enplanement floor of the percentile universe: "
                       f"{', '.join(result['excluded_below_floor'])}. Lower min_enplanements to include them.")
    if any(x.get("data_gaps") or x["missing_components"] for x in ranked):
        caveats.append("Confidence is 'medium' or 'low' where inputs were missing (most often BTS delay coverage for smaller airports, which "
                       "have fewer than 2,000 airline-reported arrivals); those scores use the remaining inputs with weights rebalanced, nothing is estimated.")
    caveats += source_caveats(engine, ["faa", "taf", "delay", "ourairports"])
    scope = {"states": states, "codes": codes, "min_enplanements": min_enpl}
    if session is not None:
        session.remember("rank_airports", {**args, **scope}, [x["lid"] for x in ranked], states)
    return {
        "data": {**result, "scope": scope},
        "sources": engine.sources("faa", "taf", "delay", "ourairports", "slots"),
        "caveats": caveats,
        "confidence": {"level": min(levels, key=["high", "medium", "low"].index) if levels else "low",
                       "distribution": {lvl: levels.count(lvl) for lvl in ("high", "medium", "low")}},
        "method": scoring.METHOD_TEXT,
    }


def _taf_history(engine: Engine, lid: str) -> List[Dict[str, Any]]:
    if engine.taf is None:
        return []
    series = engine.taf.series(lid)
    if series.empty:
        return []
    ff = engine.taf.first_forecast_year
    keep_years = set(range(2015, engine.taf.last_actual_year + 1)) | {ff, ff + 5, ff + 10, ff + 20}
    rows = []
    for r in series.itertuples(index=False):
        if int(r.year) in keep_years:
            rows.append({"year": int(r.year), "kind": "actual" if int(r.scenario) == 0 else "forecast",
                         "enplanements": _clean(r.enpl_total), "international_enplanements": _clean(r.enpl_intl),
                         "air_carrier_ops": _clean(r.ops_air_carrier), "air_taxi_ops": _clean(r.ops_air_taxi), "ga_ops": _clean(r.ops_ga)})
    return rows


def airport_profile(engine: Engine, args: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    code = str(args.get("code", "")).strip()
    airport = engine.registry.get(code)
    if airport is None:
        hits = engine.registry.search(code)
        if not hits:
            raise ToolError(f"Unknown airport '{code}'.")
        airport = hits[0]
    faa_row = engine.faa.frame[engine.faa.frame["lid"] == airport.lid].iloc[0]
    universe = engine.registry.universe()
    rank = int((universe["enplanements"] > faa_row["enplanements"]).sum()) + 1
    row = engine.row(airport.lid)
    in_universe = row is not None
    profile: Dict[str, Any] = {
        "airport": airport.to_dict(),
        "in_scored_universe": in_universe,
        "faa": {"year": engine.faa.latest_year, "preliminary": engine.faa.preliminary, "enplanements": _clean(faa_row["enplanements"]),
                "enplanements_prev": _clean(faa_row["enplanements_prev"]), "yoy_pct": _clean(faa_row["yoy_pct"]),
                "service_level": faa_row["service_level"], "hub_size": faa_row["hub"], "national_rank_by_enplanements": rank},
        "taf_history": _taf_history(engine, airport.lid),
        "live_status": _live_events(engine, [airport.lid]),
    }
    if in_universe:
        r = row
        has_delay = bool(r["has_delay"])
        profile["forecast"] = {"start_year": _clean(r["taf_forecast_start_year"]), "end_year": _clean(r["taf_forecast_end_year"]),
                               "enplanements_end": _clean(r["taf_enpl_forecast_h"]), "cagr_pct": _clean(r["forecast_cagr_pct"]),
                               "recovery_ratio_vs_2019": _clean(r["recovery_ratio"]), "international_share_pct": _clean(r["taf_intl_share_pct"])}
        profile["operations"] = {"year": _clean(r["taf_last_actual_year"]), "air_carrier_plus_air_taxi": _clean(r["ops_last_actual"]),
                                 "peak": _clean(r["ops_peak"]), "peak_year": _clean(r["ops_peak_year"]), "forecast_end_year": _clean(r["ops_forecast_h"]),
                                 "forecast_vs_peak": _clean(r["forecast_vs_peak"]), "ops_per_runway": _clean(r["ops_per_runway"]),
                                 "passengers_per_op_change_since_2019_pct": _clean(r["upgauging_pct"])}
        profile["delays_12m"] = None if not has_delay else {
            "arrivals": _clean(r["arr_flights"]), "delayed_15_pct": _clean(r["del15_pct"]), "cancelled_pct": _clean(r["cancel_pct"]),
            "nas_share_pct": _clean(r["nas_share_pct"]), "weather_share_pct": _clean(r["weather_share_pct"]),
            "carrier_share_pct": _clean(r["carrier_share_pct"]), "late_aircraft_share_pct": _clean(r["late_aircraft_share_pct"]),
            "avg_delay_min_per_delayed": _clean(r["avg_delay_min_per_delayed"])}
        profile["route_snapshot"] = None if not bool(r["has_ontime"]) else {
            "departures": _clean(r["departures"]), "dep_delayed_15_pct": _clean(r["dep_del15_pct"]), "avg_taxi_out_min": _clean(r["avg_taxi_out_min"])}
        scored = scoring.expansion_scores(engine.metrics_table(), codes=[airport.lid], limit=1)["ranked"]
        profile["expansion_score"] = scored[0] if scored else None
    if session is not None:
        session.remember("airport_profile", args, [airport.lid])
    return {
        "data": profile,
        "sources": engine.sources("faa", "taf", "delay", "ontime", "ourairports", "slots"),
        "caveats": source_caveats(engine, ["faa", "taf", "delay", "ontime", "ourairports"]) + [SCORE_CAVEAT],
        "confidence": {"level": "high" if in_universe and not airport.join_gaps else ("medium" if in_universe else "low"), "join_gaps": airport.join_gaps},
        "method": "Direct lookup of FAA, TAF, BTS and OurAirports values for one airport; the expansion score uses the national scoring method.",
    }


def compare_congestion(engine: Engine, args: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    codes = _codes(args.get("codes"))
    if not codes:
        raise ToolError("codes is required")
    lids = [engine.registry.get(c).lid if engine.registry.get(c) else c for c in codes]
    result = congestion.compare_congestion(engine.metrics_table(), lids, engine.nas_status())
    caveats = ["The Congestion Index is a relative national percentile composite; raw metrics are shown so they can be judged directly."]
    caveats += source_caveats(engine, ["delay", "ontime", "taf", "ourairports"])
    if result["not_found"]:
        caveats.append(f"Not in the scored universe (primary/commercial-service, 100k+ enplanements): {', '.join(result['not_found'])}.")
    if session is not None:
        session.remember("compare_congestion", args, [a["lid"] for a in result["airports"]])
    levels = [a["confidence"] for a in result["airports"]]
    return {
        "data": result, "sources": engine.sources("delay", "ontime", "taf", "ourairports", "slots"), "caveats": caveats,
        "confidence": {"level": min(levels, key=["high", "medium", "low"].index) if levels else "low"},
        "method": congestion.METHOD_TEXT,
    }


def long_haul_tool(engine: Engine, args: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    code = str(args.get("code", "")).strip()
    thresholds = [int(t) for t in (args.get("thresholds_mi") or long_haul.DEFAULT_THRESHOLDS_MI)]
    if long_haul.HEADLINE_THRESHOLD_MI not in thresholds:
        thresholds.append(long_haul.HEADLINE_THRESHOLD_MI)
    result = long_haul.long_haul_share(engine.ontime, engine.registry, code, thresholds, engine.row(code))
    if "error" in result and "airport" not in result:
        raise ToolError(result["error"])
    if session is not None and "airport" in result:
        session.remember("long_haul_share", args, [result["airport"]["lid"]])
    return {
        "data": result, "sources": engine.sources("ontime", "taf", "ourairports"),
        "caveats": list(result.get("caveats", [])) + source_caveats(engine, ["ontime", "taf"]),
        "confidence": {"level": "medium" if "error" not in result else "low",
                       "note": "Domestic reporting-carrier departures only; international and cargo flights are missing."},
        "method": long_haul.METHOD_TEXT,
    }


def demand_pressure(engine: Engine, args: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    code = str(args.get("code", "")).strip()
    airport = engine.registry.get(code)
    if airport is None:
        raise ToolError(f"Unknown airport '{code}'.")
    result = demand.demand_pressure(engine.metrics_table(), airport.lid)
    if "error" in result:
        raise ToolError(result["error"])
    result["live_status"] = _live_events(engine, [airport.lid])
    if session is not None:
        session.remember("demand_pressure", args, [airport.lid])
    return {
        "data": result, "sources": engine.sources("taf", "delay", "faa", "ourairports", "slots", "ontime"),
        "caveats": list(result["caveats"]) + source_caveats(engine, ["taf", "delay", "faa"]),
        "confidence": {"level": result["confidence"], "missing_components": result["missing_components"]},
        "method": demand.METHOD_TEXT,
    }


def live_airport_status(engine: Engine, args: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    codes = _codes(args.get("codes"))
    status = engine.nas_status()
    if codes:
        data = _live_events(engine, codes)
    else:
        events = status.get("events", {})
        summary = {}
        for code, items in events.items():
            for e in items:
                summary.setdefault(e["type"], []).append({"airport": code, **e})
        data = {"update_time": status.get("update_time"), "retrieved_at": status.get("retrieved_at"), "by_type": summary,
                "airports_affected": sorted(events.keys()), "error": status.get("error")}
    return {
        "data": data,
        "sources": [{"name": "FAA NAS Status (live)", "url": "https://nasstatus.faa.gov/", "period": "now",
                     "retrieved_at": status.get("retrieved_at"), "vintage": "real-time"}],
        "caveats": ["Live status is a point-in-time operational snapshot; it says nothing about structural capacity and is never used in the scores."],
        "confidence": {"level": "high" if not status.get("error") else "low"},
        "method": "FAA NAS status XML feed parsed into ground delay programs, ground stops, general delays and closures.",
    }


def explain_methodology(engine: Engine, args: Dict[str, Any], session: Optional[Session]) -> Dict[str, Any]:
    topic = str(args.get("topic", "expansion_score"))
    texts = {
        "expansion_score": {"text": scoring.METHOD_TEXT, "weights": scoring.DEFAULT_WEIGHTS, "min_enplanements": scoring.DEFAULT_MIN_ENPLANEMENTS},
        "congestion_index": {"text": congestion.METHOD_TEXT, "weights": congestion.WEIGHTS},
        "long_haul_share": {"text": long_haul.METHOD_TEXT, "caveats": long_haul.CAVEATS},
        "unmet_demand": {"text": demand.METHOD_TEXT, "caveats": demand.CAVEATS},
        "data_sources": {"sources": engine.sources("faa", "taf", "delay", "ontime", "ourairports", "slots"), "status": engine.source_status},
        "limitations": {"text": GAP_STATEMENT, "source_caveats": source_caveats(engine, ["faa", "taf", "delay", "ontime", "ourairports"])},
        "confidence": {"text": "Confidence is 'high' when every score component and every data join is available, 'medium' when one component is missing, "
                               "and 'low' when two or more are missing or the airport is outside the scored universe. Missing components are never imputed; "
                               "weights are renormalized over the available ones.", "min_arrivals_for_delay_metrics": 2000},
    }
    if topic not in texts:
        raise ToolError(f"Unknown topic '{topic}'. Choose one of: {', '.join(TOPICS)}")
    return {"data": {"topic": topic, **texts[topic]}, "sources": engine.sources("faa", "taf", "delay", "ontime", "ourairports", "slots"),
            "caveats": [], "confidence": {"level": "high"}, "method": "Static methodology text from the scoring modules."}


HANDLERS = {
    "resolve_airports": resolve_airports,
    "rank_airports": rank_airports,
    "airport_profile": airport_profile,
    "compare_congestion": compare_congestion,
    "long_haul_share": long_haul_tool,
    "demand_pressure": demand_pressure,
    "live_airport_status": live_airport_status,
    "explain_methodology": explain_methodology,
}


def dispatch(engine: Engine, name: str, arguments: Optional[Dict[str, Any]], session: Optional[Session] = None) -> Dict[str, Any]:
    args = dict(arguments or {})
    try:
        if name not in HANDLERS:
            raise ToolError(f"Unknown tool '{name}'")
        result = HANDLERS[name](engine, args, session)
    except ToolError as exc:
        return {"tool": name, "arguments": args, "error": str(exc), "data": {}, "sources": [], "caveats": [], "confidence": {"level": "low"}, "method": ""}
    return {"tool": name, "arguments": args, **result}
