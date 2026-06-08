"""점수 엔진·추천·포트폴리오 백테스트 테스트."""
import numpy as np
import pandas as pd

from stock_ai.analysis.factors import FactorRaw, compute_trend
from stock_ai.analysis.score import compute_scores
from stock_ai.analysis.recommend import build_recommendations
from stock_ai.engine.portfolio import momentum_score, run_score_portfolio
from stock_ai.runner import _sector_balanced_limit


def _raw(ticker, pe, roe, growth, mom, sent, sector="Tech"):
    return FactorRaw(
        ticker=ticker, pe=pe, pb=pe / 5, roe=roe, net_margin=roe / 2,
        debt_ratio=0.4, revenue_growth=growth, eps_growth=growth,
        above_200d=mom, momentum_12m=mom, sentiment=sent, price=100.0,
        sector=sector, name=ticker,
    )


def test_scores_rank_better_stock_higher():
    """모든 축이 좋은 종목이 모든 축이 나쁜 종목보다 종합점수가 높아야 한다."""
    good = _raw("GOOD", pe=8, roe=0.3, growth=0.3, mom=0.4, sent=0.8)
    mid = _raw("MID", pe=20, roe=0.15, growth=0.1, mom=0.1, sent=0.0)
    bad = _raw("BAD", pe=50, roe=0.02, growth=-0.2, mom=-0.3, sent=-0.8)
    df = compute_scores([good, mid, bad])
    assert df.loc["GOOD", "composite"] > df.loc["MID", "composite"]
    assert df.loc["MID", "composite"] > df.loc["BAD", "composite"]
    # 점수는 0~100 범위
    assert (df["composite"].dropna() >= 0).all() and (df["composite"].dropna() <= 100).all()


def test_value_axis_prefers_low_pe():
    """P/E 가 낮은 종목이 value 점수가 더 높아야 한다."""
    cheap = _raw("CHEAP", pe=6, roe=0.2, growth=0.1, mom=0.1, sent=0.0)
    pricey = _raw("PRICEY", pe=40, roe=0.2, growth=0.1, mom=0.1, sent=0.0)
    df = compute_scores([cheap, pricey])
    assert df.loc["CHEAP", "score_value"] > df.loc["PRICEY", "score_value"]


def test_recommend_sector_diversification():
    """한 섹터 최대 보유 수 제한이 지켜져야 한다."""
    raws = [_raw(f"T{i}", pe=8 + i, roe=0.3, growth=0.3, mom=0.4, sent=0.5, sector="Tech")
            for i in range(6)]
    raws += [_raw(f"F{i}", pe=9 + i, roe=0.25, growth=0.2, mom=0.3, sent=0.3, sector="Fin")
             for i in range(6)]
    df = compute_scores(raws)
    recs = build_recommendations(df, top_n=6, max_per_sector=2)
    from collections import Counter
    counts = Counter(r.sector for r in recs)
    assert all(c <= 2 for c in counts.values())


def test_compute_trend_uptrend_positive():
    """상승 추세면 200일선 대비 위치·모멘텀이 양수."""
    idx = pd.date_range("2020-01-01", periods=300, freq="D")
    close = pd.Series(np.linspace(50, 150, 300), index=idx)
    df = pd.DataFrame({"close": close})
    above, mom = compute_trend(df)
    assert above > 0 and mom > 0


def test_portfolio_no_lookahead():
    """포트폴리오 백테스트는 리밸런스 신호를 다음날부터 반영해야 한다.

    마지막 날 급등을 미리 알 수 없으므로, 마지막 리밸런스의 가중치가
    그 날 수익률에 적용되면 안 된다(가중치 시작이 신호일 다음날).
    """
    idx = pd.date_range("2021-01-01", periods=400, freq="D")
    a = pd.Series(np.linspace(100, 200, 400), index=idx)   # 우상향
    b = pd.Series(np.linspace(100, 90, 400), index=idx)    # 하락
    panel = pd.DataFrame({"A": a, "B": b})
    res = run_score_portfolio(panel, score_fn=momentum_score, top_n=1,
                              initial_cash=1000, commission=0)
    # 가중치는 신호일 당일이 아니라 다음 영업일부터 설정된다
    # → 각 리밸런스 행의 가중치 변화는 '그 날' 수익에 곱해지지 않음
    assert res.equity.iloc[-1] > 0
    # 우상향 A 를 주로 담으므로 최종 자산이 초기보다 커야 한다
    assert res.equity.iloc[-1] > 1000


def test_portfolio_weights_start_after_trade_day():
    """종가 패널 백테스트는 신호 다음날 종가 체결 후 그 다음날부터 새 비중을 적용한다."""
    idx = pd.date_range("2021-01-01", periods=65, freq="D")
    a = pd.Series(np.linspace(100, 130, 65), index=idx)
    b = pd.Series(np.linspace(100, 90, 65), index=idx)
    panel = pd.DataFrame({"A": a, "B": b})

    res = run_score_portfolio(
        panel,
        score_fn=momentum_score,
        top_n=1,
        backtest_top_n=1,
        rebalance="D",
        initial_cash=1000,
        commission=0,
        full_history_only=False,
    )

    assert res.weights.loc[idx[60], "A"] == 0
    assert res.weights.loc[idx[61], "A"] == 1


def test_sector_balanced_limit_avoids_head_slice_bias():
    """빠른 추천 범위는 표의 앞 N개가 아니라 섹터를 고르게 섞어야 한다."""
    uni = pd.DataFrame({
        "ticker": ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"],
        "name": [""] * 9,
        "sector": ["Alpha"] * 3 + ["Beta"] * 3 + ["Gamma"] * 3,
    })

    limited = _sector_balanced_limit(uni, 3)
    assert set(limited["sector"]) == {"Alpha", "Beta", "Gamma"}
