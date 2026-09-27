import math

import pandas as pd
import pytest

from app.kpi.normalize import cagr, confidence_level, mean_available, normalized_signal, pct_change, percentile_rank, weighted_score, winsorize


def test_percentile_rank_spans_0_to_100_and_handles_direction():
    s = pd.Series([10.0, 20.0, 30.0, 40.0])
    up = percentile_rank(s)
    assert up.tolist() == [0.0, pytest.approx(33.33, abs=0.01), pytest.approx(66.67, abs=0.01), 100.0]
    down = percentile_rank(s, higher_is_better=False)
    assert down.tolist()[0] == 100.0 and down.tolist()[-1] == 0.0


def test_constant_or_single_value_series_becomes_50():
    assert percentile_rank(pd.Series([5.0, 5.0, 5.0])).tolist() == [50.0, 50.0, 50.0]
    assert percentile_rank(pd.Series([7.0])).tolist() == [50.0]


def test_percentile_rank_keeps_nan_and_ties_share_rank():
    s = pd.Series([1.0, float("nan"), 2.0, 2.0])
    r = percentile_rank(s)
    assert math.isnan(r.iloc[1])
    assert r.iloc[2] == r.iloc[3]


def test_winsorize_clips_outliers_only_with_enough_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 1000.0])
    w = winsorize(s)
    assert w.max() < 1000.0 and w.min() >= 1.0
    assert winsorize(pd.Series([1.0, 1000.0])).max() == 1000.0


def test_normalized_signal_outlier_does_not_compress_scale():
    s = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 5000], dtype=float)
    n = normalized_signal(s)
    assert n.iloc[-1] == 100.0 and n.iloc[0] == 0.0


def test_weighted_score_renormalizes_over_available_components():
    full = weighted_score({"a": (100.0, 0.5), "b": (0.0, 0.5)})
    assert full["score"] == 50.0 and full["missing"] == []
    partial = weighted_score({"a": (80.0, 0.3), "b": (None, 0.7)})
    assert partial["score"] == 80.0 and partial["missing"] == ["b"] and partial["weights_used"] == {"a": 1.0}
    assert weighted_score({"a": (None, 1.0)})["score"] is None


def test_growth_helpers():
    assert cagr(100, 200, 10) == pytest.approx(7.177, abs=0.01)
    assert cagr(0, 100, 5) is None and cagr(100, 50, 0) is None
    assert pct_change(200, 250) == 25.0 and pct_change(0, 5) is None
    assert mean_available([None, 10.0, 20.0]) == 15.0 and mean_available([None]) is None


def test_confidence_levels():
    assert confidence_level([], [], 4) == "high"
    assert confidence_level(["x"], [], 4) == "medium"
    assert confidence_level(["x"], ["gap"], 4) == "low"
