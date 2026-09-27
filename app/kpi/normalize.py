"""Normalization helpers shared by every deterministic score.

All signals become national percentiles (0-100) after winsorizing extreme values, so
one outlier airport cannot compress the scale for everyone else. Missing components
are never imputed: weights are renormalized over what is available and the caller
records which components were missing.
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd


def winsorize(series: pd.Series, lower: float = 0.05, upper: float = 0.95) -> pd.Series:
    values = series.astype(float)
    valid = values.dropna()
    if len(valid) < 3:
        return values
    lo, hi = valid.quantile(lower), valid.quantile(upper)
    return values.clip(lower=lo, upper=hi)


def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Rank-based percentile on 0-100; ties share the average rank; constant series -> 50."""
    values = series.astype(float)
    valid = values.dropna()
    result = pd.Series(np.nan, index=values.index, dtype=float)
    if valid.empty:
        return result
    if valid.nunique() == 1 or len(valid) == 1:
        result.loc[valid.index] = 50.0
        return result
    ranks = valid.rank(method="average", ascending=higher_is_better)
    result.loc[valid.index] = (ranks - 1.0) / (len(valid) - 1.0) * 100.0
    return result


def normalized_signal(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    return percentile_rank(winsorize(series), higher_is_better)


def weighted_score(components: Mapping[str, Tuple[Optional[float], float]]) -> Dict[str, object]:
    """Combine component scores (0-100) with weights, renormalizing over available ones.

    ``components`` maps name -> (score or None, weight). Returns the score, the weights
    actually used, and the list of missing components.
    """
    def _has_value(v: Tuple[Optional[float], float]) -> bool:
        return v[0] is not None and not (isinstance(v[0], float) and np.isnan(v[0]))

    # Components with a zero weight are deliberately excluded (sensitivity variants), not "missing".
    weighted = {k: v for k, v in components.items() if v[1] > 0}
    available = {k: v for k, v in weighted.items() if _has_value(v)}
    missing = [k for k in weighted if k not in available]
    total_weight = sum(w for _, w in available.values())
    if not available or total_weight <= 0:
        return {"score": None, "weights_used": {}, "missing": missing}
    weights_used = {k: w / total_weight for k, (_, w) in available.items()}
    score = sum(available[k][0] * weights_used[k] for k in available)
    return {"score": round(float(score), 1), "weights_used": {k: round(w, 3) for k, w in weights_used.items()}, "missing": missing}


def mean_available(values: List[Optional[float]]) -> Optional[float]:
    clean = [float(v) for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return float(np.mean(clean)) if clean else None


def cagr(start: Optional[float], end: Optional[float], years: int) -> Optional[float]:
    """Compound annual growth rate in percent; None when undefined."""
    if start is None or end is None or years <= 0:
        return None
    if not (start > 0) or not (end >= 0) or np.isnan(start) or np.isnan(end):
        return None
    return (float(end) / float(start)) ** (1.0 / years) * 100.0 - 100.0


def pct_change(start: Optional[float], end: Optional[float]) -> Optional[float]:
    if start is None or end is None or not (start > 0) or np.isnan(start) or np.isnan(end):
        return None
    return (float(end) / float(start) - 1.0) * 100.0


def safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or not (denominator > 0):
        return None
    if np.isnan(numerator) or np.isnan(denominator):
        return None
    return float(numerator) / float(denominator)


def confidence_level(missing: List[str], join_gaps: List[str], total_components: int) -> str:
    penalties = len(missing) + len(join_gaps)
    if penalties == 0:
        return "high"
    if penalties == 1 and total_components >= 3:
        return "medium"
    return "low"
