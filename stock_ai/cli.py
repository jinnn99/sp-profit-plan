"""명령줄 인터페이스 (typer).

예시:
    python -m stock_ai fetch --ticker AAPL
    python -m stock_ai backtest --ticker AAPL --strategy sma_cross --start 2015-01-01
    python -m stock_ai strategies
"""
from __future__ import annotations

import sys

import typer

# Windows 콘솔(cp949)에서 한글이 깨지지 않도록 UTF-8 출력으로 강제
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (ValueError, OSError):
        pass

from stock_ai.data.prices import get_prices
from stock_ai.report.metrics import compute_metrics  # noqa: F401 (가독성용)
from stock_ai.runner import backtest_ticker, recommend_universe
from stock_ai.strategy.samples import REGISTRY

app = typer.Typer(add_completion=False, help="미국 주식 백테스트·전략검증 AI")


def _print_metrics(m: dict) -> None:
    """지표 딕셔너리를 콘솔에 보기 좋게 출력한다."""
    def pct(x):
        try:
            return f"{x*100:.2f}%"
        except (TypeError, ValueError):
            return str(x)

    typer.echo("─" * 48)
    typer.echo(f" {m['티커']} / 전략: {m['전략']}")
    typer.echo(f" 기간      : {m['시작일']} ~ {m['종료일']}")
    typer.echo(f" 총수익률  : {pct(m['총수익률'])}   (B&H {pct(m['BuyHold_총수익률'])})")
    typer.echo(f" CAGR      : {pct(m['CAGR'])}   (B&H {pct(m['BuyHold_CAGR'])})")
    typer.echo(f" 최대낙폭  : {pct(m['최대낙폭(MDD)'])}   (B&H {pct(m['BuyHold_MDD'])})")
    typer.echo(f" Sharpe    : {m['Sharpe']:.2f}    Sortino: {m['Sortino']:.2f}")
    typer.echo(f" 거래횟수  : {m['거래횟수']}    승률: {pct(m['승률'])}")
    typer.echo(f" 초과수익  : {pct(m['초과수익률(전략-BH)'])}  (전략 - Buy&Hold)")
    typer.echo("─" * 48)


@app.command()
def fetch(
    ticker: str = typer.Option(..., "--ticker", "-t", help="티커 (예: AAPL)"),
    start: str = typer.Option("2015-01-01", "--start", help="시작일 YYYY-MM-DD"),
    end: str = typer.Option(None, "--end", help="종료일 YYYY-MM-DD (기본: 오늘)"),
):
    """가격 데이터를 받아 SQLite 캐시에 저장한다."""
    df = get_prices(ticker, start=start, end=end)
    typer.echo(f"{ticker.upper()}: {len(df)}개 일봉 캐싱 완료 "
               f"({df.index.min().date()} ~ {df.index.max().date()})")


@app.command()
def backtest(
    ticker: str = typer.Option(..., "--ticker", "-t", help="티커 (예: AAPL)"),
    strategy: str = typer.Option("sma_cross", "--strategy", "-s", help="전략 이름"),
    start: str = typer.Option("2015-01-01", "--start", help="시작일 YYYY-MM-DD"),
    end: str = typer.Option(None, "--end", help="종료일 YYYY-MM-DD"),
    cash: float = typer.Option(10_000.0, "--cash", help="초기 자본"),
    commission: float = typer.Option(0.001, "--commission", help="수수료율 (0.001=0.1%)"),
    slippage: float = typer.Option(0.0005, "--slippage", help="슬리피지율"),
    fast: int = typer.Option(None, "--fast", help="(sma_cross) 단기 이동평균"),
    slow: int = typer.Option(None, "--slow", help="(sma_cross) 장기 이동평균"),
):
    """백테스트를 실행하고 HTML 리포트를 생성한다."""
    if strategy not in REGISTRY:
        typer.echo(f"알 수 없는 전략 '{strategy}'. 사용 가능: {', '.join(REGISTRY)}")
        raise typer.Exit(code=1)

    kwargs = {}
    if strategy == "sma_cross":
        if fast is not None:
            kwargs["fast"] = fast
        if slow is not None:
            kwargs["slow"] = slow

    _, metrics, report = backtest_ticker(
        ticker, strategy=strategy, start=start, end=end,
        initial_cash=cash, commission=commission, slippage=slippage,
        strategy_kwargs=kwargs,
    )
    _print_metrics(metrics)
    if report:
        typer.echo(f"리포트: {report}")


@app.command()
def strategies():
    """사용 가능한 전략 목록을 보여준다."""
    typer.echo("사용 가능한 전략:")
    for name, cls in REGISTRY.items():
        doc = (cls.__doc__ or "").strip().splitlines()[0]
        typer.echo(f"  - {name}: {doc}")


