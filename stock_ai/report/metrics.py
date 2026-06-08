"""성과·리스크 지표 계산.

일별 수익률·자산곡선으로부터 CAGR, 변동성, Sharpe, MDD, 승률 등을 구한다.
연율화는 미국 주식 거래일 기준 252일을 쓴다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _cagr(equity: pd.Series) -> float:
    """연복리 성장률(CAGR)."""
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    total_return = equity.iloc[-1] / equity.iloc[0]
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return float(total_return ** (1 / years) - 1)


def _max_drawdown(equity: pd.Series) -> float:
    """최대낙폭(MDD). 음수로 반환(예: -0.35)."""
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def _sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    """연율화 Sharpe 비율 (무위험수익률 rf=0 가정)."""
    excess = returns - rf / TRADING_DAYS
    std = excess.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float(excess.mean() / std * np.sqrt(TRADING_DAYS))


def _sortino(returns: pd.Series, rf: float = 0.0) -> float:
    """연율화 Sortino 비율 (하방 변동성만 사용)."""
    excess = returns - rf / TRADING_DAYS
    downside = excess[excess < 0]
    dd_std = downside.std()
    if dd_std == 0 or np.isnan(dd_std):
        return 0.0
    return float(excess.mean() / dd_std * np.sqrt(TRADING_DAYS))


def compute_metrics(result) -> dict:
    """BacktestResult 로부터 핵심 지표 딕셔너리를 만든다.

    Returns:
        한글 표기용 지표 딕셔너리 (전략 + Buy&Hold 비교 포함).
    """
    equity = result.equity
    returns = result.returns

    # 거래 통계
    trades = result.trades
    n_trades = 0
    win_rate = float("nan")
    if trades is not None and not trades.empty:
        # 매수→매도 한 쌍을 1회 왕복거래로 보고 승률 계산
        sells = trades[trades["action"] == "SELL"]
        buys = trades[trades["action"] == "BUY"]
        n_trades = int(len(buys))
        wins = 0
        round_trips = 0
        buy_iter = iter(buys.itertuples())
        for sell in sells.itertuples():
            try:
                b = next(buy_iter)
            except StopIteration:
                break
            round_trips += 1
            if sell.price > b.price:
                wins += 1
        if round_trips > 0:
            win_rate = wins / round_trips

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0
    bh = result.buy_hold_equity
    bh_total = float(bh.iloc[-1] / bh.iloc[0] - 1) if len(bh) > 1 else 0.0

    return {
        "티커": result.ticker,
        "전략": result.strategy_name,
        "시작일": str(equity.index[0].date()),
        "종료일": str(equity.index[-1].date()),
        "초기자본": result.initial_cash,
        "최종자산": float(equity.iloc[-1]),
        "총수익률": total_return,
        "CAGR": _cagr(equity),
        "연변동성": float(returns.std() * np.sqrt(TRADING_DAYS)),
        "Sharpe": _sharpe(returns),
        "Sortino": _sortino(returns),
        "최대낙폭(MDD)": _max_drawdown(equity),
        "거래횟수": n_trades,
        "승률": win_rate,
        "BuyHold_총수익률": bh_total,
        "BuyHold_CAGR": _cagr(bh),
        "BuyHold_MDD": _max_drawdown(bh),
        "초과수익률(전략-BH)": total_return - bh_total,
    }
