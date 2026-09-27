"""Canonical airport registry: one record per FAA location identifier (LID).

Joins the FAA enplanement universe with OurAirports (IATA/ICAO codes, coordinates,
runways), the TAF airport attributes (hub size, OEP-35 flag) and the FAA slot list.
Also owns all text-to-airport / text-to-state resolution used by the agent so the
LLM path and the rules path behave identically.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

import pandas as pd

from app.config import settings
from app.sources.ourairports import AirportReference, qualifying_runway_counts

# Three-letter English tokens that must never be read as airport codes.
STOPWORDS_3 = {
    "AND", "THE", "FOR", "ARE", "NOT", "BUT", "ALL", "ANY", "CAN", "HAS", "HOW", "ITS", "LET", "MAY", "NEW", "NOW",
    "OLD", "OUR", "OUT", "OWN", "SAY", "SEE", "TOO", "TOP", "TWO", "USE", "WAY", "WHO", "WHY", "YES", "YET", "PER",
    "VIA", "LOW", "BIG", "MID", "OFF", "ONE", "SET", "DUE", "END", "FEW", "GET", "GOT", "RUN", "WAS", "ETC", "ADD",
    "ROI", "KPI", "USA", "FAA", "BTS", "TAF", "NAS", "GDP", "CEO", "CFO", "PDF", "API", "LLM", "TOP", "VS.", "VS",
    "FAR", "MAP", "AIR", "HUB", "GAP", "BAD", "YOU", "HIM", "HER", "SHE", "HIS", "WE", "DID", "PUT", "SAW", "TEN",
    "SIX", "MAX", "MIN", "AVG", "SUM", "TAX", "FEE", "COST", "NET", "OPS", "MPH", "KMS", "MILE", "DAY", "YEAR", "JAN",
    "FEB", "MAR", "APR", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC", "MON", "TUE", "WED", "THU", "FRI", "SAT",
    "SUN", "AGO", "AKA", "TBD", "OK", "AMT", "PCT", "LBS", "TON", "CUT", "BIT", "LOT", "MET",
}
STATE_CODE_CONTEXT_RE = re.compile(r"\b(?:in|of|for|across|within|state of|from)\s+([A-Z]{2})\b")


@dataclass
class Airport:
    lid: str
    name: str
    city: str
    state: str
    service_level: str
    hub: str
    iata: Optional[str] = None
    icao: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    scheduled_service: Optional[bool] = None
    runways_qualifying: Optional[int] = None
    slot_level: int = 0
    taf_hub_size: Optional[int] = None
    oep35: bool = False
    join_gaps: List[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        code = self.iata or self.lid
        return f"{self.name} ({code}), {self.city}, {self.state}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "lid": self.lid, "iata": self.iata, "icao": self.icao, "name": self.name, "city": self.city,
            "state": self.state, "service_level": self.service_level, "hub": self.hub,
            "latitude": self.latitude, "longitude": self.longitude, "runways_qualifying": self.runways_qualifying,
            "slot_level": self.slot_level, "oep35": self.oep35, "join_gaps": list(self.join_gaps),
        }


def load_reference_json(name: str) -> Dict[str, object]:
    return json.loads((settings.reference_dir / name).read_text())


class AirportRegistry:
    def __init__(
        self,
        faa_frame: pd.DataFrame,
        reference: Optional[AirportReference] = None,
        taf_frame: Optional[pd.DataFrame] = None,
        slot_reference: Optional[Dict[str, object]] = None,
        regions: Optional[Dict[str, object]] = None,
    ) -> None:
        self.regions = regions or load_reference_json("regions.json")
        self.slot_reference = slot_reference or load_reference_json("slot_airports.json")
        self.state_names: Dict[str, str] = {v.lower(): k for k, v in self.regions["states"].items()}
        self.faa = faa_frame
        self.airports: Dict[str, Airport] = {}
        self.by_iata: Dict[str, Airport] = {}
        self.by_icao: Dict[str, Airport] = {}
        self._build(reference, taf_frame)
        self._name_index = self._build_name_index()

    # ------------------------------------------------------------------ build
    def _build(self, reference: Optional[AirportReference], taf_frame: Optional[pd.DataFrame]) -> None:
        level3 = set(self.slot_reference.get("level_3_slot_controlled", []))
        level2 = set(self.slot_reference.get("level_2_schedule_facilitated", []))
        ref_by_local: Dict[str, pd.Series] = {}
        ref_by_iata: Dict[str, pd.Series] = {}
        runway_counts: Optional[pd.Series] = None
        if reference is not None:
            # Prefer rows with scheduled service and larger facility type when codes collide.
            order = {"large_airport": 0, "medium_airport": 1, "small_airport": 2}
            ranked = reference.airports.assign(_rank=reference.airports["type"].map(order).fillna(9))
            ranked = ranked.sort_values(["scheduled_service", "_rank"], ascending=[False, True])
            for _, row in ranked.iterrows():
                if row["local_code"] and row["local_code"] not in ref_by_local:
                    ref_by_local[row["local_code"]] = row
                if row["iata_code"] and row["iata_code"] not in ref_by_iata:
                    ref_by_iata[row["iata_code"]] = row
            runway_counts = qualifying_runway_counts(reference.runways)
        taf_attrs: Dict[str, pd.Series] = {}
        if taf_frame is not None and not taf_frame.empty:
            taf_attrs = {r.lid: r for r in taf_frame.drop_duplicates("lid")[["lid", "hub_size", "oep35"]].itertuples(index=False)}

        for row in self.faa.itertuples(index=False):
            lid = str(row.lid)
            airport = Airport(lid=lid, name=str(row.name), city=str(row.city), state=str(row.state),
                              service_level=str(row.service_level), hub=str(row.hub))
            ref = ref_by_local.get(lid) if ref_by_local else None
            if ref is None and ref_by_iata:
                ref = ref_by_iata.get(lid)
            if ref is not None:
                airport.iata = ref["iata_code"] or None
                airport.icao = ref["ident"] or ref["gps_code"] or None
                airport.latitude = float(ref["latitude_deg"]) if pd.notna(ref["latitude_deg"]) else None
                airport.longitude = float(ref["longitude_deg"]) if pd.notna(ref["longitude_deg"]) else None
                airport.scheduled_service = bool(ref["scheduled_service"])
                if runway_counts is not None and airport.icao in runway_counts.index:
                    airport.runways_qualifying = int(runway_counts[airport.icao])
                elif runway_counts is not None:
                    airport.runways_qualifying = 0
            elif reference is not None:
                airport.join_gaps.append("no OurAirports match (coordinates/runways unavailable)")
            if airport.iata is None and re.fullmatch(r"[A-Z]{3}", lid):
                airport.iata = lid  # FAA LIDs of commercial airports normally equal their IATA code
            if airport.iata in level3:
                airport.slot_level = 3
            elif airport.iata in level2:
                airport.slot_level = 2
            taf = taf_attrs.get(lid)
            if taf is not None:
                airport.taf_hub_size = int(taf.hub_size)
                airport.oep35 = bool(taf.oep35)
            elif taf_attrs:
                airport.join_gaps.append("no TAF record (forecast/operations unavailable)")
            self.airports[lid] = airport
            if airport.iata and airport.iata not in self.by_iata:
                self.by_iata[airport.iata] = airport
            if airport.icao:
                self.by_icao[airport.icao] = airport

    def _build_name_index(self) -> List["tuple[str, str]"]:
        index: List["tuple[str, str]"] = []
        for airport in self.airports.values():
            if airport.service_level not in {"P", "CS"}:
                continue
            city = airport.city.lower().strip()
            if len(city) >= 4:
                index.append((city, airport.lid))
        # Longest phrases first so "san francisco" wins over "san".
        return sorted(set(index), key=lambda item: -len(item[0]))

    # ----------------------------------------------------------------- lookup
    def get(self, code: str) -> Optional[Airport]:
        code = (code or "").strip().upper()
        if not code:
            return None
        if code in self.airports:
            return self.airports[code]
        if code in self.by_iata:
            return self.by_iata[code]
        if code in self.by_icao:
            return self.by_icao[code]
        if len(code) == 4 and code.startswith("K") and code[1:] in self.airports:
            return self.airports[code[1:]]
        return None

    def universe(self, service_levels: Sequence[str] = ("P", "CS"), min_enplanements: float = 0) -> pd.DataFrame:
        frame = self.faa[self.faa["service_level"].isin(list(service_levels)) & (self.faa["enplanements"] >= min_enplanements)]
        return frame.copy()

    def states_for_region(self, name: str) -> Optional[List[str]]:
        return self.regions["regions"].get(name.lower().strip())

    # ------------------------------------------------------------- resolution
    def codes_in_text(self, text: str) -> List[str]:
        """Explicit airport codes: upper-case tokens, or lower-case tokens of major hubs."""
        found: List[str] = []
        for token in re.findall(r"\b[A-Za-z]{3,4}\b", text):
            upper = token.upper()
            if upper in STOPWORDS_3:
                continue
            airport = self.get(upper)
            if airport is None:
                continue
            if token.isupper() or (airport.hub in {"L", "M"} and airport.service_level == "P"):
                if airport.lid not in found:
                    found.append(airport.lid)
        return found

    def places_in_text(self, text: str) -> List[str]:
        """Metro aliases and city names -> LIDs (only P/CS airports for city matches)."""
        lowered = " " + re.sub(r"[^a-z0-9. ]+", " ", text.lower()) + " "
        found: List[str] = []
        consumed = re.sub(r"\bwashington state\b", " ", lowered)  # the state, not the DC metro
        aliases = sorted(self.regions["metro_aliases"].items(), key=lambda kv: -len(kv[0]))
        for alias, codes in aliases:
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, consumed):
                consumed = re.sub(pattern, " ", consumed)
                for code in codes:
                    airport = self.get(code)
                    if airport and airport.lid not in found:
                        found.append(airport.lid)
        for city, lid in self._name_index:
            if re.search(r"\b" + re.escape(city) + r"\b", consumed):
                consumed = re.sub(r"\b" + re.escape(city) + r"\b", " ", consumed)
                if lid not in found:
                    found.append(lid)
        return found

    def states_in_text(self, text: str) -> List[str]:
        """Regions ('New England'), state names ('Texas') and contextual codes ('in CA')."""
        lowered = " " + re.sub(r"[^a-z0-9\- ]+", " ", text.lower()) + " "
        states: List[str] = []
        for region, codes in sorted(self.regions["regions"].items(), key=lambda kv: -len(kv[0])):
            if re.search(r"\b" + re.escape(region) + r"\b", lowered):
                lowered = lowered.replace(region, " ")
                for code in codes:
                    if code not in states:
                        states.append(code)
        if re.search(r"\bwashington state\b", lowered):
            states.append("WA")
            lowered = lowered.replace("washington state", " ")
        for name, code in sorted(self.state_names.items(), key=lambda kv: -len(kv[0])):
            if name == "washington":
                continue  # ambiguous with the DC metro; handled by places_in_text
            if re.search(r"\b" + re.escape(name) + r"\b", lowered) and code not in states:
                states.append(code)
                lowered = lowered.replace(name, " ")
        for code in STATE_CODE_CONTEXT_RE.findall(text):
            if code in self.regions["states"] and code not in states and self.get(code) is None:
                states.append(code)
        return states

    def resolve(self, text: str) -> Dict[str, List[str]]:
        codes = self.codes_in_text(text)
        places = [lid for lid in self.places_in_text(text) if lid not in codes]
        return {"codes": codes, "places": places, "states": self.states_in_text(text)}

    def search(self, query: str, limit: int = 8) -> List[Airport]:
        q = query.lower().strip()
        hits: List[Airport] = []
        for lid in self.codes_in_text(query) + self.places_in_text(query):
            airport = self.airports.get(lid)
            if airport and airport not in hits:
                hits.append(airport)
        if not hits:
            for airport in self.airports.values():
                if airport.service_level in {"P", "CS"} and (q in airport.name.lower() or q in airport.city.lower()):
                    hits.append(airport)
        hits.sort(key=lambda a: -float(self.faa.loc[self.faa["lid"] == a.lid, "enplanements"].max() or 0))
        return hits[:limit]
