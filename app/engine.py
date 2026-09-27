"""Data engine: loads every source once and assembles one metrics table per airport.

The table is the single input to all deterministic KPIs, so every number the agent
reports can be traced to a column here and, from there, to a named public source.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from app.kpi.normalize import pct_change, safe_ratio
from app.model.airports import AirportRegistry
from app.sources.bts_delay_cause import NUMERIC_COLUMNS, DelayCause, load_delay_cause
from app.sources.bts_ontime import OnTimeSnapshot, load_ontime_snapshot
from app.sources.cache import SourceUnavailable
from app.sources.faa_enplanements import FaaEnplanements, load_faa_enplanements
from app.sources.nas_status import load_nas_status
from app.sources.ourairports import AirportReference, load_airport_reference
from app.sources.taf import Taf, load_taf

log = logging.getLogger(__name__)

FORECAST_HORIZON_YEARS = 10
MIN_ARRIVALS_FOR_DELAY_METRICS = 2000
RECOVERY_BASE_YEAR = 2019


class Engine:
    def __init__(
        self,
        faa: FaaEnplanements,
        reference: Optional[AirportReference] = None,
        taf: Optional[Taf] = None,
        delay: Optional[DelayCause] = None,
        ontime: Optional[OnTimeSnapshot] = None,
        nas_loader: Optional[Callable[[], Dict[str, object]]] = None,
        source_status: Optional[Dict[str, Dict[str, object]]] = None,
    ) -> None:
        self.faa = faa
        self.reference = reference
        self.taf = taf
        self.delay = delay
        self.ontime = ontime
        self._nas_loader = nas_loader
        self.source_status: Dict[str, Dict[str, object]] = source_status or {}
        self.registry = AirportRegistry(faa.frame, reference, taf.frame if taf else None)
        self._table: Optional[pd.DataFrame] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls) -> "Engine":
        status: Dict[str, Dict[str, object]] = {}
        t0 = time.time()
        faa = load_faa_enplanements()
        status["faa_enplanements"] = {"ok": True, "notes": faa.notes, **faa.source()}

        def attempt(name: str, loader: Callable[[], object]) -> Optional[object]:
            try:
                value = loader()
                if value is None:
                    status[name] = {"ok": False, "error": "no snapshot available"}
                    return None
                status[name] = {"ok": True, "notes": getattr(value, "notes", []), **value.source()}
                return value
            except (SourceUnavailable, Exception) as exc:  # noqa: BLE001 - degrade gracefully per source
                log.warning("source %s unavailable: %s", name, exc)
                status[name] = {"ok": False, "error": str(exc)}
                return None

        reference = attempt("ourairports", load_airport_reference)
        taf = attempt("taf", lambda: load_taf(set(faa.frame.loc[faa.frame["service_level"].isin(["P", "CS"]), "lid"])))
        delay = attempt("bts_delay_cause", load_delay_cause)
        ontime = attempt("bts_ontime", load_ontime_snapshot)
        status["load_seconds"] = {"ok": True, "seconds": round(time.time() - t0, 1)}
        return cls(faa, reference, taf, delay, ontime, load_nas_status, status)

    # ---------------------------------------------------------------- helpers
    def nas_status(self) -> Dict[str, object]:
        if self._nas_loader is None:
            return {"update_time": "", "events": {}, "error": "live status disabled", "retrieved_at": None}
        try:
            return self._nas_loader()
        except Exception as exc:  # noqa: BLE001
            return {"update_time": "", "events": {}, "error": str(exc), "retrieved_at": None}

    def sources(self, *keys: str) -> List[Dict[str, object]]:
        mapping = {
            "faa": self.faa.source(),
            "taf": self.taf.source() if self.taf else None,
            "delay": self.delay.source() if self.delay else None,
            "ontime": self.ontime.source() if self.ontime else None,
            "ourairports": self.reference.source() if self.reference else None,
            "slots": {"name": "FAA Slot Administration", **self.registry.slot_reference["source"], "period": "current",
                      "retrieved_at": self.registry.slot_reference["source"].get("verified_on"),
                      "vintage": "page last updated " + str(self.registry.slot_reference["source"].get("page_last_updated"))},
        }
        return [mapping[k] for k in keys if mapping.get(k)]

    # ------------------------------------------------------------ metrics table
    def metrics_table(self) -> pd.DataFrame:
        with self._lock:
            if self._table is None:
                self._table = self._build_table()
            return self._table

    def _build_table(self) -> pd.DataFrame:
        base = self.registry.universe().set_index("lid")
        reg = self.registry.airports
        base["iata"] = [reg[l].iata for l in base.index]
        base["icao"] = [reg[l].icao for l in base.index]
        base["slot_level"] = [reg[l].slot_level for l in base.index]
        base["runways_qualifying"] = [reg[l].runways_qualifying for l in base.index]
        base["oep35"] = [reg[l].oep35 for l in base.index]
        base["latitude"] = [reg[l].latitude for l in base.index]
        base["longitude"] = [reg[l].longitude for l in base.index]
        base["join_gaps"] = [len(reg[l].join_gaps) for l in base.index]
        base["log_enplanements"] = np.log10(base["enplanements"].clip(lower=1))

        self._add_taf(base)
        self._add_delay(base)
        self._add_ontime(base)

        base["has_taf"] = base["taf_enpl_last_actual"].notna() if "taf_enpl_last_actual" in base else False
        base["has_delay"] = base["arr_flights"].fillna(0) >= MIN_ARRIVALS_FOR_DELAY_METRICS if "arr_flights" in base else False
        base["has_ontime"] = base["departures"].fillna(0) > 0 if "departures" in base else False
        base["has_runways"] = base["runways_qualifying"].fillna(0) > 0
        return base.reset_index()

    def _add_taf(self, base: pd.DataFrame) -> None:
        cols = ["taf_enpl_last_actual", "taf_enpl_prev_actual", "taf_growth_last_actual_pct", "taf_enpl_2019", "recovery_ratio",
                "taf_intl_share_pct", "ops_last_actual", "ops_2019", "ops_peak", "ops_peak_year", "ops_forecast_h",
                "forecast_vs_peak", "forecast_vs_current_ops", "ops_per_runway", "taf_enpl_forecast_start", "taf_enpl_forecast_h",
                "forecast_cagr_pct", "pax_per_op_last", "pax_per_op_2019", "upgauging_pct", "taf_last_actual_year",
                "taf_forecast_start_year", "taf_forecast_end_year"]
        for c in cols:
            base[c] = np.nan
        if self.taf is None:
            return
        taf = self.taf.frame.copy()
        for c in ("ops_air_carrier", "ops_air_taxi", "enpl_total", "enpl_intl"):
            taf[c] = taf[c].fillna(0.0)
        taf["ops_ac_at"] = taf["ops_air_carrier"] + taf["ops_air_taxi"]
        actual = taf[taf["scenario"] == 0]
        forecast = taf[taf["scenario"] == 1]
        la, ff = self.taf.last_actual_year, self.taf.first_forecast_year
        fh = ff + FORECAST_HORIZON_YEARS

        def pick(df: pd.DataFrame, year: int, col: str) -> pd.Series:
            return df[df["year"] == year].drop_duplicates("lid").set_index("lid")[col]

        idx = base.index
        enpl_last, enpl_prev = pick(actual, la, "enpl_total"), pick(actual, la - 1, "enpl_total")
        enpl_2019 = pick(actual, RECOVERY_BASE_YEAR, "enpl_total")
        base["taf_enpl_last_actual"] = enpl_last.reindex(idx)
        base["taf_enpl_prev_actual"] = enpl_prev.reindex(idx)
        base["taf_growth_last_actual_pct"] = [pct_change(p, c) for p, c in zip(base["taf_enpl_prev_actual"], base["taf_enpl_last_actual"])]
        base["taf_enpl_2019"] = enpl_2019.reindex(idx)
        base["recovery_ratio"] = [safe_ratio(c, b) for c, b in zip(base["taf_enpl_last_actual"], base["taf_enpl_2019"])]
        intl = pick(actual, la, "enpl_intl").reindex(idx)
        base["taf_intl_share_pct"] = [safe_ratio(i, t) * 100 if safe_ratio(i, t) is not None else np.nan for i, t in zip(intl, base["taf_enpl_last_actual"])]

        ops_last, ops_2019 = pick(actual, la, "ops_ac_at"), pick(actual, RECOVERY_BASE_YEAR, "ops_ac_at")
        base["ops_last_actual"] = ops_last.reindex(idx)
        base["ops_2019"] = ops_2019.reindex(idx)
        peak_rows = actual.loc[actual.groupby("lid")["ops_ac_at"].idxmax()][["lid", "year", "ops_ac_at"]].set_index("lid")
        base["ops_peak"] = peak_rows["ops_ac_at"].reindex(idx)
        base["ops_peak_year"] = peak_rows["year"].reindex(idx)
        base["ops_forecast_h"] = pick(forecast, fh, "ops_ac_at").reindex(idx)
        base["forecast_vs_peak"] = [safe_ratio(f, p) for f, p in zip(base["ops_forecast_h"], base["ops_peak"])]
        base["forecast_vs_current_ops"] = [safe_ratio(f, c) for f, c in zip(base["ops_forecast_h"], base["ops_last_actual"])]
        base["ops_per_runway"] = [safe_ratio(o, r) for o, r in zip(base["ops_last_actual"], base["runways_qualifying"])]

        base["taf_enpl_forecast_start"] = pick(forecast, ff, "enpl_total").reindex(idx)
        base["taf_enpl_forecast_h"] = pick(forecast, fh, "enpl_total").reindex(idx)
        from app.kpi.normalize import cagr  # local import to avoid a cycle at module import time
        base["forecast_cagr_pct"] = [cagr(s, e, FORECAST_HORIZON_YEARS) for s, e in zip(base["taf_enpl_forecast_start"], base["taf_enpl_forecast_h"])]
        base["pax_per_op_last"] = [safe_ratio(e, o) for e, o in zip(base["taf_enpl_last_actual"], base["ops_last_actual"])]
        base["pax_per_op_2019"] = [safe_ratio(e, o) for e, o in zip(base["taf_enpl_2019"], base["ops_2019"])]
        base["upgauging_pct"] = [pct_change(a, b) for a, b in zip(base["pax_per_op_2019"], base["pax_per_op_last"])]
        base["taf_last_actual_year"] = la
        base["taf_forecast_start_year"] = ff
        base["taf_forecast_end_year"] = fh
        for c in cols:
            base[c] = pd.to_numeric(base[c], errors="coerce")

    def _add_delay(self, base: pd.DataFrame) -> None:
        cols = ["arr_flights", "arr_del15", "arr_cancelled", "arr_diverted", "del15_pct", "cancel_pct", "diverted_pct",
                "nas_share_pct", "weather_share_pct", "carrier_share_pct", "late_aircraft_share_pct", "security_share_pct",
                "avg_delay_min_per_delayed", "nas_minutes_share_pct"]
        for c in cols:
            base[c] = np.nan
        if self.delay is None:
            return
        d = self.delay.frame.groupby("airport")[NUMERIC_COLUMNS].sum()
        d = d[d["arr_flights"] > 0]
        d["del15_pct"] = d["arr_del15"] / d["arr_flights"] * 100
        d["cancel_pct"] = d["arr_cancelled"] / d["arr_flights"] * 100
        d["diverted_pct"] = d["arr_diverted"] / d["arr_flights"] * 100
        delayed = d["arr_del15"].replace(0, np.nan)
        d["nas_share_pct"] = d["nas_ct"] / delayed * 100
        d["weather_share_pct"] = d["weather_ct"] / delayed * 100
        d["carrier_share_pct"] = d["carrier_ct"] / delayed * 100
        d["late_aircraft_share_pct"] = d["late_aircraft_ct"] / delayed * 100
        d["security_share_pct"] = d["security_ct"] / delayed * 100
        d["avg_delay_min_per_delayed"] = d["arr_delay"] / delayed
        d["nas_minutes_share_pct"] = d["nas_delay"] / d["arr_delay"].replace(0, np.nan) * 100
        mapped = d.reindex(base["iata"].values)
        mapped.index = base.index
        for c in cols:
            base[c] = mapped[c].astype(float)

    def _add_ontime(self, base: pd.DataFrame) -> None:
        cols = ["departures", "dep_del15_pct", "avg_taxi_out_min", "dep_cancel_pct", "avg_dep_delay_min_per_flight"]
        for c in cols:
            base[c] = np.nan
        if self.ontime is None:
            return
        m = self.ontime.origin_metrics.groupby("origin")[["departures", "cancelled", "dep_del15", "taxi_out_total", "taxi_out_n", "dep_delay_total"]].sum()
        flown = (m["departures"] - m["cancelled"]).replace(0, np.nan)
        out = pd.DataFrame(index=m.index)
        out["departures"] = m["departures"]
        out["dep_del15_pct"] = m["dep_del15"] / flown * 100
        out["avg_taxi_out_min"] = m["taxi_out_total"] / m["taxi_out_n"].replace(0, np.nan)
        out["dep_cancel_pct"] = m["cancelled"] / m["departures"].replace(0, np.nan) * 100
        out["avg_dep_delay_min_per_flight"] = m["dep_delay_total"] / flown
        mapped = out.reindex(base["iata"].values)
        mapped.index = base.index
        for c in cols:
            base[c] = mapped[c].astype(float)

    def row(self, code: str) -> Optional[pd.Series]:
        airport = self.registry.get(code)
        if airport is None:
            return None
        table = self.metrics_table()
        hit = table[table["lid"] == airport.lid]
        return hit.iloc[0] if not hit.empty else None
