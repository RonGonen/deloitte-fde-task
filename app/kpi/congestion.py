"""Congestion Index and side-by-side congestion metrics for airport comparisons."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import pandas as pd

from app.kpi.normalize import confidence_level, normalized_signal, weighted_score

WEIGHTS: Dict[str, float] = {"del15_pct": 0.35, "nas_share_pct": 0.20, "cancel_pct": 0.15, "avg_taxi_out_min": 0.15, "ops_per_runway": 0.15}
LABELS = {
    "del15_pct": "Arrivals delayed 15+ min (%)",
    "nas_share_pct": "Share of delays attributed to NAS/airport capacity & weather (%)",
    "cancel_pct": "Arrivals cancelled (%)",
    "avg_taxi_out_min": "Average taxi-out time (min)",
    "ops_per_runway": "Air-carrier + air-taxi operations per qualifying runway (annual)",
}
METHOD_TEXT = (
    "Congestion Index = 0.35 x arrivals delayed 15+ minutes (%) + 0.20 x share of delayed arrivals attributed to the "
    "National Airspace System + 0.15 x cancellation rate + 0.15 x average taxi-out minutes + 0.15 x annual air-carrier "
    "and air-taxi operations per qualifying runway. Each input is converted to a national percentile (0-100) across "
    "primary/commercial-service airports with 100k+ enplanements before weighting, so 100 means the most congested "
    "airport in the country on that input. Live FAA NAS status is shown alongside but never scored."
)


def _clean(value: object) -> Optional[float]:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def congestion_table(table: pd.DataFrame, min_enplanements: float = 100_000) -> pd.DataFrame:
    universe = table[table["enplanements"] >= min_enplanements].copy()
    ok = universe["has_delay"].astype(bool)
    pct = pd.DataFrame(index=universe.index)
    pct["del15_pct"] = normalized_signal(universe["del15_pct"].where(ok))
    pct["nas_share_pct"] = normalized_signal(universe["nas_share_pct"].where(ok))
    pct["cancel_pct"] = normalized_signal(universe["cancel_pct"].where(ok))
    pct["avg_taxi_out_min"] = normalized_signal(universe["avg_taxi_out_min"])
    pct["ops_per_runway"] = normalized_signal(universe["ops_per_runway"])
    universe = universe.join(pct.add_suffix("_pctl"))
    return universe


def compare_congestion(table: pd.DataFrame, codes: Sequence[str], nas_status: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    universe = congestion_table(table)
    medians = {k: _clean(universe.loc[universe["has_delay"].astype(bool), k].median()) if k in ("del15_pct", "nas_share_pct", "cancel_pct")
               else _clean(universe[k].median()) for k in WEIGHTS}
    airports: List[Dict[str, object]] = []
    not_found: List[str] = []
    events = (nas_status or {}).get("events", {}) if nas_status else {}
    for code in codes:
        code_u = code.upper()
        hit = universe[(universe["lid"] == code_u) | (universe["iata"] == code_u)]
        if hit.empty:
            not_found.append(code_u)
            continue
        r = hit.iloc[0]
        has_delay = bool(r["has_delay"])
        comps = {}
        for k, w in WEIGHTS.items():
            value = _clean(r[f"{k}_pctl"])
            if k in ("del15_pct", "nas_share_pct", "cancel_pct") and not has_delay:
                value = None
            comps[k] = (value, w)
        idx = weighted_score(comps)
        airports.append({
            "lid": r["lid"], "iata": r["iata"], "name": r["name"], "city": r["city"], "state": r["state"],
            "congestion_index": idx["score"], "weights_used": idx["weights_used"], "missing_components": idx["missing"],
            "confidence": confidence_level(idx["missing"], [], len(WEIGHTS)),
            "metrics": {
                "arr_flights_12m": _clean(r["arr_flights"]),
                "del15_pct": _clean(r["del15_pct"]) if has_delay else None,
                "nas_share_pct": _clean(r["nas_share_pct"]) if has_delay else None,
                "weather_share_pct": _clean(r["weather_share_pct"]) if has_delay else None,
                "carrier_share_pct": _clean(r["carrier_share_pct"]) if has_delay else None,
                "late_aircraft_share_pct": _clean(r["late_aircraft_share_pct"]) if has_delay else None,
                "cancel_pct": _clean(r["cancel_pct"]) if has_delay else None,
                "avg_delay_min_per_delayed": _clean(r["avg_delay_min_per_delayed"]) if has_delay else None,
                "avg_taxi_out_min": _clean(r["avg_taxi_out_min"]),
                "dep_del15_pct": _clean(r["dep_del15_pct"]),
                "departures_snapshot": _clean(r["departures"]),
                "ops_last_actual": _clean(r["ops_last_actual"]),
                "runways_qualifying": _clean(r["runways_qualifying"]),
                "ops_per_runway": _clean(r["ops_per_runway"]),
                "slot_level": int(r["slot_level"]),
                "enplanements": _clean(r["enplanements"]),
            },
            "percentiles": {k: _clean(r[f"{k}_pctl"]) for k in WEIGHTS},
            "live_status": events.get(r["iata"], []) if events else [],
        })
    airports.sort(key=lambda a: -(a["congestion_index"] if a["congestion_index"] is not None else -1))
    return {
        "airports": airports, "not_found": not_found, "national_medians": medians, "labels": LABELS, "weights": WEIGHTS,
        "method": METHOD_TEXT, "live_status_update_time": (nas_status or {}).get("update_time"),
    }
