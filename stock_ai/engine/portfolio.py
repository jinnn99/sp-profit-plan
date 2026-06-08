"""포트폴리오 백테스트 — 점수 상위 N종목 월별 리밸런스.

추천 로직("매월 점수 상위 종목을 동일가중 보유")이 과거에 어땠는지 검증한다.

★정직한 한계(리포트에 명시):
재무·감성 점수는 '현재 시점' 데이터만 무료로 얻을 수 있어, 과거 시점의 재무를
그대로 재현하면 미래참조(look-ahead)가 된다. 그래서 과거 검증에서는 가격으로만
계산 가능한 **추세·모멘텀 점수**를 사용한다(point-in-time 안전).
종합점수(5축)는 '현재 추천'에만 쓰고, 과거 검증은 추세 프록시로 한다.

    미래참조 방지: 점수는 t시점까지의 가격만 사용한다. 종가 패널만 있으므로
    t+1일 종가에 리밸런스했다고 보고 새 비중의 수익은 t+2일부터 반영한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from stock_ai.report.metrics import _cagr, _max_drawdown, _sharpe, _sortino


@dataclass
class PortfolioResult:
    equity: pd.Series
    returns: pd.Series
    benchmark_equity: pd.Series | None
    weights: pd.DataFrame
    metrics: dict
    top_n: int
    equal_weight_equity: pd.Series | None = None  # 분석종목 동일가중(선택 효과 가늠용)
    oos_metrics: dict | None = None               # 아웃오브샘플(뒤 30%) 성과
    split_date: str | None = None                 # 인샘플/OOS 경계일


def momentum_score(panel_to_date: pd.DataFrame) -> pd.Series:
    """가격만으로 계산하는 추세·모멘텀 점수(과거 검증용, look-ahead 없음).

    점수 = 12개월 수익률, 단 200일선 아래면 큰 감점(추세 추종).
    """
    if len(panel_to_date) < 60:
        return pd.Series(dtype=float)
    last = panel_to_date.iloc[-1]
    lookback = panel_to_date.iloc[-252] if len(panel_to_date) >= 252 else panel_to_date.iloc[0]
    mom = last / lookback - 1.0
    sma200 = panel_to_date.tail(200).mean()
    above = last > sma200
    score = mom.where(above, mom - 1.0)   # 200일선 아래면 -100%p 감점
    return score.dropna()


def run_score_portfolio(
    panel: pd.DataFrame,
    score_fn=momentum_score,
    top_n: int = 10,
    initial_cash: float = 10_000.0,
    commission: float = 0.001,
    benchmark_close: pd.Series | None = None,
    full_history_only: bool = True,   # 시작 시점에 이미 상장된 종목만 (최근 IPO 편향 완화)
    rebalance: str = "QE",            # 분기 리밸런스(장기 운용·과최적화 완화). "ME"=월간
    backtest_top_n: int | None = None,  # 백테스트 분산(없으면 max(top_n,30))
) -> PortfolioResult:
    """종가 패널로 '점수 상위 N 분기 리밸런스' 백테스트(생존편향 완화 버전).

    Args:
        panel: 종가 데이터프레임(index=date, columns=ticker, 결측 NaN).
        score_fn: panel(시점까지) → 점수 Series 함수.
        top_n: (참고) 추천 종목 수.
        full_history_only: True 면 시작 무렵 이미 상장돼 있던 종목만 검증(최근 편입 급등주 제외).
        rebalance: 리밸런스 주기. "QE"(분기)·"ME"(월).
        backtest_top_n: 백테스트 보유 종목 수(분산). 기본 max(top_n, 30).
    """
    panel = panel.sort_index()
    bt_n = backtest_top_n or max(top_n, 30)

    # ── 생존편향 완화 ①: 시작 무렵(첫 20거래일 내) 이미 상장돼 있던 종목만 ──
    if full_history_only and len(panel) > 40:
        start_cut = panel.index[20]
        keep = [c for c in panel.columns
                if (fv := panel[c].first_valid_index()) is not None and fv <= start_cut]
        if len(keep) >= 20:
            panel = panel[keep]

    rets = panel.pct_change().fillna(0.0)

    # 리밸런스 날짜(분기말 등, 패널에 존재하는 마지막 영업일)
    period_ends = panel.resample(rebalance).last().index
    rebal_dates = [panel.index[panel.index.get_indexer([d], method="ffill")[0]]
                   for d in period_ends if d >= panel.index[0]]
    rebal_dates = sorted(set(d for d in rebal_dates if d in panel.index))

    weights = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    turnover = pd.Series(0.0, index=panel.index)

    prev_w = pd.Series(0.0, index=panel.columns)
    for d in rebal_dates:
        scores = score_fn(panel.loc[:d])
        scores = scores.dropna()
        if scores.empty:
            continue
        picks = scores.sort_values(ascending=False).head(bt_n).index
        target = pd.Series(0.0, index=panel.columns)
        if len(picks) > 0:
            target[picks] = 1.0 / len(picks)
        # 종가 패널만 있으므로 다음 영업일 종가에 매매했다고 보고,
        # 새 비중은 그 다음 영업일 수익률부터 반영한다(미래참조/overnight 낙관 방지).
        loc = panel.index.get_loc(d)
        if loc + 2 >= len(panel.index):
            continue
        trade_date = panel.index[loc + 1]
        eff_from = panel.index[loc + 2]
        weights.loc[eff_from:] = target.values
        turnover.loc[trade_date] += float((target - prev_w).abs().sum())
        prev_w = target

    # 일별 포트폴리오 수익률 - 리밸런스일 거래비용 차감
    port_ret = (weights * rets).sum(axis=1) - turnover * commission
    equity = (1.0 + port_ret).cumprod() * initial_cash
    equity.name = "equity"
    port_ret.name = "returns"

    bench_equity = None
    if benchmark_close is not None and not benchmark_close.empty:
        b = benchmark_close.reindex(panel.index).ffill().dropna()
        if not b.empty:
            bench_equity = (b / b.iloc[0]) * initial_cash
            bench_equity.name = "benchmark"

    # 동일가중(분석 종목 전체를 매일 똑같이) — '종목 선택'이 더한 가치를 가늠하는 잣대.
    # 전략이 이걸 못 이기면, 좋은 성과는 선택 능력이 아니라 그냥 이 종목들에 묻어간 것.
    ew_ret = rets.mean(axis=1, skipna=True)
    equal_weight_equity = (1.0 + ew_ret).cumprod() * initial_cash
    equal_weight_equity.name = "equal_weight"

    metrics = {
        "총수익률": float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0,
        "CAGR": _cagr(equity),
        "연변동성": float(port_ret.std() * np.sqrt(252)),
        "Sharpe": _sharpe(port_ret),
        "Sortino": _sortino(port_ret),
        "최대낙폭(MDD)": _max_drawdown(equity),
        "시작일": str(equity.index[0].date()),
        "종료일": str(equity.index[-1].date()),
        "동일가중_총수익률": float(equal_weight_equity.iloc[-1] / equal_weight_equity.iloc[0] - 1),
        "동일가중_CAGR": _cagr(equal_weight_equity),
        "보유종목수": int(panel.shape[1]),
        "리밸런스": rebalance,
    }
    # 정직한 헤드라인: 전략 − 동일가중 (둘 다 같은 생존편향 → 차이가 '선택'의 가치)
    metrics["선택초과_총수익률"] = metrics["총수익률"] - metrics["동일가중_총수익률"]
    if bench_equity is not None:
        metrics["벤치마크_총수익률"] = float(bench_equity.iloc[-1] / bench_equity.iloc[0] - 1)
        metrics["벤치마크_CAGR"] = _cagr(bench_equity)
        metrics["벤치마크_MDD"] = _max_drawdown(bench_equity)
        metrics["초과수익률"] = metrics["총수익률"] - metrics["벤치마크_총수익률"]

    # ── 아웃오브샘플(OOS): 뒤 30% 기간만 따로 평가 (정직한 신뢰 지표) ──
    oos_metrics = None
    split_date = None
    n_idx = len(equity)
    if n_idx > 60:
        split = int(n_idx * 0.7)
        split_date = str(equity.index[split].date())

        def _seg(series):
            if series is None:
                return None
            seg = series.iloc[split:]
            if len(seg) < 2 or seg.iloc[0] == 0:
                return None
            return seg / seg.iloc[0]  # OOS 시작=1로 재정규화

        seg_strat = _seg(equity)
        seg_bench = _seg(bench_equity)
        seg_ew = _seg(equal_weight_equity)
        if seg_strat is not None:
            oos_metrics = {
                "기간": f"{split_date} ~ {str(equity.index[-1].date())}",
                "전략_총수익률": float(seg_strat.iloc[-1] - 1),
                "전략_MDD": _max_drawdown(seg_strat),
            }
            if seg_bench is not None:
                oos_metrics["SPY_총수익률"] = float(seg_bench.iloc[-1] - 1)
            if seg_ew is not None:
                oos_metrics["동일가중_총수익률"] = float(seg_ew.iloc[-1] - 1)
                oos_metrics["선택초과_총수익률"] = oos_metrics["전략_총수익률"] - oos_metrics["동일가중_총수익률"]

    return PortfolioResult(
        equity=equity, returns=port_ret, benchmark_equity=bench_equity,
        weights=weights, metrics=metrics, top_n=top_n,
        equal_weight_equity=equal_weight_equity,
        oos_metrics=oos_metrics, split_date=split_date,
    )
