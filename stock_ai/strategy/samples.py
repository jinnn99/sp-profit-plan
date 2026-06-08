"""예시 전략 모음.

Phase 1 에서는 이동평균 교차(SMA cross)와 RSI 반전 전략을 제공한다.
새 전략은 Strategy 를 상속해 generate_signals 를 구현하고 REGISTRY 에 등록하면 된다.
"""
from __future__ import annotations

import pandas as pd

from stock_ai.features.indicators import rsi, sma
from stock_ai.strategy.base import Strategy


class SmaCross(Strategy):
    """이동평균 교차 전략.

    단기 SMA 가 장기 SMA 위에 있으면 매수(1.0), 아니면 현금(0.0).
    추세추종의 가장 기본형.
    """

    name = "sma_cross"

    def __init__(self, fast: int = 20, slow: int = 50):
        if fast >= slow:
            raise ValueError("fast 는 slow 보다 작아야 합니다.")
        self.fast = fast
        self.slow = slow

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast = sma(df["close"], self.fast)
        slow = sma(df["close"], self.slow)
        signal = (fast > slow).astype(float)
        # 지표가 아직 계산 안 된 초기 구간은 현금(0)
        signal[slow.isna() | fast.isna()] = 0.0
        signal.name = "position"
        return signal


class RsiReversion(Strategy):
    """RSI 평균회귀 전략.

    RSI 가 oversold(기본 30) 아래로 내려가면 매수, overbought(기본 70) 위로
    올라오면 청산. 그 사이에는 직전 포지션을 유지한다.
    """

    name = "rsi_reversion"

    def __init__(self, window: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        self.window = window
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        r = rsi(df["close"], self.window)
        pos = pd.Series(index=df.index, dtype=float)
        current = 0.0
        for i, val in enumerate(r):
            if pd.notna(val):
                if val <= self.oversold:
                    current = 1.0
                elif val >= self.overbought:
                    current = 0.0
            pos.iloc[i] = current
        pos.name = "position"
        return pos


# 전략 이름 → (클래스, 기본 파라미터) 등록표
REGISTRY: dict[str, type[Strategy]] = {
    SmaCross.name: SmaCross,
    RsiReversion.name: RsiReversion,
}


def get_strategy(name: str, **kwargs) -> Strategy:
    """이름으로 전략 인스턴스를 만든다.

    Args:
        name: REGISTRY 의 키 (예: "sma_cross").
        **kwargs: 전략 생성자 인자 (예: fast=10, slow=30).
    """
    if name not in REGISTRY:
        avail = ", ".join(REGISTRY)
        raise KeyError(f"알 수 없는 전략 '{name}'. 사용 가능: {avail}")
    return REGISTRY[name](**kwargs)
