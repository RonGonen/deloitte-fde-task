"""BTS Reporting Carrier On-Time Performance (flight-level, monthly ~33 MB zip).

Source: https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{Y}_{M}.zip
Only domestic flights of carriers above the DOT reporting threshold are included;
international and all-cargo operations are absent. The files are large and the server
is slow, so this module is only used by ``scripts/refresh_data.py`` to build two small
snapshots: routes by origin (with distance) and per-origin departure metrics.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.config import settings

PREZIP_URL = "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
USE_COLUMNS = ["Year", "Month", "Origin", "Dest", "Distance", "DepDel15", "DepDelay", "TaxiOut", "Cancelled", "Diverted"]


def ontime_url(year: int, month: int) -> str:
    return PREZIP_URL.format(year=year, month=month)


def read_month(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as archive:
        csv_name = [n for n in archive.namelist() if n.lower().endswith(".csv")][0]
        with archive.open(csv_name) as handle:
            df = pd.read_csv(handle, usecols=lambda c: c in USE_COLUMNS, low_memory=False)
    for col in ("Origin", "Dest"):
        df[col] = df[col].astype(str).str.strip().str.upper()
    return df


def aggregate_month(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (routes_by_origin, origin_metrics) for one month of flight-level rows."""
    year, month = int(df["Year"].iloc[0]), int(df["Month"].iloc[0])
    routes = df.groupby(["Origin", "Dest"], as_index=False).agg(
        departures=("Dest", "size"), cancelled=("Cancelled", "sum"), distance_mi=("Distance", "first"))
    routes.insert(0, "month", month)
    routes.insert(0, "year", year)
    routes = routes.rename(columns={"Origin": "origin", "Dest": "dest"})

    flown = df[df["Cancelled"] == 0]
    metrics = df.groupby("Origin").agg(departures=("Origin", "size"), cancelled=("Cancelled", "sum"), diverted=("Diverted", "sum"))
    flown_metrics = flown.groupby("Origin").agg(
        dep_del15=("DepDel15", "sum"), taxi_out_total=("TaxiOut", "sum"), taxi_out_n=("TaxiOut", "count"),
        dep_delay_total=("DepDelay", lambda s: s.clip(lower=0).sum()))
    metrics = metrics.join(flown_metrics, how="left").fillna(0).reset_index().rename(columns={"Origin": "origin"})
    metrics.insert(0, "month", month)
    metrics.insert(0, "year", year)
    return routes, metrics


@dataclass
class OnTimeSnapshot:
    routes: pd.DataFrame
    origin_metrics: pd.DataFrame
    months: List[str]
    retrieved_at: str
    notes: List[str] = field(default_factory=list)

    @property
    def period_label(self) -> str:
        return ", ".join(self.months) if self.months else "n/a"

    def source(self) -> Dict[str, object]:
        return {"name": "BTS Reporting Carrier On-Time Performance (flight-level)",
                "url": "https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FGJ",
                "period": self.period_label, "retrieved_at": self.retrieved_at,
                "vintage": "domestic scheduled flights of reporting carriers only"}


def load_ontime_snapshot() -> Optional[OnTimeSnapshot]:
    routes_path = settings.snapshot_dir / "routes_by_origin.csv"
    metrics_path = settings.snapshot_dir / "ontime_origin_metrics.csv"
    if not (routes_path.exists() and metrics_path.exists()):
        return None
    routes = pd.read_csv(routes_path)
    metrics = pd.read_csv(metrics_path)
    months = sorted({f"{int(y)}-{int(m):02d}" for y, m in metrics[["year", "month"]].drop_duplicates().itertuples(index=False)})
    retrieved = "snapshot"
    try:
        retrieved = json.loads((settings.snapshot_dir / "manifest.json").read_text()).get("ontime", {}).get("retrieved_at", retrieved)
    except (OSError, ValueError):
        pass
    return OnTimeSnapshot(routes, metrics, months, retrieved)
