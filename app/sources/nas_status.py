"""FAA National Airspace System status feed (live ground delays, ground stops, closures).

Source: https://nasstatus.faa.gov/api/airport-status-information (public XML, no key).
Used only as a live annotation; it never enters the deterministic scores.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from app.sources.cache import SourceUnavailable, fetch_bytes

NAS_STATUS_URL = "https://nasstatus.faa.gov/api/airport-status-information"


def parse_nas_status(xml_bytes: bytes) -> Dict[str, object]:
    root = ET.fromstring(xml_bytes)
    update_time = (root.findtext("Update_Time") or "").strip()
    events: Dict[str, List[Dict[str, str]]] = {}

    def add(code: Optional[str], event: Dict[str, str]) -> None:
        if not code:
            return
        events.setdefault(code.strip().upper(), []).append(event)

    for node in root.iter("Ground_Delay"):
        add(node.findtext("ARPT"), {"type": "ground_delay", "reason": (node.findtext("Reason") or "").strip(),
                                    "average": (node.findtext("Avg") or "").strip(), "max": (node.findtext("Max") or "").strip()})
    for node in root.iter("Ground_Stop"):
        add(node.findtext("ARPT"), {"type": "ground_stop", "reason": (node.findtext("Reason") or "").strip(),
                                    "end_time": (node.findtext("End_Time") or "").strip()})
    for node in root.iter("Delay"):
        ad = node.find("Arrival_Departure")
        add(node.findtext("ARPT"), {"type": "general_delay", "reason": (node.findtext("Reason") or "").strip(),
                                    "direction": (ad.get("Type") if ad is not None else "") or "",
                                    "min": (ad.findtext("Min") if ad is not None else "") or "",
                                    "max": (ad.findtext("Max") if ad is not None else "") or "",
                                    "trend": (ad.findtext("Trend") if ad is not None else "") or ""})
    for node in root.iter("Airport_Closure"):
        add(node.findtext("ARPT"), {"type": "closure", "reason": (node.findtext("Reason") or "").strip(),
                                    "start": (node.findtext("Start") or "").strip(), "reopen": (node.findtext("Reopen") or "").strip()})
    return {"update_time": update_time, "events": events}


def load_nas_status(ttl_seconds: float = 300) -> Dict[str, object]:
    try:
        fetched = fetch_bytes(NAS_STATUS_URL, "nas_status.xml", ttl_seconds, timeout=20)
    except SourceUnavailable as exc:
        return {"update_time": "", "events": {}, "error": str(exc), "retrieved_at": None}
    parsed = parse_nas_status(fetched.content)
    parsed["retrieved_at"] = fetched.retrieved_at
    parsed["url"] = NAS_STATUS_URL
    return parsed
