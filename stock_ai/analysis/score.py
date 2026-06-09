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
    # 낮을수록 저평가(False) + 높을수록 좋은 수익률(True)
    "value": [
        ("pe", False), ("pb", False), ("ps", False), ("ev_ebitda", False),
        ("fcf_yield", True), ("div_yield", True),
    ],
    "quality": [
        ("roe", True), ("roa", True), ("net_margin", True), ("gross_margin", True),
        ("op_margin", True), ("current_ratio", True), ("interest_coverage", True),
        ("piotroski", True), ("debt_ratio", False),
    ],
    "growth": [
        ("revenue_growth", True), ("eps_growth", True),
        ("revenue_cagr", True), ("eps_cagr", True),
    ],
    # 추세 + 위험조정(저변동·저낙폭·저베타 우대)
    "trend": [
        ("above_200d", True), ("momentum_12m", True), ("momentum_6m", True),
        ("momentum_3m", True), ("dist_52w_high", True),
        ("volatility", False), ("max_drawdown", False), ("beta", False),
    ],
    "sentiment": [("sentiment", True)],
}

# 한 축 안에서 일부 지표에 가중치를 더 준다(나머지는 1.0). 핵심 지표 강조용.
_METRIC_WEIGHTS = {
    "piotroski": 2.0,   # 종합 재무건전성
    "roe": 1.5, "fcf_yield": 1.5, "momentum_12m": 1.5,
}


# _AXIS_METRICS 에 쓰이는 모든 지표 컬럼(자동 수집).
_ALL_METRIC_COLS = [c for metrics in _AXIS_METRICS.values() for c, _ in metrics]


def _pct_score_sector(series: pd.Series, sectors: pd.Series, higher_is_better: bool,
                      min_n: int = 8) -> pd.Series:
    """섹터 내 백분위(0~100). 같은 섹터 표본이 적으면(또는 섹터 미상) 전체 기준으로 폴백.

    은행 P/E vs 테크 P/E 처럼 섹터마다 정상 범위가 달라, 같은 업종끼리 비교해야
    왜곡이 줄어든다. 순위(rank) 기반이라 이상치에도 강건하다.
    """
    glob = series.rank(pct=True, ascending=higher_is_better) * 100.0
    out = glob.copy()
    for sec, idx in sectors.groupby(sectors).groups.items():
        if not sec:
            continue  # 섹터 미상 → 전체 기준 유지
        sub = series.loc[idx]
        if sub.notna().sum() >= min_n:
            out.loc[idx] = sub.rank(pct=True, ascending=higher_is_better) * 100.0
    return out


def _to_frame(raws: list[FactorRaw]) -> pd.DataFrame:
    rows = []
    for r in raws:
        row = {
            "ticker": r.ticker, "name": r.name, "sector": r.sector,
            "price": r.price, "notes": "; ".join(r.notes),
        }
        for col in _ALL_METRIC_COLS:
            row[col] = getattr(r, col, np.nan)
        rows.append(row)
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

    # 축별 서브점수 계산 — 섹터 상대 백분위의 (지표)가중 평균(결측 지표는 제외)
    sectors = df["sector"].astype("string").fillna("")
    axis_scores = {}
    for axis, metrics in _AXIS_METRICS.items():
        parts = [_pct_score_sector(df[col], sectors, higher) for col, higher in metrics]
        mweights = np.array([_METRIC_WEIGHTS.get(col, 1.0) for col, _ in metrics], dtype=float)
        vals = pd.concat(parts, axis=1).to_numpy(dtype=float)   # rows × metrics
        mask = ~np.isnan(vals)
        num = np.nansum(np.where(mask, vals, 0.0) * mweights, axis=1)
        den = (mask * mweights).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            scores = np.where(den > 0, num / den, np.nan)
        axis_scores[axis] = pd.Series(scores, index=df.index)

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
