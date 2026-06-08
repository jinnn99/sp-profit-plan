"""기본적 분석 데이터 — SEC EDGAR 공식 재무제표(XBRL).

SEC `companyfacts` API 는 상장사가 제출한 재무제표 원본을 제공한다.
(유료 데이터 서비스들이 결국 여기서 가져다 판다.)

추출 지표:
  - 매출(Revenues), 순이익(NetIncomeLoss), 자기자본(StockholdersEquity),
    총자산(Assets), 총부채(Liabilities), 희석EPS, 발행주식수
파생 지표:
  - ROE, 순이익률, 부채비율, 매출성장률(YoY), EPS성장률(YoY)

companyfacts JSON 은 종목당 한 번 받아 파일로 캐싱한다.
키 불필요(User-Agent 헤더만). 호출은 정중하게(분당 한도) 처리한다.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict

import requests

from stock_ai.config import settings
from stock_ai.data.universe import get_cik

_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# SEC 공정접근 권고(<=10 req/s) 준수: 실제 네트워크 호출 뒤에만 짧게 쉰다.
# (캐시 적중 시에는 지연이 없어 전체 분석 속도에 영향이 거의 없다.)
_POLITE_DELAY = 0.12

# 각 지표에 대응할 수 있는 XBRL 개념명 후보(회사마다 태그가 다르다)
_CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "net_income": ["NetIncomeLoss"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
}
_DURATION_METRICS = {"revenue", "net_income", "eps"}  # 기간(연간) 개념
_INSTANT_METRICS = {"equity", "assets", "liabilities"}  # 시점(잔액) 개념


@dataclass
class Fundamentals:
    """한 종목의 핵심 재무 지표 묶음 (없으면 None)."""

    ticker: str
    revenue: float | None = None
    revenue_growth: float | None = None      # 전년대비
    net_income: float | None = None
    net_margin: float | None = None          # 순이익/매출
    eps: float | None = None
    eps_growth: float | None = None
    equity: float | None = None
    assets: float | None = None
    liabilities: float | None = None
    roe: float | None = None                 # 순이익/자기자본
    debt_ratio: float | None = None          # 부채/자산
    shares: float | None = None              # 발행주식수(최근)
    as_of: str | None = None                 # 최신 회계연도 종료일

    def to_dict(self) -> dict:
        return asdict(self)


def _facts_cache_file(cik: str):
    d = settings.cache_path / "edgar"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"CIK{cik}.json"


def _cache_fresh(path, max_age_hours: float | None) -> bool:
    if max_age_hours is None:
        return True
    return (time.time() - path.stat().st_mtime) <= max_age_hours * 3600.0


def _fetch_company_facts(
    cik: str,
    refresh: bool = False,
    max_age_hours: float | None = 24 * 7,
) -> dict | None:
    """companyfacts JSON 을 받아온다(파일 캐싱)."""
    cache = _facts_cache_file(cik)
    cached = None
    if cache.exists() and not refresh:
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if _cache_fresh(cache, max_age_hours):
                return cached
        except json.JSONDecodeError:
            pass
    try:
        resp = requests.get(
            _FACTS_URL.format(cik=cik),
            headers={"User-Agent": settings.sec_user_agent},
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        cache.write_text(json.dumps(data), encoding="utf-8")
        # 캐시 미스로 실제 호출이 일어난 경우에만 정중하게 지연(전체 503종목 콜드런 보호).
        time.sleep(_POLITE_DELAY)
        return data
    except requests.RequestException as e:
        print(f"[fundamentals] CIK{cik} 수집 실패: {e}")
        return cached


def _annual_points(facts: dict, concept_names: list[str], duration: bool) -> list[tuple[str, float]]:
    """주어진 개념(들)의 '연간' 데이터 포인트 [(종료일, 값)] 를 최신순으로 반환.

    duration=True 면 기간(약 1년)짜리 항목만, False 면 시점(잔액) 항목.
    USD(또는 EPS 의 USD/shares) 단위, 10-K(연간보고서) 우선.
    """
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for name in concept_names:
        if name not in gaap:
            continue
        units = gaap[name].get("units", {})
        # 단위 키 선택: 금액은 USD, EPS 는 USD/shares
        unit_key = next((k for k in units if k.upper().startswith("USD")), None)
        if unit_key is None:
            continue
        points: dict[str, float] = {}  # 종료일 → 값 (중복은 최신 제출이 덮어씀)
        for item in units[unit_key]:
            if item.get("form") not in ("10-K", "10-K/A"):
                continue
            end = item.get("end")
            val = item.get("val")
            if end is None or val is None:
                continue
            if duration:
                start = item.get("start")
                if not start:
                    continue
                # 연간(약 350~380일)만
                days = (_to_date(end) - _to_date(start)).days
                if not (350 <= days <= 380):
                    continue
            points[end] = float(val)
        if points:
            return sorted(points.items(), key=lambda kv: kv[0], reverse=True)
    return []


def _to_date(s: str):
    from datetime import date
    y, m, d = map(int, s.split("-"))
    return date(y, m, d)


def _latest_shares(facts: dict) -> float | None:
    """발행주식수(최근). dei 네임스페이스 우선, 없으면 us-gaap."""
    for ns in ("dei", "us-gaap"):
        block = facts.get("facts", {}).get(ns, {})
        for name in ("EntityCommonStockSharesOutstanding",
                     "CommonStockSharesOutstanding",
                     "WeightedAverageNumberOfDilutedSharesOutstanding"):
            if name not in block:
                continue
            units = block[name].get("units", {})
            unit_key = next((k for k in units if k.lower() == "shares"), None)
            if not unit_key:
                continue
            items = [it for it in units[unit_key] if it.get("val")]
            if items:
                items.sort(key=lambda it: it.get("end", ""), reverse=True)
                return float(items[0]["val"])
    return None


def _safe_div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def get_fundamentals(
    ticker: str,
    refresh: bool = False,
    max_age_hours: float | None = 24 * 7,
) -> Fundamentals:
    """티커의 SEC 재무 지표를 계산해 반환한다(데이터 없으면 필드 None)."""
    ticker = ticker.upper()
    cik = get_cik(ticker)
    if cik is None:
        return Fundamentals(ticker=ticker)
    facts = _fetch_company_facts(cik, refresh=refresh, max_age_hours=max_age_hours)
    if not facts:
        return Fundamentals(ticker=ticker)

    f = Fundamentals(ticker=ticker)

    # 기간 지표(연간) — 최신 + 직전으로 성장률 계산
    rev = _annual_points(facts, _CONCEPTS["revenue"], duration=True)
    ni = _annual_points(facts, _CONCEPTS["net_income"], duration=True)
    eps = _annual_points(facts, _CONCEPTS["eps"], duration=True)
    # 시점 지표 — 최신값
    eq = _annual_points(facts, _CONCEPTS["equity"], duration=False)
    assets = _annual_points(facts, _CONCEPTS["assets"], duration=False)
    liab = _annual_points(facts, _CONCEPTS["liabilities"], duration=False)

    if rev:
        f.revenue = rev[0][1]
        f.as_of = rev[0][0]
        if len(rev) > 1 and rev[1][1]:
            f.revenue_growth = _safe_div(rev[0][1] - rev[1][1], abs(rev[1][1]))
    if ni:
        f.net_income = ni[0][1]
    if eps:
        f.eps = eps[0][1]
        if len(eps) > 1 and eps[1][1]:
            f.eps_growth = _safe_div(eps[0][1] - eps[1][1], abs(eps[1][1]))
    if eq:
        f.equity = eq[0][1]
    if assets:
        f.assets = assets[0][1]
    if liab:
        f.liabilities = liab[0][1]

    # 파생 지표
    f.net_margin = _safe_div(f.net_income, f.revenue)
    f.roe = _safe_div(f.net_income, f.equity)
    f.debt_ratio = _safe_div(f.liabilities, f.assets)
    f.shares = _latest_shares(facts)
    return f


def get_many_fundamentals(tickers: list[str], polite_delay: float = 0.15) -> dict[str, Fundamentals]:
    """여러 종목의 재무 지표를 모은다(캐시 우선, 신규 호출만 지연).

    SEC 권고 속도(<=10 req/s)를 지키려 캐시 미스 시에만 짧게 쉰다.
    """
    out: dict[str, Fundamentals] = {}
    for t in tickers:
        cik = get_cik(t)
        cache_file = _facts_cache_file(cik) if cik is not None else None
        will_fetch = (
            cache_file is not None
            and (not cache_file.exists() or not _cache_fresh(cache_file, 24 * 7))
        )
        out[t] = get_fundamentals(t)
        if will_fetch:
            time.sleep(polite_delay)
    return out
