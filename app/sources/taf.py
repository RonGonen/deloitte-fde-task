"""FAA Terminal Area Forecast (TAF): actual history and official forecasts per airport.

Source: https://taf.faa.gov/ (APO100_TAF_Final_2025.zip). The zip holds Excel tables:
Enplanements (aac, aat, commuter, us_flag, frgn_flag by year), AirportsOperations
(itinerant air carrier / air taxi / GA / military), and Airports (hub size, OEP35 flag).
``scenario`` 0 = actual (through the last actual year), 1 = FAA forecast.

Because the 15 MB workbook set takes tens of seconds to parse, ``scripts/refresh_data.py``
builds a compact CSV snapshot (``data/snapshots/taf_compact.csv``) that the app loads.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import pandas as pd

from app.config import settings
from app.sources.cache import SourceUnavailable, fetch_bytes

TAF_ZIP_URL = "https://taf.faa.gov/Downloads/APO100_TAF_Final_2025.zip"
TAF_PAGE_URL = "https://taf.faa.gov/"
TAF_EDITION = "TAF 2025 (final, published 2026)"
MIN_YEAR = 1990

COMPACT_COLUMNS = ["lid", "scenario", "year", "enpl_total", "enpl_domestic", "enpl_intl",
                   "ops_air_carrier", "ops_air_taxi", "ops_ga", "ops_military", "hub_size", "oep35"]


@dataclass
class Taf:
    frame: pd.DataFrame
    last_actual_year: int
    first_forecast_year: int
    last_forecast_year: int
    retrieved_at: str
    edition: str = TAF_EDITION
    notes: List[str] = field(default_factory=list)

    def source(self) -> Dict[str, object]:
        return {"name": "FAA Terminal Area Forecast (TAF)", "url": TAF_PAGE_URL,
                "period": f"actuals to {self.last_actual_year}, forecast {self.first_forecast_year}-{self.last_forecast_year}",
                "retrieved_at": self.retrieved_at, "vintage": self.edition}

    def series(self, lid: str) -> pd.DataFrame:
        return self.frame[self.frame["lid"] == lid.upper()].sort_values(["scenario", "year"])


def build_compact(zip_bytes: bytes, lids: Optional[Iterable[str]] = None, min_year: int = MIN_YEAR) -> pd.DataFrame:
    """Parse the TAF workbooks into one compact long table (slow: ~30-60 s)."""
    wanted = {l.upper() for l in lids} if lids is not None else None
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        enp = pd.read_excel(io.BytesIO(archive.read("Enplanements.xlsx")))
        ops = pd.read_excel(io.BytesIO(archive.read("AirportsOperations.xlsx")))
        air = pd.read_excel(io.BytesIO(archive.read("Airports.xlsx")))
    for df in (enp, ops):
        df["locid"] = df["locid"].astype(str).str.strip().str.upper()
        df.rename(columns={"ayear": "year"}, inplace=True)
    air["LOCID"] = air["LOCID"].astype(str).str.strip().str.upper()
    if wanted is not None:
        enp = enp[enp["locid"].isin(wanted)]
        ops = ops[ops["locid"].isin(wanted)]
    enp = enp[enp["year"] >= min_year]
    ops = ops[ops["year"] >= min_year]

    enp = enp.assign(
        enpl_domestic=enp["aac"] + enp["aat"] + enp["commuter"],
        enpl_intl=enp["us_flag"] + enp["frgn_flag"],
    )
    enp["enpl_total"] = enp["enpl_domestic"] + enp["enpl_intl"]
    ops = ops.rename(columns={"itn_Ac": "ops_air_carrier", "itn_at": "ops_air_taxi", "itn_ga": "ops_ga", "itn_mil": "ops_military"})
    merged = enp[["locid", "scenario", "year", "enpl_total", "enpl_domestic", "enpl_intl"]].merge(
        ops[["locid", "scenario", "year", "ops_air_carrier", "ops_air_taxi", "ops_ga", "ops_military"]],
        on=["locid", "scenario", "year"], how="outer")
    attrs = air.set_index("LOCID")[["HUB_SIZE", "OEP35"]]
    merged["hub_size"] = merged["locid"].map(attrs["HUB_SIZE"]).fillna(0).astype(int)
    merged["oep35"] = merged["locid"].map(attrs["OEP35"]).fillna(0).astype(int)
    merged = merged.rename(columns={"locid": "lid"})
    return merged[COMPACT_COLUMNS].sort_values(["lid", "scenario", "year"]).reset_index(drop=True)


def _from_frame(frame: pd.DataFrame, retrieved_at: str) -> Taf:
    actual = frame[frame["scenario"] == 0]
    forecast = frame[frame["scenario"] == 1]
    return Taf(frame, int(actual["year"].max()), int(forecast["year"].min()), int(forecast["year"].max()), retrieved_at)


def download_and_build(lids: Optional[Iterable[str]] = None) -> Taf:
    fetched = fetch_bytes(TAF_ZIP_URL, "APO100_TAF_Final_2025.zip", 30 * 24 * 3600)
    frame = build_compact(fetched.content, lids)
    return _from_frame(frame, fetched.retrieved_at)


def load_taf(lids: Optional[Iterable[str]] = None) -> Taf:
    """Load the committed compact snapshot; build it from the FAA download if missing."""
    snapshot = settings.snapshot_dir / "taf_compact.csv"
    manifest = settings.snapshot_dir / "manifest.json"
    if snapshot.exists():
        frame = pd.read_csv(snapshot)
        retrieved = "snapshot"
        try:
            retrieved = json.loads(manifest.read_text()).get("taf", {}).get("retrieved_at", retrieved)
        except (OSError, ValueError):
            pass
        return _from_frame(frame, retrieved)
    if settings.offline:
        raise SourceUnavailable("No TAF snapshot and OFFLINE=1")
    taf = download_and_build(lids)
    taf.notes.append("TAF compact table built live from the FAA download (no snapshot found).")
    return taf
