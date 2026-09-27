"""BTS Airline On-Time Statistics and Delay Causes (per airport, per carrier, per month).

Source: https://www.transtats.bts.gov/OT_Delay/OT_DelayCause1.asp ("Download Raw Data").
The download endpoint takes an obfuscated SQL fragment in the ``8n4`` query parameter:
a +13 rotation over the 62-character alphabet [0-9A-Za-z]. The month key is
``year * 12 + month``. This was verified against the link the BTS page itself emits.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.config import settings
from app.sources.cache import SourceUnavailable, fetch_bytes

PAGE_URL = "https://www.transtats.bts.gov/OT_Delay/OT_DelayCause1.asp"
DOWNLOAD_URL = "https://www.transtats.bts.gov/ot_delay/ot_delaycause1_DL.aspx"
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
NUMERIC_COLUMNS = ["arr_flights", "arr_del15", "carrier_ct", "weather_ct", "nas_ct", "security_ct",
                   "late_aircraft_ct", "arr_cancelled", "arr_diverted", "arr_delay", "carrier_delay",
                   "weather_delay", "nas_delay", "security_delay", "late_aircraft_delay"]


def encode(text: str) -> str:
    return "".join(ALPHABET[(ALPHABET.index(ch) + 13) % 62] if ch in ALPHABET else ch for ch in text)


def decode(text: str) -> str:
    return "".join(ALPHABET[(ALPHABET.index(ch) - 13) % 62] if ch in ALPHABET else ch for ch in text)


def month_key(year: int, month: int) -> int:
    return year * 12 + month


def key_to_month(key: int) -> Tuple[int, int]:
    year, month = divmod(key, 12)
    if month == 0:
        return year - 1, 12
    return year, month


def download_param(start: Tuple[int, int], end: Tuple[int, int]) -> str:
    return encode(f"where yearmonth between {month_key(*start)} AND {month_key(*end)}")


def default_window(today: Optional[date] = None, months: int = 12, lag_months: int = 2) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """BTS publishes with roughly a two-month lag; ask for the trailing window ending then."""
    today = today or date.today()
    end_key = month_key(today.year, today.month) - lag_months
    start_key = end_key - months + 1
    return key_to_month(start_key), key_to_month(end_key)


@dataclass
class DelayCause:
    frame: pd.DataFrame  # one row per airport (IATA), year, month, aggregated across carriers
    period_start: Tuple[int, int]
    period_end: Tuple[int, int]
    retrieved_at: str
    from_cache: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def period_label(self) -> str:
        return f"{self.period_start[0]}-{self.period_start[1]:02d} to {self.period_end[0]}-{self.period_end[1]:02d}"

    def source(self) -> Dict[str, object]:
        return {"name": "BTS Airline On-Time Statistics and Delay Causes", "url": PAGE_URL,
                "period": self.period_label, "retrieved_at": self.retrieved_at,
                "vintage": "monthly; domestic flights of reporting carriers; arrivals-based"}


def parse_delay_cause_csv(csv_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(csv_bytes), encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["airport"] = df["airport"].astype(str).str.strip().str.upper()
    grouped = df.groupby(["airport", "year", "month"], as_index=False)[NUMERIC_COLUMNS].sum()
    names = df.drop_duplicates("airport").set_index("airport")["airport_name"]
    grouped["airport_name"] = grouped["airport"].map(names)
    return grouped


def parse_download(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        csv_names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError("Delay-cause download has no CSV member")
        return parse_delay_cause_csv(archive.read(csv_names[0]))


def load_delay_cause(months: int = 12, ttl_seconds: float = 24 * 3600, today: Optional[date] = None) -> DelayCause:
    start, end = default_window(today, months)
    snapshot = settings.snapshot_dir / "delay_cause_12m.csv"
    try:
        fetched = fetch_bytes(
            DOWNLOAD_URL,
            f"bts_delay_cause_{start[0]}{start[1]:02d}_{end[0]}{end[1]:02d}.zip",
            ttl_seconds,
            params={"8n4": download_param(start, end)},
            headers={"Referer": PAGE_URL},
            prime_url=PAGE_URL,
        )
        frame = parse_download(fetched.content)
        if frame.empty:
            raise SourceUnavailable("Delay-cause download returned no rows")
        actual_start = tuple(frame.sort_values(["year", "month"]).iloc[0][["year", "month"]].astype(int))
        actual_end = tuple(frame.sort_values(["year", "month"]).iloc[-1][["year", "month"]].astype(int))
        result = DelayCause(frame, (int(actual_start[0]), int(actual_start[1])), (int(actual_end[0]), int(actual_end[1])),
                            fetched.retrieved_at, fetched.from_cache)
        if fetched.stale:
            result.notes.append("BTS delay-cause data served from a stale cache because the live fetch failed.")
        return result
    except (SourceUnavailable, ValueError, zipfile.BadZipFile) as exc:
        if not snapshot.exists():
            raise SourceUnavailable(f"BTS delay cause unavailable and no snapshot: {exc}")
        frame = pd.read_csv(snapshot)
        ordered = frame.sort_values(["year", "month"])
        first, last = ordered.iloc[0], ordered.iloc[-1]
        result = DelayCause(frame, (int(first.year), int(first.month)), (int(last.year), int(last.month)), "snapshot", True)
        result.notes.append(f"Using committed BTS delay-cause snapshot; live fetch failed: {exc}")
        return result
