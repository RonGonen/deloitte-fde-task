"""OurAirports open data (public domain): airport reference and runways.

Source: https://ourairports.com/data/ (CSV mirrors on GitHub Pages).
Used for code mapping (FAA LID <-> IATA <-> ICAO), coordinates, municipality, and a
physical capacity proxy (count of qualifying runways).
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from app.config import settings
from app.sources.cache import SourceUnavailable, fetch_bytes

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"
AIRPORT_TYPES = ("large_airport", "medium_airport", "small_airport")
US_COUNTRIES = ("US", "PR", "VI", "GU", "MP", "AS")  # states plus territories in the FAA system
SOFT_SURFACE_RE = re.compile(r"water|turf|grass|gravel|grvl|dirt|sand|snow|ice|clay|soil|gvl|earth", re.IGNORECASE)
MIN_RUNWAY_FT = 5000


@dataclass
class AirportReference:
    airports: pd.DataFrame
    runways: pd.DataFrame
    retrieved_at: str
    url: str = AIRPORTS_URL

    def source(self) -> Dict[str, object]:
        return {"name": "OurAirports open data (airports, runways)", "url": "https://ourairports.com/data/",
                "period": "current", "retrieved_at": self.retrieved_at, "vintage": "community-maintained, refreshed daily"}


def parse_airports(csv_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)
    df = df[df["iso_country"].isin(US_COUNTRIES) & df["type"].isin(AIRPORT_TYPES)].copy()
    df["state"] = df["iso_region"].str.split("-").str[-1].str.upper()
    for col in ("ident", "gps_code", "iata_code", "local_code"):
        df[col] = df[col].str.strip().str.upper()
    df["latitude_deg"] = pd.to_numeric(df["latitude_deg"], errors="coerce")
    df["longitude_deg"] = pd.to_numeric(df["longitude_deg"], errors="coerce")
    df["scheduled_service"] = df["scheduled_service"].str.lower().eq("yes")
    keep = ["ident", "type", "name", "latitude_deg", "longitude_deg", "state", "municipality",
            "scheduled_service", "gps_code", "iata_code", "local_code"]
    return df[keep].reset_index(drop=True)


def parse_runways(csv_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)
    df["airport_ident"] = df["airport_ident"].str.strip().str.upper()
    df["length_ft"] = pd.to_numeric(df["length_ft"], errors="coerce")
    df["closed"] = pd.to_numeric(df["closed"], errors="coerce").fillna(0).astype(int)
    df["qualifying"] = (
        (df["closed"] == 0)
        & (df["length_ft"] >= MIN_RUNWAY_FT)
        & ~df["surface"].str.contains(SOFT_SURFACE_RE, na=False)
        & ~df["le_ident"].str.upper().str.startswith("H")
    )
    return df[["airport_ident", "length_ft", "surface", "closed", "le_ident", "he_ident", "qualifying"]].reset_index(drop=True)


def qualifying_runway_counts(runways: pd.DataFrame) -> pd.Series:
    """Number of open, paved, >= 5,000 ft runways per airport ident (ICAO/GPS code)."""
    return runways[runways["qualifying"]].groupby("airport_ident").size()


AIRPORTS_SNAPSHOT = "ourairports_airports_compact.csv"
RUNWAYS_SNAPSHOT = "ourairports_runways_compact.csv"


def reference_from_csv(airports_path: Path, runways_path: Path, retrieved_at: str = "snapshot") -> AirportReference:
    """Load already-parsed airport/runway tables written by ``compact_reference``."""
    airports = pd.read_csv(airports_path, dtype=str, keep_default_na=False)
    airports["latitude_deg"] = pd.to_numeric(airports["latitude_deg"], errors="coerce")
    airports["longitude_deg"] = pd.to_numeric(airports["longitude_deg"], errors="coerce")
    airports["scheduled_service"] = airports["scheduled_service"].str.lower().eq("true")
    runways = pd.read_csv(runways_path, dtype={"airport_ident": str, "surface": str, "le_ident": str, "he_ident": str}, keep_default_na=False)
    runways["length_ft"] = pd.to_numeric(runways["length_ft"], errors="coerce")
    runways["closed"] = pd.to_numeric(runways["closed"], errors="coerce").fillna(0).astype(int)
    runways["qualifying"] = runways["qualifying"].astype(str).str.lower().eq("true")
    return AirportReference(airports, runways, retrieved_at)


def compact_reference(reference: AirportReference, lids: Iterable[str]) -> AirportReference:
    """Keep only rows that can join to an FAA airport (by FAA LID, IATA or ICAO ident) plus their runways."""
    wanted = {l.upper() for l in lids}
    icao = {"K" + l for l in wanted if len(l) == 3}
    a = reference.airports
    keep = a["local_code"].isin(wanted) | a["iata_code"].isin(wanted) | a["ident"].isin(wanted | icao) | a["gps_code"].isin(wanted | icao)
    airports = a[keep].reset_index(drop=True)
    runways = reference.runways[reference.runways["airport_ident"].isin(set(airports["ident"]))].reset_index(drop=True)
    return AirportReference(airports, runways, reference.retrieved_at)


def load_airport_reference_live(ttl_seconds: float = 7 * 24 * 3600) -> AirportReference:
    airports = fetch_bytes(AIRPORTS_URL, "ourairports_airports.csv", ttl_seconds)
    runways = fetch_bytes(RUNWAYS_URL, "ourairports_runways.csv", ttl_seconds)
    return AirportReference(parse_airports(airports.content), parse_runways(runways.content), airports.retrieved_at)


def load_airport_reference(ttl_seconds: float = 7 * 24 * 3600, prefer_snapshot: bool = True) -> AirportReference:
    """Use the compact committed snapshot (a few hundred KB) when present; otherwise download the
    full 17 MB tables. ``scripts/refresh_data.py`` refreshes the snapshot."""
    airports_path = settings.snapshot_dir / AIRPORTS_SNAPSHOT
    runways_path = settings.snapshot_dir / RUNWAYS_SNAPSHOT
    if prefer_snapshot and airports_path.exists() and runways_path.exists():
        retrieved = "snapshot"
        try:
            retrieved = json.loads((settings.snapshot_dir / "manifest.json").read_text()).get("ourairports", {}).get("retrieved_at", retrieved)
        except (OSError, ValueError):
            pass
        return reference_from_csv(airports_path, runways_path, retrieved)
    if settings.offline:
        raise SourceUnavailable("No OurAirports snapshot and OFFLINE=1")
    return load_airport_reference_live(ttl_seconds)
