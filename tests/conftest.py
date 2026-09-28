"""Shared offline fixtures: a full Engine built from small slices of the real data."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.engine import Engine
from app.sources.bts_delay_cause import DelayCause
from app.sources.bts_ontime import OnTimeSnapshot
from app.sources.faa_enplanements import parse_workbook
from app.sources.ourairports import reference_from_csv
from app.sources.taf import Taf

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_nas() -> dict:
    return {"update_time": "Sun Sep 27 15:07:39 2026 GMT", "retrieved_at": "2026-09-27T15:07:39+00:00",
            "events": {"SFO": [{"type": "ground_delay", "reason": "low ceilings", "average": "49 minutes", "max": "1 hour and 42 minutes"}]}}


@pytest.fixture(scope="session")
def faa():
    return parse_workbook((FIXTURES / "faa_sample.xlsx").read_bytes(),
                          "https://www.faa.gov/x/arp-cy2025-all-enplanements-preliminary.xlsx", "2026-09-27T00:00:00+00:00", True)


@pytest.fixture(scope="session")
def reference():
    return reference_from_csv(FIXTURES / "ourairports_sample.csv", FIXTURES / "runways_sample.csv", "2026-09-27T00:00:00+00:00")


@pytest.fixture(scope="session")
def taf():
    frame = pd.read_csv(FIXTURES / "taf_compact_sample.csv")
    return Taf(frame, 2024, 2025, 2055, "snapshot")


@pytest.fixture(scope="session")
def delay():
    frame = pd.read_csv(FIXTURES / "delay_cause_sample.csv")
    return DelayCause(frame, (2025, 8), (2026, 7), "snapshot", True)


@pytest.fixture(scope="session")
def ontime():
    return OnTimeSnapshot(pd.read_csv(FIXTURES / "routes_sample.csv"), pd.read_csv(FIXTURES / "ontime_metrics_sample.csv"), ["2026-07"], "snapshot")


@pytest.fixture(scope="session")
def engine(faa, reference, taf, delay, ontime):
    return Engine(faa, reference, taf, delay, ontime, _fake_nas, {"test": {"ok": True}})


@pytest.fixture(scope="session")
def table(engine):
    return engine.metrics_table()
