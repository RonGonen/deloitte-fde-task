"""Unmet Demand Indicator for one airport: is demand pressing against binding capacity?

There is no public seat or load-factor feed in this build (BTS T-100 is not scriptable), so
unserved passengers cannot be counted. The indicator instead combines the FAA's unconstrained
forecast against demonstrated throughput with observed congestion and structural constraints,
and explains each driver so the reader can judge it.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import pandas as pd

from app.kpi.normalize import confidence_level, mean_available, normalized_signal
from app.kpi.scoring import SLOT_SCORE

COMPONENTS = {
    "forecast_vs_peak": ("FAA forecast operations vs demonstrated peak annual operations", True),
    "del15_pct": ("Arrivals delayed 15+ min (%) trailing 12 months", True),
    "nas_share_pct": ("Share of delays attributed to NAS/airport capacity & weather", True),
    "slot": ("FAA slot control / schedule facilitation status", True),
    "recovery_gap": ("Enplanements still below 2019 (latent demand not yet re-accommodated)", False),
    "upgauging_pct": ("Passengers per operation growth since 2019 (airlines up-gauging instead of adding flights)", True),
}
METHOD_TEXT = (
    "Unmet Demand Indicator = mean of national percentiles (0-100) of six pressure signals: FAA TAF forecast "
    "air-carrier operations 10 years out relative to the airport's highest annual operations since 1990; share of "
    "arrivals delayed 15+ minutes; share of delayed arrivals attributed to the National Airspace System; FAA slot "
    "status (Level 3 = 100, Level 2 = 50, none = 0); the inverse of the enplanement recovery ratio vs 2019; and growth "
    "in passengers per operation since 2019 (up-gauging is how constrained airports absorb demand). It is an indicator "
    "of demand pressing on capacity, not a count of unserved passengers or a load factor."
)
CAVEATS = [
    "No seat, load-factor or fare data is available in this build (BTS T-100 could not be pulled), so unserved "
    "passengers cannot be counted; the indicator measures pressure, not a passenger gap.",
    "'Demonstrated peak operations' is the highest annual air-carrier + air-taxi operations recorded since 1990, not an "
    "engineered runway capacity; fleet mix and procedures have changed since that year.",
    "The FAA TAF forecast is unconstrained (it assumes capacity will be provided).",
    "Delay statistics include weather-driven delays; the weather share is shown so it can be separated from structural congestion.",
]


def _clean(value: object) -> Optional[float]:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def demand_pressure(table: pd.DataFrame, code: str, min_enplanements: float = 100_000) -> Dict[str, object]:
    universe = table[table["enplanements"] >= min_enplanements].copy()
    code_u = code.upper()
    hit = universe[(universe["lid"] == code_u) | (universe["iata"] == code_u)]
    if hit.empty:
        return {"error": f"{code_u} is not in the scored universe (primary/commercial-service airports with at least {min_enplanements:,.0f} enplanements)."}
    idx = hit.index[0]
    ok = universe["has_delay"].astype(bool)
    pct = {
        "forecast_vs_peak": normalized_signal(universe["forecast_vs_peak"]),
        "del15_pct": normalized_signal(universe["del15_pct"].where(ok)),
        "nas_share_pct": normalized_signal(universe["nas_share_pct"].where(ok)),
        "slot": universe["slot_level"].map(SLOT_SCORE).astype(float),
        "recovery_gap": normalized_signal(universe["recovery_ratio"], higher_is_better=False),
        "upgauging_pct": normalized_signal(universe["upgauging_pct"]),
    }
    r = universe.loc[idx]
    percentiles = {k: _clean(v.loc[idx]) for k, v in pct.items()}
    if not bool(r["has_delay"]):
        percentiles["del15_pct"] = None
        percentiles["nas_share_pct"] = None
    missing = [k for k, v in percentiles.items() if v is None]
    indicator = mean_available(list(percentiles.values()))
    medians = {
        "del15_pct": _clean(universe.loc[ok, "del15_pct"].median()),
        "nas_share_pct": _clean(universe.loc[ok, "nas_share_pct"].median()),
        "weather_share_pct": _clean(universe.loc[ok, "weather_share_pct"].median()),
        "cancel_pct": _clean(universe.loc[ok, "cancel_pct"].median()),
        "forecast_vs_peak": _clean(universe["forecast_vs_peak"].median()),
        "recovery_ratio": _clean(universe["recovery_ratio"].median()),
        "upgauging_pct": _clean(universe["upgauging_pct"].median()),
        "forecast_cagr_pct": _clean(universe["forecast_cagr_pct"].median()),
    }
    facts = {
        "enplanements_faa": _clean(r["enplanements"]), "yoy_pct": _clean(r["yoy_pct"]),
        "taf_last_actual_year": _clean(r["taf_last_actual_year"]), "taf_enpl_last_actual": _clean(r["taf_enpl_last_actual"]),
        "taf_enpl_2019": _clean(r["taf_enpl_2019"]), "recovery_ratio": _clean(r["recovery_ratio"]),
        "taf_forecast_end_year": _clean(r["taf_forecast_end_year"]), "taf_enpl_forecast_h": _clean(r["taf_enpl_forecast_h"]),
        "forecast_cagr_pct": _clean(r["forecast_cagr_pct"]),
        "ops_last_actual": _clean(r["ops_last_actual"]), "ops_peak": _clean(r["ops_peak"]), "ops_peak_year": _clean(r["ops_peak_year"]),
        "ops_forecast_h": _clean(r["ops_forecast_h"]), "forecast_vs_peak": _clean(r["forecast_vs_peak"]),
        "forecast_vs_current_ops": _clean(r["forecast_vs_current_ops"]),
        "runways_qualifying": _clean(r["runways_qualifying"]), "ops_per_runway": _clean(r["ops_per_runway"]),
        "slot_level": int(r["slot_level"]),
        "del15_pct": _clean(r["del15_pct"]) if bool(r["has_delay"]) else None,
        "nas_share_pct": _clean(r["nas_share_pct"]) if bool(r["has_delay"]) else None,
        "weather_share_pct": _clean(r["weather_share_pct"]) if bool(r["has_delay"]) else None,
        "carrier_share_pct": _clean(r["carrier_share_pct"]) if bool(r["has_delay"]) else None,
        "late_aircraft_share_pct": _clean(r["late_aircraft_share_pct"]) if bool(r["has_delay"]) else None,
        "cancel_pct": _clean(r["cancel_pct"]) if bool(r["has_delay"]) else None,
        "avg_delay_min_per_delayed": _clean(r["avg_delay_min_per_delayed"]) if bool(r["has_delay"]) else None,
        "avg_taxi_out_min": _clean(r["avg_taxi_out_min"]),
        "pax_per_op_2019": _clean(r["pax_per_op_2019"]), "pax_per_op_last": _clean(r["pax_per_op_last"]), "upgauging_pct": _clean(r["upgauging_pct"]),
        "taf_intl_share_pct": _clean(r["taf_intl_share_pct"]),
    }
    reasons = _reasons(facts, medians)
    return {
        "airport": {"lid": r["lid"], "iata": r["iata"], "name": r["name"], "city": r["city"], "state": r["state"]},
        "indicator": round(indicator, 1) if indicator is not None else None,
        "component_percentiles": {k: (round(v, 1) if v is not None else None) for k, v in percentiles.items()},
        "component_labels": {k: v[0] for k, v in COMPONENTS.items()},
        "missing_components": missing,
        "confidence": confidence_level(missing, [], len(COMPONENTS)),
        "facts": facts,
        "national_medians": medians,
        "reasons": reasons,
        "method": METHOD_TEXT,
        "caveats": list(CAVEATS),
        "universe_size": int(len(universe)),
    }


def _reasons(f: Dict[str, Optional[float]], m: Dict[str, Optional[float]]) -> List[str]:
    out: List[str] = []
    if f["slot_level"] == 3:
        out.append("FAA Level 3 slot-controlled airport: runway slots are capped by regulation, so airlines cannot add flights freely.")
    elif f["slot_level"] == 2:
        out.append("FAA Level 2 schedule-facilitated airport: the FAA formally reviews airline schedules because runway capacity is constrained.")
    if f["forecast_vs_peak"] is not None and f["ops_peak_year"] is not None:
        pct = (f["forecast_vs_peak"] - 1) * 100
        if f["forecast_vs_peak"] >= 1.0:
            out.append(f"FAA forecasts {int(f['taf_forecast_end_year'])} air-carrier operations {pct:.0f}% above the airport's highest-ever annual operations ({int(f['ops_peak_year'])}), i.e. demand is forecast to exceed anything the airfield has demonstrated.")
        else:
            out.append(f"FAA forecasts {int(f['taf_forecast_end_year'])} operations at {f['forecast_vs_peak']*100:.0f}% of the airport's demonstrated peak ({int(f['ops_peak_year'])}), leaving airfield headroom on this measure.")
    if f["del15_pct"] is not None and m["del15_pct"] is not None:
        rel = "above" if f["del15_pct"] > m["del15_pct"] else "below"
        out.append(f"{f['del15_pct']:.1f}% of arrivals were delayed 15+ minutes over the trailing 12 months, {rel} the national median of {m['del15_pct']:.1f}%.")
    if f["nas_share_pct"] is not None and m["nas_share_pct"] is not None:
        rel = "above" if f["nas_share_pct"] > m["nas_share_pct"] else "below"
        weather = f" (weather itself accounts for {f['weather_share_pct']:.1f}% of delays)" if f.get("weather_share_pct") is not None else ""
        out.append(f"{f['nas_share_pct']:.1f}% of delayed arrivals were attributed to the National Airspace System (airport/airspace capacity and weather-driven flow restrictions), {rel} the national median of {m['nas_share_pct']:.1f}%{weather}.")
    if f["upgauging_pct"] is not None and m["upgauging_pct"] is not None:
        rel = "more" if f["upgauging_pct"] > m["upgauging_pct"] else "less"
        out.append(f"Passengers per operation changed {f['upgauging_pct']:+.1f}% since 2019 ({rel} up-gauging than the national median of {m['upgauging_pct']:+.1f}%); up-gauging is how airlines grow at airports where they cannot add flights.")
    if f["recovery_ratio"] is not None:
        if f["recovery_ratio"] < 1.0:
            out.append(f"Enplanements are still at {f['recovery_ratio']*100:.0f}% of 2019, so part of pre-pandemic demand has not yet been re-accommodated.")
        else:
            out.append(f"Enplanements have recovered to {f['recovery_ratio']*100:.0f}% of 2019 levels.")
    if f["runways_qualifying"] is not None:
        out.append(f"{int(f['runways_qualifying'])} open paved runways of 5,000 ft or more; {f['ops_per_runway']:,.0f} annual air-carrier/air-taxi operations per runway." if f["ops_per_runway"] else f"{int(f['runways_qualifying'])} qualifying runways.")
    return out
