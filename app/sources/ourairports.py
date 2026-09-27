"""OurAirports open data (public domain): airport reference and runways.

Source: https://ourairports.com/data/ (CSV mirrors on GitHub Pages).
Used for code mapping (FAA LID <-> IATA <-> ICAO), coordinates, municipality, and a
physical capacity proxy (count of qualifying runways).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from app.sources.cache import fetch_bytes

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


def load_airport_reference(ttl_seconds: float = 7 * 24 * 3600) -> AirportReference:
    airports = fetch_bytes(AIRPORTS_URL, "ourairports_airports.csv", ttl_seconds)
    runways = fetch_bytes(RUNWAYS_URL, "ourairports_runways.csv", ttl_seconds)
    return AirportReference(parse_airports(airports.content), parse_runways(runways.content), airports.retrieved_at)
