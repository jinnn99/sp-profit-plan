"""HTML 리포트 생성 — plotly 로 인터랙티브 차트를 단일 HTML 파일로 만든다.

구성:
1. 헤더 + 면책 문구
2. 핵심 지표 표 (전략 vs Buy&Hold)
3. 자산곡선 (전략 vs Buy&Hold)
4. 낙폭(drawdown) 곡선
5. 매매 시점이 표시된 가격 차트
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from stock_ai.config import settings
from stock_ai.report.metrics import compute_metrics

DISCLAIMER = (
    "⚠️ 본 리포트는 과거 데이터 기반 백테스트 결과이며 투자 자문이 아닙니다. "
    "과거 성과는 미래 수익을 보장하지 않습니다. 과최적화·생존편향·데이터 한계에 유의하세요."
)


def _fmt_pct(x) -> str:
    try:
        if pd.isna(x):
            return "—"
        return f"{x * 100:.2f}%"
    except (TypeError, ValueError):
        return str(x)


def _fmt_num(x) -> str:
    try:
        if pd.isna(x):
            return "—"
        return f"{x:,.2f}"
    except (TypeError, ValueError):
        return str(x)


def _metrics_table_html(m: dict) -> str:
    """지표 딕셔너리를 2단 비교 표 HTML 로 만든다."""
    rows = [
        ("기간", f"{m['시작일']} ~ {m['종료일']}", ""),
        ("초기자본", _fmt_num(m["초기자본"]), ""),
        ("최종자산", _fmt_num(m["최종자산"]), ""),
        ("총수익률", _fmt_pct(m["총수익률"]), _fmt_pct(m["BuyHold_총수익률"])),
        ("CAGR", _fmt_pct(m["CAGR"]), _fmt_pct(m["BuyHold_CAGR"])),
        ("최대낙폭(MDD)", _fmt_pct(m["최대낙폭(MDD)"]), _fmt_pct(m["BuyHold_MDD"])),
        ("연변동성", _fmt_pct(m["연변동성"]), ""),
        ("Sharpe", _fmt_num(m["Sharpe"]), ""),
        ("Sortino", _fmt_num(m["Sortino"]), ""),
        ("거래횟수", str(m["거래횟수"]), ""),
        ("승률", _fmt_pct(m["승률"]), ""),
        ("초과수익률(전략-BH)", _fmt_pct(m["초과수익률(전략-BH)"]), ""),
    ]
    body = "\n".join(
        f"<tr><th>{k}</th><td>{v1}</td><td>{v2}</td></tr>" for k, v1, v2 in rows
    )
    return (
        "<table class='metrics'>"
        "<thead><tr><th>지표</th><th>전략</th><th>Buy &amp; Hold</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _build_figure(df: pd.DataFrame, result) -> go.Figure:
    """자산곡선·낙폭·가격+매매 시점 3단 차트."""
    equity = result.equity
    bh = result.buy_hold_equity
    drawdown = equity / equity.cummax() - 1.0

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.45, 0.2, 0.35],
        vertical_spacing=0.05,
        subplot_titles=("자산곡선 (전략 vs Buy&Hold)", "전략 낙폭(Drawdown)", "가격 & 매매 시점"),
    )

    # 1단: 자산곡선
    fig.add_trace(go.Scatter(x=equity.index, y=equity.values, name="전략",
                             line=dict(color="#2563eb")), row=1, col=1)
    fig.add_trace(go.Scatter(x=bh.index, y=bh.values, name="Buy & Hold",
                             line=dict(color="#9ca3af", dash="dash")), row=1, col=1)

    # 2단: 낙폭
    fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown.values * 100, name="낙폭(%)",
                             fill="tozeroy", line=dict(color="#dc2626")), row=2, col=1)

    # 3단: 가격 + 매매 마커
    fig.add_trace(go.Scatter(x=df.index, y=df["close"], name="종가",
                             line=dict(color="#111827")), row=3, col=1)
    trades = result.trades
    if trades is not None and not trades.empty:
        buys = trades[trades["action"] == "BUY"]
        sells = trades[trades["action"] == "SELL"]
        if not buys.empty:
            fig.add_trace(go.Scatter(x=buys.index, y=buys["price"], mode="markers",
                                     name="매수", marker=dict(color="#16a34a", size=9,
                                     symbol="triangle-up")), row=3, col=1)
        if not sells.empty:
            fig.add_trace(go.Scatter(x=sells.index, y=sells["price"], mode="markers",
                                     name="매도", marker=dict(color="#dc2626", size=9,
                                     symbol="triangle-down")), row=3, col=1)

    fig.update_layout(
        height=900,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=30, t=60, b=40),
    )
    return fig


def build_html_report(df: pd.DataFrame, result, out_path: str | Path | None = None) -> Path:
    """백테스트 결과를 단일 HTML 리포트로 저장하고 경로를 반환한다.

    Args:
        df: 백테스트에 쓴 OHLCV 데이터프레임.
        result: BacktestResult.
        out_path: 저장 경로. None 이면 reports/{티커}_{전략}.html.
    """
    m = compute_metrics(result)

    if out_path is None:
        fname = f"{result.ticker or 'asset'}_{result.strategy_name or 'strategy'}.html"
        out_path = settings.reports_path / fname
    out_path = Path(out_path)

    fig = _build_figure(df, result)
    chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>백테스트 리포트 — {result.ticker} / {result.strategy_name}</title>
<style>
  body {{ font-family: -apple-system, "Malgun Gothic", sans-serif; margin: 0; background:#f8fafc; color:#111827; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 60px; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .sub {{ color:#6b7280; margin-bottom: 18px; }}
  .disclaimer {{ background:#fef3c7; border:1px solid #fde68a; color:#92400e;
                 padding:12px 16px; border-radius:8px; font-size:13px; margin-bottom:24px; }}
  table.metrics {{ border-collapse: collapse; width: 100%; background:#fff;
                   border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.08); margin-bottom:28px; }}
  table.metrics th, table.metrics td {{ padding:9px 14px; text-align:right; border-bottom:1px solid #f1f5f9; }}
  table.metrics thead th {{ background:#1e293b; color:#fff; text-align:right; }}
  table.metrics tbody th {{ text-align:left; color:#374151; font-weight:600; }}
  .chart {{ background:#fff; border-radius:8px; padding:8px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
</style>
</head>
<body>
<div class="wrap">
  <h1>백테스트 리포트</h1>
  <div class="sub">{result.ticker} &nbsp;·&nbsp; 전략: {result.strategy_name}
       &nbsp;·&nbsp; 수수료 {result.meta.get('commission', 0)*100:.2f}%
       / 슬리피지 {result.meta.get('slippage', 0)*100:.3f}%</div>
  <div class="disclaimer">{DISCLAIMER}</div>
  {_metrics_table_html(m)}
  <div class="chart">{chart_html}</div>
</div>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    return out_path
