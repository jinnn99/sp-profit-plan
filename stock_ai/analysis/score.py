"""종합 점수 엔진 — 횡단면 표준화 + 가중합.

원천 팩터(factors.FactorRaw)를 S&P500 '집단 내 상대평가'로 0~100 서브점수로 바꾼 뒤,
가중합해 종합점수(0~100)를 만든다.

상대평가(percentile rank)를 쓰는 이유: 절대값(예: ROE 15%)이 좋은지 나쁜지는
시장 전체와 비교해야 의미가 있기 때문이다. 같은 날 같은 집단 안에서만 비교하므로
미래참조 편향도 없다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.analysis.factors import FactorRaw
from stock_ai.config import DEFAULT_FACTOR_WEIGHTS

# 축 → (지표컬럼, 높을수록좋은가) 목록. 한 축의 여러 지표는 백분위 평균.
_AXIS_METRICS = {
    "value": [("pe", False), ("pb", False)],                  # 낮을수록 저평가=좋음
    "quality": [("roe", True), ("net_margin", True), ("debt_ratio", False)],
    "growth": [("revenue_growth", True), ("eps_growth", True)],
    "trend": [("above_200d", True), ("momentum_12m", True)],
    "sentiment": [("sentiment", True)],
}


def _pct_score(series: pd.Series, higher_is_better: bool) -> pd.Series:
    """집단 내 백분위(0~100). 결측은 일단 NaN 유지(상위에서 처리)."""
    # 극단 이상치 영향 완화를 위해 순위(rank) 기반 백분위 사용
    ranked = series.rank(pct=True, ascending=higher_is_better)
    return ranked * 100.0


def _to_frame(raws: list[FactorRaw]) -> pd.DataFrame:
    rows = []
    for r in raws:
        rows.append({
            "ticker": r.ticker, "name": r.name, "sector": r.sector, "price": r.price,
            "pe": r.pe, "pb": r.pb, "roe": r.roe, "net_margin": r.net_margin,
            "debt_ratio": r.debt_ratio, "revenue_growth": r.revenue_growth,
            "eps_growth": r.eps_growth, "above_200d": r.above_200d,
            "momentum_12m": r.momentum_12m, "sentiment": r.sentiment,
            "notes": "; ".join(r.notes),
        })
    return pd.DataFrame(rows).set_index("ticker")


def compute_scores(
    raws: list[FactorRaw],
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """원천 팩터 리스트 → 축별 서브점수 + 종합점수 데이터프레임.

    Returns:
        인덱스=ticker. 컬럼: name, sector, price, 각 축 raw 지표,
        score_value/quality/growth/trend/sentiment, coverage, composite.
        composite 내림차순 정렬.
    """
    if not raws:
        return pd.DataFrame()

    weights = dict(weights or DEFAULT_FACTOR_WEIGHTS)
    wsum = sum(weights.values()) or 1.0
    weights = {k: v / wsum for k, v in weights.items()}  # 합 1.0 정규화

    df = _to_frame(raws)

    # 축별 서브점수 계산
    axis_scores = {}
    for axis, metrics in _AXIS_METRICS.items():
        parts = []
        for col, higher in metrics:
            parts.append(_pct_score(df[col], higher))
        # 한 축 안에서 지표 백분위 평균(결측 지표는 평균에서 제외)
        axis_df = pd.concat(parts, axis=1)
        axis_scores[axis] = axis_df.mean(axis=1, skipna=True)

    score_df = pd.DataFrame(axis_scores)  # 컬럼: value/quality/...(0~100, 결측 가능)

    # 데이터 커버리지: 5축 중 값이 있는 비율
    coverage = score_df.notna().mean(axis=1)

    # 종합점수: 결측 축은 그 종목의 '있는 축 가중 평균'으로 대체(중립 50 대신,
    # 결측 시 분모를 줄여 과대평가를 방지)
    composite = pd.Series(0.0, index=score_df.index)
    used_weight = pd.Series(0.0, index=score_df.index)
    for axis in _AXIS_METRICS:
        w = weights.get(axis, 0.0)
        col = score_df[axis]
        mask = col.notna()
        composite[mask] += col[mask] * w
        used_weight[mask] += w
    composite = composite / used_weight.replace(0.0, np.nan)

    out = df.copy()
    for axis in _AXIS_METRICS:
        out[f"score_{axis}"] = score_df[axis]
    out["coverage"] = coverage
    out["composite"] = composite

    # 커버리지가 너무 낮은(축 2개 미만) 종목은 신뢰 어려워 후순위로
    out = out.sort_values(["composite"], ascending=False)
    return out
