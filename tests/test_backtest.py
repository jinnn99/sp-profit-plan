"""백테스트 엔진 단위 테스트 — 특히 미래참조 편향 방지 검증."""
import numpy as np
import pandas as pd

from stock_ai.engine.backtest import run_backtest


def _make_df(prices, opens=None):
    """종가(또는 시가 별도) 리스트로 OHLCV 데이터프레임을 만든다."""
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    o = opens if opens is not None else prices
    return pd.DataFrame({
        "open": o, "high": prices, "low": prices,
        "close": prices, "volume": [1_000] * len(prices),
    }, index=idx)


def test_no_lookahead_signal_executes_next_day():
    """t일 신호는 t+1일 시가에 체결되어야 한다(미래참조 차단).

    가격이 [10, 10, 20, 20] 이고, 신호를 t=1(둘째날)에 처음 1.0 으로 켜면
    체결은 t=2(셋째날) 시가 20 에 일어나야 한다. 만약 미래참조였다면
    t=1의 시가 10 에 체결되어 큰 이익이 났을 것.
    """
    df = _make_df([10, 10, 20, 20])
    signals = pd.Series([0, 1, 1, 1], index=df.index, dtype=float)
    res = run_backtest(df, signals, initial_cash=1000, commission=0, slippage=0)

    # 체결은 셋째날(인덱스2)에 발생해야 한다
    assert not res.trades.empty
    first_buy = res.trades.iloc[0]
    assert first_buy["action"] == "BUY"
    assert first_buy.name == df.index[2]      # t+1 = 셋째날
    assert first_buy["price"] == 20.0          # 그날 시가에 체결


def test_commission_reduces_equity():
    """수수료가 있으면 매매 직후 자산이 줄어야 한다."""
    df = _make_df([100, 100, 100])
    signals = pd.Series([1, 1, 1], index=df.index, dtype=float)
    no_fee = run_backtest(df, signals, initial_cash=1000, commission=0, slippage=0)
    with_fee = run_backtest(df, signals, initial_cash=1000, commission=0.01, slippage=0)
    assert with_fee.equity.iloc[-1] < no_fee.equity.iloc[-1]


def test_buy_size_respects_fee_and_slippage_budget():
    """풀매수도 수수료·슬리피지까지 낼 수 있는 수량으로 제한해야 한다."""
    df = _make_df([100, 100, 100])
    signals = pd.Series([1, 1, 1], index=df.index, dtype=float)
    res = run_backtest(df, signals, initial_cash=1000, commission=0.10, slippage=0.10)

    buy = res.trades.iloc[0]
    gross_cost = buy["shares"] * buy["price"] * (1 + 0.10)
    assert gross_cost <= 1000 + 1e-9


def test_flat_position_keeps_cash():
    """신호가 계속 0이면 자산은 초기자본 그대로여야 한다."""
    df = _make_df([10, 12, 8, 15])
    signals = pd.Series([0, 0, 0, 0], index=df.index, dtype=float)
    res = run_backtest(df, signals, initial_cash=1000, commission=0.001, slippage=0.001)
    assert np.isclose(res.equity.iloc[-1], 1000)
    assert res.trades.empty


def test_buy_hold_tracks_price():
    """Buy&Hold 곡선은 가격 흐름을 따라가야 한다(2배 오르면 ~2배)."""
    df = _make_df([100, 150, 200])
    signals = pd.Series([0, 0, 0], index=df.index, dtype=float)
    res = run_backtest(df, signals, initial_cash=1000, commission=0, slippage=0)
    ratio = res.buy_hold_equity.iloc[-1] / res.buy_hold_equity.iloc[0]
    assert np.isclose(ratio, 2.0, atol=0.01)
