"""백테스트 엔진 — 미래참조 편향 방지 + 거래비용 반영.

설계 원칙:
1. 신호는 t일 종가까지 정보로 계산된다(전략 책임).
2. 엔진은 신호를 'shift(1)' 하여 t+1일 '시가'에 체결한다.
   → t일에 본 정보로 t일에 체결하는 미래참조(look-ahead)를 원천 차단.
3. 매매가 일어난 날에만 수수료 + 슬리피지를 차감한다.
4. 포지션은 0.0(현금) 또는 1.0(풀매수)만 (Phase 1). 공매도·레버리지 없음.

자산곡선은 일별 수익률을 누적해 계산한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    """백테스트 결과 묶음."""

    equity: pd.Series           # 일별 포트폴리오 가치(초기자본 기준)
    returns: pd.Series          # 일별 전략 수익률
    positions: pd.Series        # 실제 체결된 포지션(shift 적용 후)
    trades: pd.DataFrame        # 매매 발생 시점 기록
    buy_hold_equity: pd.Series  # 비교용 단순 보유(Buy & Hold) 곡선
    initial_cash: float
    ticker: str = ""
    strategy_name: str = ""
    meta: dict = field(default_factory=dict)


def run_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    initial_cash: float = 10_000.0,
    commission: float = 0.001,   # 거래대금의 0.1%
    slippage: float = 0.0005,    # 체결가 0.05% 불리하게
    ticker: str = "",
    strategy_name: str = "",
) -> BacktestResult:
    """단일 종목 롱온리 백테스트를 실행한다.

    Args:
        df: open/high/low/close 인덱스=date 데이터프레임.
        signals: 전략의 목표 포지션(0.0~1.0), df 와 같은 인덱스.
        initial_cash: 초기 자본.
        commission: 매매 1회당 거래대금 대비 수수료율.
        slippage: 체결 시 가격 불리 비율(매수 시 +, 매도 시 -).
        ticker, strategy_name: 리포트 표기용.

    Returns:
        BacktestResult.
    """
    df = df.sort_index()
    signals = signals.reindex(df.index).fillna(0.0).clip(0.0, 1.0)

    # ── 핵심: 신호를 하루 미뤄 다음 봉에 반영 (미래참조 차단) ──
    target = signals.shift(1).fillna(0.0)

    open_px = df["open"].to_numpy(dtype=float)
    close_px = df["close"].to_numpy(dtype=float)
    tgt = target.to_numpy(dtype=float)
    n = len(df)

    cash = initial_cash
    shares = 0.0
    equity = np.zeros(n)
    pos_frac = np.zeros(n)     # 그날 장중 보유 비중(자산 대비)
    trade_records: list[dict] = []

    for i in range(n):
        o = open_px[i]
        c = close_px[i]

        # 1) 시가에 목표 포지션으로 리밸런싱 (target 이 바뀐 날만 거래)
        want = tgt[i]
        port_value_open = cash + shares * o
        desired_shares = (want * port_value_open) / o if o > 0 else 0.0

        if not np.isclose(desired_shares, shares):
            delta = desired_shares - shares       # +면 매수, -면 매도
            # 슬리피지: 매수는 비싸게, 매도는 싸게 체결
            fill_px = o * (1 + slippage) if delta > 0 else o * (1 - slippage)
            if delta > 0:
                # 수수료·슬리피지까지 내고도 살 수 있는 수량으로 제한한다.
                max_delta = cash / (fill_px * (1 + commission)) if fill_px > 0 else 0.0
                delta = min(delta, max_delta)
                if np.isclose(delta, 0.0):
                    equity[i] = cash + shares * c
                    port_now = equity[i]
                    pos_frac[i] = (shares * c / port_now) if port_now > 0 else 0.0
                    continue
            trade_value = abs(delta) * fill_px
            fee = trade_value * commission
            cash -= delta * fill_px      # 매수면 현금 감소, 매도면 증가
            cash -= fee
            shares += delta
            trade_records.append({
                "date": df.index[i],
                "action": "BUY" if delta > 0 else "SELL",
                "price": fill_px,
                "shares": abs(delta),
                "fee": fee,
                "target": want,
            })

        # 2) 종가 기준 평가
        equity[i] = cash + shares * c
        port_now = equity[i]
        pos_frac[i] = (shares * c / port_now) if port_now > 0 else 0.0

    equity_s = pd.Series(equity, index=df.index, name="equity")
    returns_s = equity_s.pct_change().fillna(0.0)
    returns_s.name = "returns"
    positions_s = pd.Series(pos_frac, index=df.index, name="position")

    # 비교용 Buy & Hold (첫날 시가 전량 매수, 수수료 1회)
    bh_fill_px = open_px[0] * (1 + slippage) if open_px[0] > 0 else 0.0
    bh_shares = initial_cash / (bh_fill_px * (1 + commission)) if bh_fill_px > 0 else 0.0
    buy_hold = pd.Series(bh_shares * close_px, index=df.index, name="buy_hold")

    trades_df = pd.DataFrame(trade_records)
    if not trades_df.empty:
        trades_df = trades_df.set_index("date")

    return BacktestResult(
        equity=equity_s,
        returns=returns_s,
        positions=positions_s,
        trades=trades_df,
        buy_hold_equity=buy_hold,
        initial_cash=initial_cash,
        ticker=ticker,
        strategy_name=strategy_name,
        meta={"commission": commission, "slippage": slippage},
    )
