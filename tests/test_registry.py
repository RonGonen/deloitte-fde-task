"""Airport registry: joins and text resolution (the collisions that bit the previous prototype)."""
from __future__ import annotations

import pytest

NEW_ENGLAND = ["CT", "ME", "MA", "NH", "RI", "VT"]


def test_registry_joins_codes_runways_and_slot_levels(engine):
    reg = engine.registry
    sfo = reg.get("SFO")
    assert sfo.iata == "SFO" and sfo.icao == "KSFO" and sfo.slot_level == 2 and sfo.runways_qualifying == 4
    assert reg.get("KSFO") is sfo and reg.get("sfo") is sfo
    assert reg.get("JFK").slot_level == 3 and reg.get("BOS").slot_level == 0
    assert reg.get("SNA").runways_qualifying == 1
    assert reg.get("ANC").taf_hub_size == 2 and reg.get("BOS").oep35 is True
    assert reg.get("NOPE") is None


def test_universe_filters_service_level_and_volume(engine):
    uni = engine.registry.universe(min_enplanements=100_000)
    assert set(uni["service_level"]) <= {"P", "CS"}
    assert (uni["enplanements"] >= 100_000).all()
    assert "DGG" not in set(uni["lid"])  # GA airport in the fixture


@pytest.mark.parametrize("text,codes", [
    ("And compare BOS too", ["BOS"]),
    ("Compare BOS and SEA passenger traffic", ["BOS", "SEA"]),
    ("tell me about sfo", ["SFO"]),
    ("compare lax and sna", ["LAX", "SNA"]),
    ("what is the ROI for the top airport", []),
    ("Which airports are in Oregon", []),
    ("show me the FAA data for JFK", ["JFK"]),
])
def test_codes_in_text_ignores_english_words_and_acronyms(engine, text, codes):
    assert engine.registry.codes_in_text(text) == codes


@pytest.mark.parametrize("text,places", [
    ("Compare LA and Santa Ana airport congestion levels.", {"LAX", "SNA"}),
    ("What is the percentage of long haul flights out of Anchorage airport?", {"ANC"}),
    ("Boston versus Providence", {"BOS", "PVD"}),
    ("How is Los Angeles doing", {"LAX"}),
])
def test_places_in_text_resolves_metro_aliases_and_cities(engine, text, places):
    assert set(engine.registry.places_in_text(text)) == places


@pytest.mark.parametrize("text,states", [
    ("Which airports in New England are strong candidates for terminal expansion?", NEW_ENGLAND),
    ("top airports in Texas", ["TX"]),
    ("fastest growing airports in CA", ["CA"]),
    ("Which airports in Oregon and Maine", ["OR", "ME"]),
    ("airports in the Pacific Northwest", ["OR", "WA", "ID"]),
    ("what about Washington state", ["WA"]),
    ("Compare BOS and SEA passenger traffic", []),   # SEA is an airport, not a state
    ("tell me about ME", []),                          # bare code without context is not a state
])
def test_states_in_text(engine, text, states):
    assert engine.registry.states_in_text(text) == states


def test_washington_state_does_not_become_dc_airports(engine):
    resolved = engine.registry.resolve("what about Washington state")
    assert resolved["states"] == ["WA"] and resolved["places"] == []


def test_resolve_returns_codes_places_and_states_without_duplicates(engine):
    resolved = engine.registry.resolve("Compare SFO with San Francisco and Boston in Massachusetts")
    assert resolved["codes"] == ["SFO"] and resolved["places"] == ["BOS"] and resolved["states"] == ["MA"]
