"""FAA passenger boarding (enplanement) statistics.

Source page: https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger
The FAA publishes one workbook per calendar year with the current and prior year
enplanements for every US airport in the NPIAS, plus service level (P = primary,
CS = commercial service, GA, R = reliever) and hub size (L/M/S/N).
"""
from __future__ import annotations

import io
import logging
import re
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.config import settings
from app.sources.cache import Fetched, SourceUnavailable, fetch_bytes

log = logging.getLogger(__name__)
FAA_PAGE_URL = "https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger"
WORKBOOK_RE = re.compile(r'href="([^"]*arp-cy(\d{4})-all-enplanements(-preliminary)?\.xlsx)"', re.IGNORECASE)
CY_COLUMN_RE = re.compile(r"^CY\s*(\d{2,4})\s*Enplanements$", re.IGNORECASE)


@dataclass
class FaaEnplanements:
    frame: pd.DataFrame
    latest_year: int
    previous_year: int
    preliminary: bool
    source_url: str
    retrieved_at: str
    from_cache: bool = False
    notes: List[str] = field(default_factory=list)

    def source(self) -> Dict[str, object]:
        return {
            "name": "FAA Passenger Boarding (Enplanement) Data",
            "url": self.source_url,
            "period": f"CY{self.latest_year} vs CY{self.previous_year}" + (" (preliminary)" if self.preliminary else ""),
            "retrieved_at": self.retrieved_at,
            "vintage": f"CY{self.latest_year}{' preliminary' if self.preliminary else ' final'}",
        }


def discover_workbooks(html: str) -> List[Tuple[int, bool, str]]:
    """Return (year, preliminary, absolute_url) for every enplanement workbook linked on the page."""
    found = []
    for href, year, prelim in WORKBOOK_RE.findall(html):
        url = href if href.startswith("http") else "https://www.faa.gov" + href
        found.append((int(year), bool(prelim), url))
    found.sort(key=lambda item: (item[0], not item[1]), reverse=True)
    return found


def _year_from_header(header: str) -> int:
    match = CY_COLUMN_RE.match(header.strip())
    if not match:
        raise ValueError(f"Not a CY enplanement column: {header!r}")
    value = int(match.group(1))
    return value + 2000 if value < 100 else value


def parse_workbook(content: bytes, source_url: str = "", retrieved_at: str = "", from_cache: bool = False) -> FaaEnplanements:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Cannot parse header or footer", category=UserWarning)  # cosmetic openpyxl notice
        raw = pd.read_excel(io.BytesIO(content), header=None)
    header_idx = None
    for idx, row in raw.iterrows():
        values = [str(v).strip() for v in row.tolist()]
        if "Locid" in values:
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError("FAA workbook has no 'Locid' header row")
    headers = [str(v).strip() for v in raw.iloc[header_idx].tolist()]
    body = raw.iloc[header_idx + 1 :].copy()
    body.columns = headers

    cy_cols = [h for h in headers if CY_COLUMN_RE.match(h)]
    if len(cy_cols) < 2:
        raise ValueError("FAA workbook does not contain two CY enplanement columns")
    cy_cols.sort(key=_year_from_header, reverse=True)
    latest_col, prev_col = cy_cols[0], cy_cols[1]
    latest_year, previous_year = _year_from_header(latest_col), _year_from_header(prev_col)

    frame = pd.DataFrame(
        {
            "lid": body["Locid"].astype(str).str.strip().str.upper(),
            "state": body["ST"].astype(str).str.strip().str.upper(),
            "region": body["RO"].astype(str).str.strip().str.upper() if "RO" in body else "",
            "city": body["City"].astype(str).str.strip(),
            "name": body["Airport Name"].astype(str).str.strip(),
            "service_level": body["S/L"].astype(str).str.strip().str.upper(),
            "hub": body["Hub"].astype(str).str.strip().str.upper() if "Hub" in body else "",
            "enplanements": pd.to_numeric(body[latest_col], errors="coerce"),
            "enplanements_prev": pd.to_numeric(body[prev_col], errors="coerce"),
        }
    )
    frame = frame[frame["lid"].ne("") & frame["lid"].ne("NAN") & frame["enplanements"].notna()].copy()
    frame["enplanements"] = frame["enplanements"].astype(float)
    # Growth is recomputed from the two columns; the workbook's '% Change' column is a
    # fraction (e.g. -0.0139) and is only used as a cross-check in tests.
    prev = frame["enplanements_prev"]
    frame["yoy_pct"] = ((frame["enplanements"] / prev) - 1.0) * 100.0
    frame.loc[~(prev > 0), "yoy_pct"] = float("nan")
    frame = frame.drop_duplicates("lid").reset_index(drop=True)

    preliminary = "preliminary" in source_url.lower()
    return FaaEnplanements(frame, latest_year, previous_year, preliminary, source_url, retrieved_at, from_cache)


def load_faa_enplanements(ttl_seconds: float = 24 * 3600) -> FaaEnplanements:
    """Fetch the newest FAA workbook (live, cached) and fall back to the committed copy."""
    fallback = settings.snapshot_dir / "faa_enplanements_fallback.xlsx"
    try:
        page = fetch_bytes(FAA_PAGE_URL, "faa_enplanements_page.html", ttl_seconds)
        workbooks = discover_workbooks(page.content.decode("utf-8", errors="ignore"))
        if not workbooks:
            raise SourceUnavailable("No enplanement workbook link found on the FAA page")
        year, prelim, url = workbooks[0]
        fetched: Fetched = fetch_bytes(url, f"faa_enplanements_cy{year}{'_prelim' if prelim else ''}.xlsx", ttl_seconds)
        result = parse_workbook(fetched.content, fetched.url, fetched.retrieved_at, fetched.from_cache)
        if fetched.stale:
            result.notes.append("FAA workbook served from a stale cache because the live fetch failed.")
        return result
    except SourceUnavailable as exc:
        if not fallback.exists():
            raise
        result = parse_workbook(
            fallback.read_bytes(),
            "https://www.faa.gov/airports/planning_capacity/passenger_allcargo_stats/passenger/arp-cy2025-all-enplanements-preliminary.xlsx",
            "snapshot",
            True,
        )
        log.warning("FAA enplanement live fetch failed, using committed copy: %s", exc)
        result.notes.append("Live FAA download was unavailable; using the committed CY2025 preliminary workbook.")
        return result
