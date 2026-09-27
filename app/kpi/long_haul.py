"""Long-haul share of departures for one origin airport (BTS on-time snapshot)."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import pandas as pd

from app.model.airports import AirportRegistry
from app.sources.bts_ontime import OnTimeSnapshot

DEFAULT_THRESHOLDS_MI: Sequence[int] = (1500, 2500, 3000)
HEADLINE_THRESHOLD_MI = 3000
METHOD_TEXT = (
    "Long-haul share = scheduled departures on routes whose great-circle stage length is at or above the threshold, "
    "divided by all scheduled departures from the airport in the snapshot months (departure-count weighted, not "
    "seat weighted). Headline threshold 3,000 statute miles; 1,500 and 2,500 mile shares are shown for sensitivity. "
    "Source rows are BTS on-time records: domestic flights of US carriers above the DOT reporting threshold only."
)
CAVEATS = [
    "Covers domestic scheduled passenger flights of BTS reporting carriers only: international flights, all-cargo "
    "operations and small regional/intrastate operators are NOT included, so the true long-haul share (especially "
    "for a cargo gateway like Anchorage) is understated.",
    "Departure counts, not seats or passengers; wide-body long-haul flights carry more passengers per departure.",
    "Distance is the BTS great-circle stage length in statute miles between origin and destination airports.",
]


def _clean(value: object) -> Optional[float]:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def long_haul_share(
    ontime: Optional[OnTimeSnapshot],
    registry: AirportRegistry,
    code: str,
    thresholds_mi: Sequence[int] = DEFAULT_THRESHOLDS_MI,
    taf_row: Optional[pd.Series] = None,
    top_n: int = 10,
) -> Dict[str, object]:
    airport = registry.get(code)
    if airport is None:
        return {"error": f"Unknown airport '{code}'"}
    if ontime is None:
        return {"error": "No BTS on-time route snapshot is available (run scripts/refresh_data.py --ontime YYYY-MM)."}
    iata = airport.iata or airport.lid
    routes = ontime.routes[ontime.routes["origin"] == iata]
    if routes.empty:
        return {"airport": airport.to_dict(), "error": f"No reporting-carrier departures from {iata} in the snapshot months ({ontime.period_label})."}
    agg = routes.groupby("dest", as_index=False).agg(departures=("departures", "sum"), cancelled=("cancelled", "sum"), distance_mi=("distance_mi", "max"))
    total = float(agg["departures"].sum())
    shares = {}
    for t in sorted(thresholds_mi):
        long = float(agg.loc[agg["distance_mi"] >= t, "departures"].sum())
        shares[str(t)] = {"threshold_mi": t, "departures": long, "share_pct": round(long / total * 100, 1) if total else None}
    top = agg.sort_values("departures", ascending=False).head(top_n)
    top_routes = []
    for r in top.itertuples(index=False):
        dest = registry.get(r.dest)
        top_routes.append({"dest": r.dest, "dest_name": dest.name if dest else None, "dest_city": dest.city if dest else None,
                           "departures": int(r.departures), "distance_mi": _clean(r.distance_mi),
                           "long_haul_3000": bool(r.distance_mi >= HEADLINE_THRESHOLD_MI)})
    longest = agg.sort_values("distance_mi", ascending=False).head(5)
    longest_routes = [{"dest": r.dest, "departures": int(r.departures), "distance_mi": _clean(r.distance_mi)} for r in longest.itertuples(index=False)]
    weighted_avg = float((agg["departures"] * agg["distance_mi"]).sum() / total) if total else None
    result: Dict[str, object] = {
        "airport": airport.to_dict(),
        "months": ontime.months,
        "total_departures": total,
        "destinations": int(len(agg)),
        "headline_threshold_mi": HEADLINE_THRESHOLD_MI,
        "headline_share_pct": shares[str(HEADLINE_THRESHOLD_MI)]["share_pct"] if str(HEADLINE_THRESHOLD_MI) in shares else None,
        "shares_by_threshold": shares,
        "avg_stage_length_mi": round(weighted_avg, 0) if weighted_avg else None,
        "top_routes": top_routes,
        "longest_routes": longest_routes,
        "method": METHOD_TEXT,
        "caveats": list(CAVEATS),
    }
    if taf_row is not None:
        result["taf_context"] = {
            "year": int(taf_row["taf_last_actual_year"]) if not pd.isna(taf_row.get("taf_last_actual_year")) else None,
            "international_enplanement_share_pct": _clean(taf_row.get("taf_intl_share_pct")),
            "enplanements_taf": _clean(taf_row.get("taf_enpl_last_actual")),
            "air_carrier_plus_air_taxi_ops": _clean(taf_row.get("ops_last_actual")),
            "note": "TAF international share counts passengers boarding international flights (all carriers); "
                    "it is a complementary indicator because international flights are missing from the BTS on-time rows.",
        }
    return result
