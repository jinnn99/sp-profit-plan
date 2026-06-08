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
    # value
    pe: float = np.nan          # P/E (낮을수록 저평가)
    pb: float = np.nan          # P/B
    # quality
    roe: float = np.nan
    net_margin: float = np.nan
    debt_ratio: float = np.nan  # 낮을수록 좋다
    # growth
    revenue_growth: float = np.nan
    eps_growth: float = np.nan
    # trend
    above_200d: float = np.nan  # (현재가/200일선 - 1)
    momentum_12m: float = np.nan
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


def build_factor_raw(
    ticker: str,
    fundamentals: Fundamentals,
    prices: pd.DataFrame | None,
    sentiment: float | None,
    sector: str = "",
    name: str = "",
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

    # --- quality ---
    fr.roe = _safe(fundamentals.roe)
    fr.net_margin = _safe(fundamentals.net_margin)
    fr.debt_ratio = _safe(fundamentals.debt_ratio)

    # --- growth ---
    fr.revenue_growth = _safe(fundamentals.revenue_growth)
    fr.eps_growth = _safe(fundamentals.eps_growth)

    # --- trend ---
    fr.above_200d, fr.momentum_12m = compute_trend(prices)

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
