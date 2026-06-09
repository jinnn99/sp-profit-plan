"""실행 오케스트레이션 — 데이터 → 전략 → 백테스트 → 리포트 한 번에.

CLI 와 테스트가 공통으로 쓰는 진입 함수를 둔다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_ai.data.prices import get_prices
from stock_ai.engine.backtest import BacktestResult, run_backtest
from stock_ai.report.html_report import build_html_report
from stock_ai.report.metrics import compute_metrics
from stock_ai.strategy.samples import get_strategy


def _sector_balanced_limit(uni: pd.DataFrame, limit: int | None) -> pd.DataFrame:
    """분석 범위를 줄일 때 표의 앞부분 편향을 피하기 위한 섹터 균형 샘플."""
    if not limit or limit >= len(uni):
        return uni.copy()
    if limit <= 0:
        return uni.copy()

    uni = uni.copy()
    if "sector" not in uni.columns:
        return uni.sample(n=limit, random_state=42).sort_values("ticker").reset_index(drop=True)

    selected: list[int] = []
    groups = [
        group.sort_values("ticker")
        for _, group in uni.groupby("sector", dropna=False, sort=True)
    ]
    positions = [0] * len(groups)

    while len(selected) < limit:
        progressed = False
        for i, group in enumerate(groups):
            if positions[i] < len(group):
                selected.append(group.index[positions[i]])
                positions[i] += 1
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break

    return uni.loc[selected].reset_index(drop=True)


def backtest_ticker(
    ticker: str,
    strategy: str = "sma_cross",
    start: str | None = "2015-01-01",
    end: str | None = None,
    initial_cash: float = 10_000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
    strategy_kwargs: dict | None = None,
    make_report: bool = True,
) -> tuple[BacktestResult, dict, Path | None]:
    """한 종목을 받아 백테스트하고 (결과, 지표, 리포트경로)를 반환한다."""
    df = get_prices(ticker, start=start, end=end)
    strat = get_strategy(strategy, **(strategy_kwargs or {}))
    signals = strat.generate_signals(df)

    result = run_backtest(
        df, signals,
        initial_cash=initial_cash,
        commission=commission,
        slippage=slippage,
        ticker=ticker.upper(),
        strategy_name=strat.name,
    )
    metrics = compute_metrics(result)

    report_path: Path | None = None
    if make_report:
        report_path = build_html_report(df, result)

    return result, metrics, report_path


def recommend_universe(
    top_n: int = 10,
    limit: int | None = 60,
    start: str = "2015-01-01",
    sentiment_method: str = "lexicon",   # "none" | "lexicon"(가벼움·기본) | "finbert"(고메모리)
    weights: dict | None = None,
    style: str = "balanced",
    make_report: bool = True,
    progress: bool = True,
    refresh_data: bool = False,
    validate: bool = False,
):
    """S&P500(또는 일부)을 종합분석해 추천 + 과거 검증 + 리포트를 만든다.

    Args:
        top_n: 추천 종목 수.
        limit: 분석 종목 수 상한(None/0 = S&P500 전체). 첫 실행 속도용.
        sentiment_method: 뉴스 감성 방식("none" | "lexicon" | "finbert").
        weights: 5축 가중치(없으면 기본).
        refresh_data: True 면 S&P500/SEC 재무 캐시를 새로 받는다.
        validate: True 면 과거 검증(점수 상위 N 리밸런스) 백테스트를 계산한다.
            현재 추천 리포트에는 표시하지 않으므로 기본은 False(불필요한 연산 방지).

    Returns:
        (recommendations, score_df, portfolio_result, report_path)
    """
    from stock_ai.analysis.factors import build_factor_raw
    from stock_ai.analysis.recommend import build_recommendations, build_score_universe
    from stock_ai.analysis.score import compute_scores
    from stock_ai.data.fundamentals import get_fundamentals
    from stock_ai.data.universe import get_sp500
    from stock_ai.engine.portfolio import run_score_portfolio
    from stock_ai.report.recommend_report import build_recommend_report

    uni = get_sp500(refresh=refresh_data)
    universe_size = len(uni)
    if limit:
        uni = _sector_balanced_limit(uni, limit)
    tickers = uni["ticker"].tolist()
    sectors = dict(zip(uni["ticker"], uni.get("sector", "")))
    names = dict(zip(uni["ticker"], uni.get("name", "")))

    raws = []
    price_map: dict[str, pd.Series] = {}
    n = len(tickers)
    from stock_ai.data.fundamentals import Fundamentals
    # 베타(시장 민감도) 계산용 벤치마크(SPY) — 한 번만 받아 모든 종목에 재사용.
    try:
        benchmark_close = get_prices("SPY", start=start)["close"]
    except Exception:
        benchmark_close = None
    failed = []
    for i, t in enumerate(tickers, 1):
        if progress and (i == 1 or i % 10 == 0 or i == n):
            print(f"  분석 {i}/{n} … {t}", flush=True)
        # 한 종목에서 무슨 예외가 나도 전체 실행이 죽지 않도록 통째로 감싼다.
        try:
            try:
                prices = get_prices(t, start=start)
            except Exception:
                prices = None
            if prices is not None and not prices.empty:
                price_map[t] = prices["close"]

            try:
                fund = get_fundamentals(t, refresh=refresh_data)
            except Exception:
                fund = Fundamentals(ticker=t)

            sent = None
            if sentiment_method != "none":
                try:
                    from stock_ai.analysis.sentiment import get_sentiment
                    sent = get_sentiment(t, method=sentiment_method)
                except Exception:
                    sent = None

            raws.append(build_factor_raw(t, fund, prices, sent,
                                         sector=sectors.get(t, ""), name=names.get(t, ""),
                                         benchmark=benchmark_close))
        except Exception as e:
            failed.append(t)
            print(f"  ! {t} 건너뜀: {str(e)[:80]}", flush=True)

    if failed:
        print(f"  (수집 실패 {len(failed)}종목: {', '.join(failed[:15])}{'…' if len(failed)>15 else ''})",
              flush=True)

    # 투자성향 토글(클라이언트 전환)용으로 3개 성향을 미리 계산한다.
    # raws(무거운 부분)는 위에서 한 번만 만들고, 가중치만 바꿔 재점수화하므로 저렴하다.
    from stock_ai.config import FACTOR_WEIGHT_PRESETS
    ux_order = ["balanced", "momentum", "dividend"]
    default_style = style if style in ux_order else "balanced"
    style_recs: dict[str, list] = {}
    score_df = None
    for st in ux_order:
        sdf = compute_scores(raws, weights=FACTOR_WEIGHT_PRESETS[st])
        style_recs[st] = build_recommendations(sdf, top_n=top_n)
        if st == default_style:
            score_df = sdf
    recs = style_recs[default_style]
    # 브라우저 가중치 슬라이더용 전 종목 데이터(서브점수는 가중치 무관이라 한 번만 만든다).
    score_universe = build_score_universe(score_df) if score_df is not None else []
    holding_universe = []
    if score_df is not None and not score_df.empty:
        for ticker, row in score_df.iterrows():
            price = row.get("price")
            holding_universe.append({
                "ticker": str(ticker).upper(),
                "name": str(row.get("name", "") or ""),
                "sector": str(row.get("sector", "") or ""),
                "price": float(price) if pd.notna(price) else None,
            })

    # 과거 검증: 분석 종목 종가 패널 + SPY 벤치마크
    # 주의: 현재 추천 리포트는 이 결과를 렌더링하지 않는다. 전체 S&P500 콜드런에서
    # 매번 무겁게 계산해 버리는 낭비를 막기 위해 validate=True 일 때만 실행한다.
    portfolio_result = None
    if validate and price_map:
        panel = pd.DataFrame(price_map).sort_index()
        try:
            spy = get_prices("SPY", start=start)["close"]
        except Exception:
            spy = None
        try:
            portfolio_result = run_score_portfolio(panel, top_n=top_n, benchmark_close=spy)
        except Exception as e:
            print(f"  포트폴리오 백테스트 건너뜀: {e}")

    report_path = None
    if make_report:
        report_path = build_recommend_report(
            style_recs=style_recs, default_style=default_style,
            portfolio_result=portfolio_result,
            universe_size=universe_size, analyzed=len(tickers),
            holding_universe=holding_universe,
            score_universe=score_universe,
        )
    return recs, score_df, portfolio_result, report_path
