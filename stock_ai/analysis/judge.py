"""종목 '지금' 판단 — 단일 종목을 그 순간 데이터로 종합 판단.

대시보드의 '종목 즉시 판단기'가 쓴다. 전체 S&P500 횡단면 점수와 달리,
한 종목만 빠르게(1~2초) 라이브로 보고 **매수/보유·관망/청산** 신호와 근거를 준다.

★예측이 아니라 '규칙 기반 신호'다. 타이밍은 추세(200일선·RSI)가 주도하고,
재무(품질)·뉴스 감성은 보조 근거로 함께 보여 준다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from stock_ai.analysis.sentiment import get_sentiment
from stock_ai.data.fundamentals import get_fundamentals
from stock_ai.data.prices import get_prices
from stock_ai.features.indicators import rsi


@dataclass
class Judgment:
    ticker: str
    verdict: str          # 진입 검토 / 보유·관망 / 청산·관망 / 데이터부족
    color: str            # green / amber / red / gray
    headline: str         # 한 줄 요약
    price: float = float("nan")
    sma200: float = float("nan")
    rsi: float = float("nan")
    pe: float = float("nan")
    roe: float = float("nan")
    sentiment: float = float("nan")
    reasons: list[str] = field(default_factory=list)   # 종합 근거
    entry_rules: list[str] = field(default_factory=list)
    exit_rules: list[str] = field(default_factory=list)
    as_of: str = ""


def _fmt_pct(x):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:.1f}%"


def judge_ticker(ticker: str, live: bool = True) -> Judgment:
    """단일 종목을 지금 데이터로 판단한다.

    Args:
        live: True 면 가격을 캐시 무시하고 새로 받아 최신가로 판단.
    """
    ticker = ticker.upper().strip()
    start = (date.today() - timedelta(days=420)).isoformat()  # 200일선·RSI 충분히
    try:
        prices = get_prices(ticker, start=start, use_cache=not live)
    except Exception as e:
        return Judgment(ticker, "데이터부족", "gray",
                        f"가격 데이터를 가져오지 못했습니다({str(e)[:60]}).")

    close = prices["close"].dropna()
    if len(close) < 30:
        return Judgment(ticker, "데이터부족", "gray", "가격 이력이 부족합니다.")

    last = float(close.iloc[-1])
    sma200 = float(close.tail(200).mean())
    rsi_val = float(rsi(close, 14).iloc[-1])
    as_of = str(close.index[-1].date())

    fund = get_fundamentals(ticker)
    try:
        sent = get_sentiment(ticker, method="lexicon")
    except Exception:
        sent = None

    pe = last / fund.eps if (fund.eps and fund.eps > 0) else float("nan")

    j = Judgment(ticker=ticker, verdict="", color="", headline="",
                 price=last, sma200=sma200, rsi=rsi_val,
                 pe=pe,
                 roe=fund.roe if fund.roe is not None else float("nan"),
                 sentiment=sent if sent is not None else float("nan"),
                 as_of=as_of)

    above = last >= sma200
    gap = (last / sma200 - 1) if sma200 > 0 else 0.0

    # ── 종합 근거 모으기 ──
    j.reasons.append(
        f"추세: 현재가 ${last:,.2f} 가 200일선(${sma200:,.2f}) "
        + (f"위 (+{gap*100:.1f}%) → 장기 상승 추세" if above
           else f"아래 ({gap*100:.1f}%) → 추세 약화/하락")
    )
    j.reasons.append(
        f"단기 과열도(RSI 14일): {rsi_val:.0f} "
        + ("→ 과매수(과열)" if rsi_val >= 70 else ("→ 과매도(눌림)" if rsi_val <= 30 else "→ 중립권"))
    )
    if fund.roe is not None:
        q = "양호" if fund.roe >= 0.12 else ("보통" if fund.roe >= 0.05 else "약함")
        j.reasons.append(f"수익성(ROE {_fmt_pct(fund.roe)}) {q}"
                         + (f", 순이익률 {_fmt_pct(fund.net_margin)}" if fund.net_margin is not None else ""))
    else:
        j.reasons.append("재무: SEC 데이터 결손(품질 확인 불가)")
    if fund.debt_ratio is not None and fund.debt_ratio > 0.7:
        j.reasons.append(f"⚠️ 부채비율 높음({_fmt_pct(fund.debt_ratio)})")
    if sent is not None:
        tone = "긍정" if sent > 0.1 else ("부정" if sent < -0.1 else "중립")
        j.reasons.append(f"최근 뉴스 심리: {tone}({sent:+.2f})")

    # ── 판단 규칙 (타이밍은 추세가 주도) ──
    weak_fund = (fund.roe is not None and fund.roe < 0.0)  # 적자
    if not above:
        j.verdict, j.color = "청산·관망", "red"
        j.headline = "200일선 아래 — 신규 매수 부적합. 보유 중이면 비중 축소 검토."
    elif rsi_val >= 70:
        j.verdict, j.color = "보유·관망", "amber"
        j.headline = "추세는 양호하나 단기 과열 — 눌림목까지 분할매수 대기."
    elif weak_fund:
        j.verdict, j.color = "보유·관망", "amber"
        j.headline = "추세는 양호하나 적자 등 펀더멘털 부담 — 신중히 소액만."
    else:
        j.verdict, j.color = "진입 검토", "green"
        j.headline = "장기 추세 양호 + 과열 아님 — 분할매수 검토 구간."

    j.entry_rules = [
        "한 번에 사지 말고 3회 이상 나눠 분할매수(평균단가 분산)",
        "200일선 위·과열(RSI≥70) 아님을 확인하고 진입",
        "종목당 비중은 한도(예: 10%) 이내, 현금 버퍼 유지",
    ]
    j.exit_rules = [
        "트레일링 손절: 매수 후 고점 대비 −20%면 기계적으로 매도",
        "추세 이탈: 종가가 200일선을 의미 있게 하향 이탈하면 비중 축소",
        "※ '고점 예측'이 아니라 손실을 제한하는 사전 약속",
    ]
    return j
