"""지표 단위 테스트."""
import numpy as np
import pandas as pd

from stock_ai.features.indicators import macd, rsi, sma


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = sma(s, 3)
    # 처음 두 칸은 NaN, 세 번째는 (1+2+3)/3 = 2
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == 2.0
    assert out.iloc[4] == 4.0


def test_rsi_bounds():
    # 꾸준히 상승하면 RSI 가 100 근처여야 한다
    s = pd.Series(np.arange(1, 50, dtype=float))
    r = rsi(s, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()
    assert r.iloc[-1] > 90


def test_macd_columns():
    s = pd.Series(np.linspace(10, 20, 100))
    m = macd(s)
    assert list(m.columns) == ["macd", "signal", "hist"]
    # hist = macd - signal 정의 확인
    valid = m.dropna()
    assert np.allclose(valid["hist"], valid["macd"] - valid["signal"])