@app.command()
def fundamentals(
    ticker: str = typer.Option(..., "--ticker", "-t", help="티커 (예: AAPL)"),
    refresh: bool = typer.Option(False, "--refresh", help="SEC 재무 캐시를 무시하고 새로 받기"),
):
    """SEC EDGAR 공식 재무 지표를 조회한다(무료·캐싱)."""
    from stock_ai.data.fundamentals import get_fundamentals

    f = get_fundamentals(ticker, refresh=refresh)
    d = f.to_dict()
    if d.get("as_of") is None:
        typer.echo(f"{ticker.upper()}: SEC 재무 데이터를 찾지 못했습니다.")
        raise typer.Exit(code=1)

    def pct(x):
        return f"{x*100:.1f}%" if isinstance(x, (int, float)) else "—"

    typer.echo("─" * 48)
    typer.echo(f" {ticker.upper()}  (기준 회계연도 종료: {d['as_of']})")
    typer.echo(f" 매출      : {d['revenue']:,.0f}  (성장 {pct(d['revenue_growth'])})")
    typer.echo(f" 순이익    : {d['net_income']:,.0f}  (순이익률 {pct(d['net_margin'])})")
    typer.echo(f" EPS       : {d['eps']}  (성장 {pct(d['eps_growth'])})")
    typer.echo(f" ROE       : {pct(d['roe'])}    부채비율: {pct(d['debt_ratio'])}")
    typer.echo("─" * 48)


@app.command()
def recommend(
    top: int = typer.Option(10, "--top", help="추천 종목 수"),
    limit: int = typer.Option(60, "--limit", help="분석 종목 수 상한 (0=S&P500 전체)"),
    start: str = typer.Option("2015-01-01", "--start", help="과거 검증 시작일"),
    style: str = typer.Option("balanced", "--style",
                              help="투자 성향: balanced/value/growth/dividend/momentum"),
    no_sentiment: bool = typer.Option(False, "--no-sentiment", help="감성분석(심리 축) 끄기"),
    finbert: bool = typer.Option(False, "--finbert",
                                 help="⚠️고메모리(RAM 8GB+). 저사양 PC에서는 쓰지 마세요"),
    refresh: bool = typer.Option(False, "--refresh", help="S&P500/SEC 재무 캐시를 무시하고 새로 받기"),
):
    """S&P500을 종합분석해 추천 종목·공통 매매 규칙 리포트를 만든다.

    --style 로 투자 성향(가치/성장/배당안정/모멘텀/균형)을 골라 추천 성격을 바꿉니다.
    감성분석 기본은 가벼운 키워드 방식(메모리 안전). --finbert 는 고메모리라
    RAM 이 작은 PC에서는 시스템이 다운될 수 있으니 쓰지 마세요.
    """
    from stock_ai.config import FACTOR_WEIGHT_PRESETS, STYLE_LABELS_KO

    if style not in FACTOR_WEIGHT_PRESETS:
        typer.echo(f"알 수 없는 성향 '{style}'. 사용 가능: {', '.join(FACTOR_WEIGHT_PRESETS)}")
        raise typer.Exit(code=1)
    weights = FACTOR_WEIGHT_PRESETS[style]

    method = "none" if no_sentiment else ("finbert" if finbert else "lexicon")
    if method == "finbert":
        typer.echo("⚠️ FinBERT(고메모리) 모드입니다. RAM 부족 시 시스템이 다운될 수 있습니다.")
    typer.echo(f"종합분석을 시작합니다… (성향={STYLE_LABELS_KO[style]}, 감성={method})")
    recs, score_df, portfolio, report = recommend_universe(
        top_n=top, limit=(limit or None), start=start, sentiment_method=method,
        weights=weights, style=style, refresh_data=refresh,
    )
    if not recs:
        typer.echo("추천 종목을 만들지 못했습니다(데이터 부족).")
        raise typer.Exit(code=1)

    typer.echo("─" * 56)
    typer.echo(f" 추천 상위 {len(recs)}종목 (종합점수 / 신뢰도)")
    for i, r in enumerate(recs, 1):
        typer.echo(f" {i:2d}. {r.ticker:6s} {r.composite:5.0f}점  {r.confidence}  | {r.name}")
    typer.echo("─" * 56)
    typer.echo(" 상세 리포트에는 각 종목의 강점·리스크, 핵심 근거, 공통 매매 규칙이 정리됩니다.")
    if report:
        typer.echo(f"리포트: {report}")


if __name__ == "__main__":
    app()
