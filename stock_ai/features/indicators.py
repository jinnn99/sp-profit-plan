"""기술적 지표 — 순수 pandas 구현.

외부 라이브러리(pandas-ta 등) 의존을 피하고 직접 계산한다.
모든 지표는 '해당 시점까지의 과거 데이터만' 사용하므로 미래참조 편향이 없다.
입력은 종가 Series 또는 OHLCV 데이터프레임이다.
"""
from __future__ import annotations

import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    """단순이동평균(Simple Moving Average)."""
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, window: int) -> pd.Series:
    """지수이동평균(Exponential Moving Average)."""
    return close.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI(상대강도지수). Wilder 평활(EMA alpha=1/window) 방식.

    0~100 범위. 통상 70 이상 과매수, 30 이하 과매도로 본다.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    out = 100 - (100 / (1 + rs))
    # 손실이 0이면 RSI=100 으로 정의
    out = out.where(avg_loss != 0, 100.0)
    return out.astype(float)


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD. 반환 컬럼: macd, signal, hist(히스토그램)."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def add_indicators(df: pd.DataFrame, indicators: dict | None = None) -> pd.DataFrame:
    """OHLCV 데이터프레임에 지정한 지표 컬럼을 덧붙여 반환한다.

    Args:
        df: open/high/low/close/volume 컬럼을 가진 데이터프레임.
        indicators: 추가할 지표 설정. 예:
            {"sma": [20, 50], "rsi": [14], "macd": True}
            None 이면 sma 20/50, rsi 14 를 기본 추가.

    Returns:
        원본 + 지표 컬럼이 붙은 새 데이터프레임.
    """
    if indicators is None:
        indicators = {"sma": [20, 50], "rsi": [14]}

    out = df.copy()
    close = out["close"]

    for w in indicators.get("sma", []):
        out[f"sma_{w}"] = sma(close, w)
    for w in indicators.get("ema", []):
        out[f"ema_{w}"] = ema(close, w)
    for w in indicators.get("rsi", []):
        out[f"rsi_{w}"] = rsi(close, w)
    if indicators.get("macd"):
        m = macd(close)
        out["macd"] = m["macd"]
        out["macd_signal"] = m["signal"]
        out["macd_hist"] = m["hist"]

    return out
