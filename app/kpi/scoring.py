"""Expansion Opportunity Score: where demand growth and binding capacity coincide.

Deterministic. Every component is a national percentile (0-100) across FAA primary and
commercial-service airports above a volume floor. Region filters are applied *after*
scoring so a small peer set does not degenerate into 0/50/100 ranks.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from app.kpi.normalize import confidence_level, mean_available, normalized_signal, weighted_score

DEFAULT_WEIGHTS: Dict[str, float] = {"forecast_growth": 0.30, "demand_momentum": 0.20, "capacity_pressure": 0.30, "scale": 0.20}
DEFAULT_MIN_ENPLANEMENTS = 100_000
SLOT_SCORE = {3: 100.0, 2: 50.0, 0: 0.0}

COMPONENT_LABELS = {
    "forecast_growth": "FAA TAF forecast growth (10-yr enplanement CAGR)",
    "demand_momentum": "Recent demand momentum (FAA YoY + TAF last actual growth)",
    "capacity_pressure": "Capacity pressure (structural constraints + observed delays)",
    "scale": "Scale (log annual enplanements)",
}

METHOD_TEXT = (
    "Expansion Opportunity Score = weighted sum of four national-percentile components: "
    "forecast growth (TAF 10-year enplanement CAGR), demand momentum (FAA year-over-year growth blended 50/50 with "
    "the latest TAF actual growth), capacity pressure (half structural: air-carrier operations per qualifying runway, "
    "FAA slot/schedule-facilitation status, forecast operations vs the airport's demonstrated peak; half observed: "
    "share of arrivals delayed 15+ minutes, share of delays attributed to the National Airspace System, cancellation "
    "rate over the trailing 12 months), and scale (log10 enplanements). Raw signals are winsorized at the 5th/95th "
    "percentile before ranking. Missing components are dropped and weights renormalized; confidence is lowered."
)


def _component_frame(universe: pd.DataFrame) -> pd.DataFrame:
    comp = pd.DataFrame(index=universe.index)
    comp["forecast_growth"] = normalized_signal(universe["forecast_cagr_pct"])
    yoy = normalized_signal(universe["yoy_pct"])
    taf_growth = normalized_signal(universe["taf_growth_last_actual_pct"])
    comp["demand_momentum"] = pd.concat([yoy, taf_growth], axis=1).mean(axis=1, skipna=True)

    structural_parts = pd.concat([
        normalized_signal(universe["ops_per_runway"]),
        universe["slot_level"].map(SLOT_SCORE).astype(float),
        normalized_signal(universe["forecast_vs_peak"]),
    ], axis=1)
    comp["structural_pressure"] = structural_parts.mean(axis=1, skipna=True)
    observed_ok = universe["has_delay"].astype(bool)
    observed_parts = pd.concat([
        normalized_signal(universe["del15_pct"].where(observed_ok)),
        normalized_signal(universe["nas_share_pct"].where(observed_ok)),
        normalized_signal(universe["cancel_pct"].where(observed_ok)),
    ], axis=1)
    comp["observed_pressure"] = observed_parts.mean(axis=1, skipna=True)
    comp["capacity_pressure"] = comp[["structural_pressure", "observed_pressure"]].mean(axis=1, skipna=True)
    comp["scale"] = normalized_signal(universe["log_enplanements"])
    return comp


def _clean(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _drivers(sub_scores: Dict[str, Optional[float]], weights_used: Dict[str, float]) -> List[Dict[str, object]]:
    contributions = []
    for name, score in sub_scores.items():
        if score is None or name not in weights_used:
            continue
        contributions.append({"component": name, "label": COMPONENT_LABELS[name], "percentile": round(score, 1),
                              "contribution": round((score - 50.0) * weights_used[name], 1)})
    contributions.sort(key=lambda c: -abs(float(c["contribution"])))
    return contributions[:3]


def expansion_scores(
    table: pd.DataFrame,
    states: Optional[Sequence[str]] = None,
    codes: Optional[Sequence[str]] = None,
    min_enplanements: float = DEFAULT_MIN_ENPLANEMENTS,
    weights: Optional[Dict[str, float]] = None,
    limit: int = 10,
) -> Dict[str, object]:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    universe = table[table["enplanements"] >= min_enplanements].copy()
    if universe.empty:
        return {"ranked": [], "universe_size": 0, "weights": weights, "min_enplanements": min_enplanements,
                "message": f"No primary/commercial-service airports with at least {min_enplanements:,.0f} annual enplanements."}
    comp = _component_frame(universe)

    rows: List[Dict[str, object]] = []
    for idx, r in universe.iterrows():
        subs = {k: _clean(comp.at[idx, k]) for k in DEFAULT_WEIGHTS}
        result = weighted_score({k: (subs[k], weights[k]) for k in DEFAULT_WEIGHTS})
        no_scale = weighted_score({k: (subs[k], 0.0 if k == "scale" else weights[k]) for k in DEFAULT_WEIGHTS})
        missing = list(result["missing"])
        gaps = int(r["join_gaps"]) if not pd.isna(r["join_gaps"]) else 0
        rows.append({
            "lid": r["lid"], "iata": r["iata"], "name": r["name"], "city": r["city"], "state": r["state"], "hub": r["hub"],
            "score": result["score"], "score_without_scale": no_scale["score"],
            "sub_scores": {k: (round(v, 1) if v is not None else None) for k, v in subs.items()},
            "structural_pressure": _clean(comp.at[idx, "structural_pressure"]),
            "observed_pressure": _clean(comp.at[idx, "observed_pressure"]),
            "weights_used": result["weights_used"],
            "drivers": _drivers(subs, result["weights_used"]),
            "confidence": confidence_level(missing, ["join gap"] * gaps, len(DEFAULT_WEIGHTS)),
            "missing_components": missing,
            "metrics": {
                "enplanements": _clean(r["enplanements"]), "yoy_pct": _clean(r["yoy_pct"]),
                "taf_growth_last_actual_pct": _clean(r["taf_growth_last_actual_pct"]), "forecast_cagr_pct": _clean(r["forecast_cagr_pct"]),
                "taf_enpl_forecast_h": _clean(r["taf_enpl_forecast_h"]), "recovery_ratio": _clean(r["recovery_ratio"]),
                "ops_per_runway": _clean(r["ops_per_runway"]), "runways_qualifying": _clean(r["runways_qualifying"]),
                "slot_level": int(r["slot_level"]), "forecast_vs_peak": _clean(r["forecast_vs_peak"]),
                "del15_pct": _clean(r["del15_pct"]) if bool(r["has_delay"]) else None,
                "nas_share_pct": _clean(r["nas_share_pct"]) if bool(r["has_delay"]) else None,
                "weather_share_pct": _clean(r["weather_share_pct"]) if bool(r["has_delay"]) else None,
                "cancel_pct": _clean(r["cancel_pct"]) if bool(r["has_delay"]) else None,
                "arr_flights": _clean(r["arr_flights"]),
            },
        })

    selected = rows
    if codes:
        wanted = {c.upper() for c in codes}
        selected = [x for x in selected if x["lid"] in wanted or (x["iata"] or "") in wanted]
    if states:
        wanted_states = {s.upper() for s in states}
        selected = [x for x in selected if x["state"] in wanted_states]
    selected.sort(key=lambda x: (-(x["score"] if x["score"] is not None else -1), x["lid"]))
    for i, x in enumerate(selected, start=1):
        x["rank"] = i
    return {
        "ranked": selected[:limit] if limit else selected,
        "candidates_in_filter": len(selected),
        "universe_size": int(len(universe)),
        "min_enplanements": min_enplanements,
        "weights": weights,
        "method": METHOD_TEXT,
        "normalization": "national percentiles across the universe; region/code filters applied after scoring",
    }
