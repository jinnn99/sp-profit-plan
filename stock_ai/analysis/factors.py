"""5축 팩터의 원천 값(raw)을 종목별로 모은다.

축:
  - value:     저평가일수록 좋다 → -P/E, -P/B (음수로 저장: 클수록 저평가)
  - quality:   ROE, 순이익률, -부채비율
  - growth:    매출성장률, EPS성장률
  - trend:     200일선 대비 위치, 12개월 모멘텀
  - sentiment: 뉴스 감성점수

여기서는 '원천 지표'만 계산한다. 종목 간 비교(표준화)와 가중합은 score.py 가 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from stock_ai.data.fundamentals import Fundamentals


@dataclass
class FactorRaw:
    """한 종목의 축별 원천 값(없으면 NaN). 각 값은 '클수록 좋다' 방향으로 정렬."""

    ticker: str
    # value (낮을수록 저평가인 비율 + 높을수록 좋은 수익률)
    pe: float = np.nan          # P/E (낮을수록 저평가)
    pb: float = np.nan          # P/B
    ps: float = np.nan          # P/S (낮을수록 저평가)
    ev_ebitda: float = np.nan   # EV/EBITDA (낮을수록 저평가)
    fcf_yield: float = np.nan   # FCF/시가총액 (높을수록 좋다)
    div_yield: float = np.nan   # 배당/시가총액 (높을수록 좋다)
    # quality
    roe: float = np.nan
    roa: float = np.nan
    net_margin: float = np.nan
    gross_margin: float = np.nan
    op_margin: float = np.nan
    current_ratio: float = np.nan
    interest_coverage: float = np.nan
    piotroski: float = np.nan    # 0~9 (높을수록 건전)
    debt_ratio: float = np.nan  # 낮을수록 좋다
    # growth
    revenue_growth: float = np.nan
    eps_growth: float = np.nan
    revenue_cagr: float = np.nan
    eps_cagr: float = np.nan
    # trend / risk (추세 축에 위험조정 통합)
    above_200d: float = np.nan  # (현재가/200일선 - 1)
    momentum_12m: float = np.nan
    momentum_6m: float = np.nan
    momentum_3m: float = np.nan
    dist_52w_high: float = np.nan   # 현재가/52주고점 - 1 (0에 가까울수록 강세)
    volatility: float = np.nan      # 연율 변동성 (낮을수록 좋다)
    max_drawdown: float = np.nan    # 최대낙폭 크기(양수, 낮을수록 좋다)
    beta: float = np.nan            # 시장 베타 (낮을수록 안정)
    # sentiment
    sentiment: float = np.nan
    # 보조(리포트용)
    price: float = np.nan
    sector: str = ""
    name: str = ""
    notes: list[str] = field(default_factory=list)


def _safe(x):
    return np.nan if x is None else float(x)


def compute_trend(prices: pd.DataFrame) -> tuple[float, float]:
    """가격 데이터프레임에서 (200일선 대비 위치, 12개월 모멘텀)을 계산한다."""
    if prices is None or prices.empty:
        return np.nan, np.nan
    close = prices["close"].dropna()
    if len(close) < 30:
        return np.nan, np.nan
    last = float(close.iloc[-1])
    sma200 = float(close.tail(200).mean()) if len(close) >= 200 else float(close.mean())
    above = (last / sma200 - 1.0) if sma200 > 0 else np.nan
    # 12개월(약 252거래일) 모멘텀
    if len(close) >= 252:
        mom = last / float(close.iloc[-252]) - 1.0
    else:
        mom = last / float(close.iloc[0]) - 1.0
    return above, mom


def compute_risk(prices: pd.DataFrame, benchmark: pd.Series | None = None) -> dict:
    """가격(+벤치마크)에서 위험·다기간 모멘텀 지표를 계산한다(추가 네트워크 0)."""
    out = {
        "momentum_6m": np.nan, "momentum_3m": np.nan, "dist_52w_high": np.nan,
        "volatility": np.nan, "max_drawdown": np.nan, "beta": np.nan,
    }
    if prices is None or prices.empty:
        return out
    close = prices["close"].dropna()
    if len(close) < 30:
        return out
    last = float(close.iloc[-1])
    if len(close) >= 63:
        out["momentum_3m"] = last / float(close.iloc[-63]) - 1.0
    if len(close) >= 126:
        out["momentum_6m"] = last / float(close.iloc[-126]) - 1.0
    window = close.tail(252)
    hi = float(window.max())
    if hi > 0:
        out["dist_52w_high"] = last / hi - 1.0           # ≤0, 0에 가까울수록 강세
    rets = close.pct_change().dropna()
    if len(rets) >= 30:
        out["volatility"] = float(rets.std()) * (252 ** 0.5)
        roll_max = window.cummax()
        out["max_drawdown"] = float((1.0 - window / roll_max).max())  # 양수 크기
    if benchmark is not None and len(rets) >= 60:
        bret = benchmark.reindex(close.index).pct_change().dropna()
        joined = pd.concat([rets, bret], axis=1, join="inner").dropna()
        if len(joined) >= 60:
            var_b = float(joined.iloc[:, 1].var())
            if var_b > 0:
                cov = float(joined.iloc[:, 0].cov(joined.iloc[:, 1]))
                out["beta"] = cov / var_b
    return out


def build_factor_raw(
    ticker: str,
    fundamentals: Fundamentals,
    prices: pd.DataFrame | None,
    sentiment: float | None,
    sector: str = "",
    name: str = "",
    benchmark: pd.Series | None = None,
) -> FactorRaw:
    """종목 하나의 원천 팩터 값을 조립한다.

    P/E, P/B 는 현재가 + SEC 발행주식수/EPS/자기자본으로 계산한다.
    """
    fr = FactorRaw(ticker=ticker, sector=sector, name=name)

    last_price = np.nan
    if prices is not None and not prices.empty:
        last_price = float(prices["close"].dropna().iloc[-1])
    fr.price = last_price

    # --- value: P/E, P/B ---
    if not np.isnan(last_price):
        if fundamentals.eps and fundamentals.eps > 0:
            fr.pe = last_price / fundamentals.eps
        if fundamentals.equity and fundamentals.shares and fundamentals.shares > 0:
            book_per_share = fundamentals.equity / fundamentals.shares
            if book_per_share > 0:
                fr.pb = last_price / book_per_share
        # 시가총액 기반 밸류(P/S·FCF수익률·EV/EBITDA·배당수익률)
        shares = fundamentals.shares
        mktcap = last_price * shares if shares and shares > 0 else np.nan
        if mktcap == mktcap and mktcap > 0:
            if fundamentals.revenue and fundamentals.revenue > 0:
                fr.ps = mktcap / fundamentals.revenue
            if fundamentals.fcf is not None:
                fr.fcf_yield = fundamentals.fcf / mktcap
            if fundamentals.dividends_paid is not None:
                fr.div_yield = fundamentals.dividends_paid / mktcap
            if fundamentals.ebitda and fundamentals.ebitda > 0:
                ev = mktcap + (fundamentals.total_debt or 0.0) - (fundamentals.cash or 0.0)
                fr.ev_ebitda = ev / fundamentals.ebitda

    # --- quality ---
    fr.roe = _safe(fundamentals.roe)
    fr.roa = _safe(fundamentals.roa)
    fr.net_margin = _safe(fundamentals.net_margin)
    fr.gross_margin = _safe(fundamentals.gross_margin)
    fr.op_margin = _safe(fundamentals.op_margin)
    fr.current_ratio = _safe(fundamentals.current_ratio)
    fr.interest_coverage = _safe(fundamentals.interest_coverage)
    fr.piotroski = _safe(fundamentals.piotroski)
    fr.debt_ratio = _safe(fundamentals.debt_ratio)

    # --- growth ---
    fr.revenue_growth = _safe(fundamentals.revenue_growth)
    fr.eps_growth = _safe(fundamentals.eps_growth)
    fr.revenue_cagr = _safe(fundamentals.revenue_cagr)
    fr.eps_cagr = _safe(fundamentals.eps_cagr)

    # --- trend / risk ---
    fr.above_200d, fr.momentum_12m = compute_trend(prices)
    risk = compute_risk(prices, benchmark)
    fr.momentum_6m = risk["momentum_6m"]
    fr.momentum_3m = risk["momentum_3m"]
    fr.dist_52w_high = risk["dist_52w_high"]
    fr.volatility = risk["volatility"]
    fr.max_drawdown = risk["max_drawdown"]
    fr.beta = risk["beta"]

    # --- sentiment ---
    fr.sentiment = _safe(sentiment)

    # 데이터 결손 메모(리포트 투명성용)
    if np.isnan(fr.pe):
        fr.notes.append("P/E 없음(적자 또는 데이터 결손)")
    if np.isnan(fr.roe):
        fr.notes.append("재무(ROE) 데이터 결손")
    if np.isnan(fr.sentiment):
        fr.notes.append("최근 뉴스 없음")
    return fr
