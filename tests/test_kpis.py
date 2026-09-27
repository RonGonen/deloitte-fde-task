"""Deterministic KPI tests on the fixture engine (real data slices, no network)."""
from __future__ import annotations

import pytest

from app.kpi.congestion import WEIGHTS as CONGESTION_WEIGHTS, compare_congestion
from app.kpi.demand import demand_pressure
from app.kpi.long_haul import long_haul_share
from app.kpi.scoring import DEFAULT_WEIGHTS, expansion_scores

NEW_ENGLAND = ["CT", "ME", "MA", "NH", "RI", "VT"]


def test_metrics_table_has_one_row_per_universe_airport_with_expected_columns(table):
    assert table["lid"].is_unique
    for col in ("forecast_cagr_pct", "ops_per_runway", "del15_pct", "nas_share_pct", "avg_taxi_out_min", "recovery_ratio", "upgauging_pct"):
        assert col in table.columns
    sfo = table[table["lid"] == "SFO"].iloc[0]
    assert sfo["slot_level"] == 2 and sfo["runways_qualifying"] == 4 and sfo["has_delay"] and sfo["has_taf"]
    assert sfo["ops_peak_year"] == 2018 and sfo["forecast_vs_peak"] > 1.0
    assert 25 < sfo["del15_pct"] < 40 and 45 < sfo["nas_share_pct"] < 65


def test_weights_sum_to_one():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(CONGESTION_WEIGHTS.values()) == pytest.approx(1.0)


def test_expansion_scores_are_deterministic_ranked_and_bounded(table):
    a = expansion_scores(table, states=NEW_ENGLAND)
    b = expansion_scores(table, states=NEW_ENGLAND)
    assert [x["lid"] for x in a["ranked"]] == [x["lid"] for x in b["ranked"]]
    scores = [x["score"] for x in a["ranked"]]
    assert scores == sorted(scores, reverse=True) and all(0 <= s <= 100 for s in scores)
    assert all(x["state"] in NEW_ENGLAND for x in a["ranked"])
    assert a["ranked"][0]["rank"] == 1 and a["ranked"][0]["lid"] == "BOS"
    assert a["universe_size"] > len(a["ranked"])  # normalization is national, filter applied after


def test_expansion_score_exposes_sub_scores_drivers_and_sensitivity(table):
    top = expansion_scores(table, states=NEW_ENGLAND)["ranked"][0]
    assert set(top["sub_scores"]) == set(DEFAULT_WEIGHTS)
    assert top["drivers"] and {"component", "percentile", "contribution"} <= set(top["drivers"][0])
    assert top["score_without_scale"] is not None and top["score_without_scale"] != top["score"]
    assert top["confidence"] in {"high", "medium", "low"}
    assert top["metrics"]["enplanements"] > 20_000_000


def test_expansion_scores_handle_missing_delay_data_by_renormalizing(table):
    ranked = expansion_scores(table, min_enplanements=100_000, limit=0)["ranked"]
    small = [x for x in ranked if x["metrics"]["del15_pct"] is None]
    assert small, "fixture should include an airport without BTS delay coverage"
    assert all(x["score"] is not None for x in small)
    assert all(x["sub_scores"]["capacity_pressure"] is not None for x in small)  # structural half still available


def test_expansion_scores_custom_weights_and_code_filter(table):
    result = expansion_scores(table, codes=["SFO", "LAX", "SNA"], weights={"scale": 0.0, "forecast_growth": 0.5})
    assert [x["lid"] for x in result["ranked"]] and len(result["ranked"]) == 3
    assert result["weights"]["scale"] == 0.0 and result["weights"]["forecast_growth"] == 0.5
    assert all(x["weights_used"].get("scale") is None for x in result["ranked"])


def test_expansion_scores_empty_universe_returns_message(table):
    result = expansion_scores(table, min_enplanements=10 ** 12)
    assert result["ranked"] == [] and "No primary" in result["message"]


def test_congestion_comparison_orders_by_index_and_reports_raw_metrics(table, engine):
    result = compare_congestion(table, ["SNA", "LAX"], engine.nas_status())
    codes = [a["lid"] for a in result["airports"]]
    assert codes == ["LAX", "SNA"]
    lax, sna = result["airports"]
    assert lax["congestion_index"] > sna["congestion_index"]
    assert lax["metrics"]["slot_level"] == 2 and sna["metrics"]["runways_qualifying"] == 1
    assert lax["metrics"]["weather_share_pct"] is not None  # weather shown next to NAS share
    assert result["not_found"] == [] and "del15_pct" in result["national_medians"]


def test_congestion_unknown_code_is_reported_not_raised(table):
    result = compare_congestion(table, ["LAX", "ZZZ"])
    assert result["not_found"] == ["ZZZ"] and len(result["airports"]) == 1


def test_congestion_live_status_is_attached_but_not_scored(table, engine):
    with_live = compare_congestion(table, ["SFO"], engine.nas_status())
    without = compare_congestion(table, ["SFO"], None)
    assert with_live["airports"][0]["live_status"][0]["reason"] == "low ceilings"
    assert with_live["airports"][0]["congestion_index"] == without["airports"][0]["congestion_index"]


def test_long_haul_share_thresholds_are_monotonic_and_caveated(engine):
    result = long_haul_share(engine.ontime, engine.registry, "ANC", taf_row=engine.row("ANC"))
    shares = [result["shares_by_threshold"][k]["share_pct"] for k in ("1500", "2500", "3000")]
    assert shares[0] >= shares[1] >= shares[2] and result["headline_share_pct"] == shares[2]
    assert result["total_departures"] > 2000 and result["top_routes"][0]["dest"] == "SEA"
    assert any("international" in c.lower() for c in result["caveats"])
    assert result["taf_context"]["international_enplanement_share_pct"] < 5


def test_long_haul_share_handles_unknown_or_uncovered_airport(engine):
    assert "error" in long_haul_share(engine.ontime, engine.registry, "ZZZ")
    assert "error" in long_haul_share(None, engine.registry, "ANC")


def test_demand_pressure_for_sfo_is_high_with_reasons(table):
    result = demand_pressure(table, "SFO")
    assert result["indicator"] > 60 and result["confidence"] == "high"
    assert result["facts"]["slot_level"] == 2 and result["facts"]["forecast_vs_peak"] > 1
    joined = " ".join(result["reasons"])
    assert "Level 2" in joined and "National Airspace System" in joined and "highest-ever" in joined
    assert any("load-factor" in c or "load factor" in c for c in result["caveats"])


def test_demand_pressure_outside_universe_is_explicit(table):
    assert "error" in demand_pressure(table, "DGG")
