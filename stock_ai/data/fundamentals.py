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
    # --- 확장(같은 캐시 JSON에서 추가 파싱, 네트워크 호출 0) ---
    "gross_profit": ["GrossProfit"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "operating_income": ["OperatingIncomeLoss"],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "dna": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt"],
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "debt_current": ["LongTermDebtCurrent", "DebtCurrent"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
}
# 기간(연간) 개념 — 손익·현금흐름
_DURATION_METRICS = {
    "revenue", "net_income", "eps", "gross_profit", "cogs", "operating_income",
    "operating_cash_flow", "capex", "dna", "interest_expense", "dividends_paid",
    "shares_diluted",
}
# 시점(잔액) 개념 — 재무상태표
_INSTANT_METRICS = {
    "equity", "assets", "liabilities", "cash", "long_term_debt", "debt_current",
    "current_assets", "current_liabilities",
}


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
    # --- 확장 파생 지표(같은 SEC 캐시에서 계산, 네트워크 0) ---
    roa: float | None = None                 # 순이익/총자산
    gross_margin: float | None = None        # 매출총이익/매출
    op_margin: float | None = None           # 영업이익/매출
    current_ratio: float | None = None       # 유동자산/유동부채
    interest_coverage: float | None = None   # 영업이익/이자비용
    fcf: float | None = None                 # 영업현금흐름 − CapEx
    ebitda: float | None = None              # 영업이익 + D&A
    total_debt: float | None = None          # 장기+단기 차입금
    cash: float | None = None                # 현금성자산
    dividends_paid: float | None = None      # 배당 지급액(절대값)
    revenue_cagr: float | None = None        # 매출 다년 CAGR
    eps_cagr: float | None = None            # EPS 다년 CAGR
    piotroski: float | None = None           # 0~9 (재무 건전성)

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
    best: list[tuple[str, float]] = []
    best_end = ""
    # 후보 태그 중 '가장 최신 데이터를 가진' 개념을 고른다(회사가 태그를 바꾸면
    # 먼저 나열된 태그가 옛 값만 가질 수 있어, 첫 매칭이 아닌 최신 종료일 기준으로 선택).
    for name in concept_names:
        if name not in gaap:
            continue
        units = gaap[name].get("units", {})
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
        if not points:
            continue
        cur_end = max(points)
        if cur_end > best_end:
            best_end = cur_end
            best = sorted(points.items(), key=lambda kv: kv[0], reverse=True)
    return best


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


def _first(points):
    """[(end,val)] 최신값(없으면 None)."""
    return points[0][1] if points else None


def _at(points, i):
    return points[i][1] if points and len(points) > i else None


def _cagr(points, max_years: int = 4):
    """[(end,val)] 최신순에서 다년 CAGR. 양수 값에서만 의미가 있어 음수면 None."""
    if not points or len(points) < 2:
        return None
    n = min(max_years, len(points) - 1)
    newest = points[0][1]
    oldest = points[n][1]
    if newest is None or oldest is None or newest <= 0 or oldest <= 0 or n <= 0:
        return None
    try:
        return (newest / oldest) ** (1.0 / n) - 1.0
    except (ValueError, ZeroDivisionError):
        return None


def _piotroski(rev, ni, assets, ocf, gp, ca, cl, ltd, shares):
    """Piotroski F-Score(0~9). 산출 가능한 신호가 5개 미만이면 None.

    인자는 모두 _annual_points 결과(최신순 [(end,val)]). 결측 신호는 제외하고
    9점 만점으로 환산한다(데이터 결손 종목을 과도하게 깎지 않기 위함).
    """
    def r(a, b):
        return _safe_div(a, b)

    a0, a1 = _at(assets, 0), _at(assets, 1)
    ni0, ni1 = _at(ni, 0), _at(ni, 1)
    ocf0 = _at(ocf, 0)
    roa0, roa1 = r(ni0, a0), r(ni1, a1)

    signals = []  # 각 (조건충족 bool) — 계산 가능할 때만 추가
    if roa0 is not None:
        signals.append(roa0 > 0)                       # 1 수익성
    if ocf0 is not None:
        signals.append(ocf0 > 0)                       # 2 영업현금흐름
    if roa0 is not None and roa1 is not None:
        signals.append(roa0 > roa1)                    # 3 ROA 개선
    if ocf0 is not None and ni0 is not None:
        signals.append(ocf0 > ni0)                     # 4 발생액(현금이익 질)
    l0, l1 = r(_at(ltd, 0), a0), r(_at(ltd, 1), a1)
    if l0 is not None and l1 is not None:
        signals.append(l0 < l1)                        # 5 레버리지 감소
    cr0, cr1 = r(_at(ca, 0), _at(cl, 0)), r(_at(ca, 1), _at(cl, 1))
    if cr0 is not None and cr1 is not None:
        signals.append(cr0 > cr1)                      # 6 유동성 개선
    s0, s1 = _at(shares, 0), _at(shares, 1)
    if s0 is not None and s1 is not None:
        signals.append(s0 <= s1 * 1.02)                # 7 무증자(희석 없음)
    gm0, gm1 = r(_at(gp, 0), _at(rev, 0)), r(_at(gp, 1), _at(rev, 1))
    if gm0 is not None and gm1 is not None:
        signals.append(gm0 > gm1)                      # 8 매출총이익률 개선
    at0, at1 = r(_at(rev, 0), a0), r(_at(rev, 1), a1)
    if at0 is not None and at1 is not None:
        signals.append(at0 > at1)                      # 9 자산회전율 개선

    if len(signals) < 5:
        return None
    score = sum(1 for s in signals if s)
    return round(score * 9.0 / len(signals), 2)


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

    # --- 확장 개념 추출(같은 캐시 JSON, 네트워크 0) ---
    gp = _annual_points(facts, _CONCEPTS["gross_profit"], duration=True)
    cogs = _annual_points(facts, _CONCEPTS["cogs"], duration=True)
    opinc = _annual_points(facts, _CONCEPTS["operating_income"], duration=True)
    ocf = _annual_points(facts, _CONCEPTS["operating_cash_flow"], duration=True)
    capex = _annual_points(facts, _CONCEPTS["capex"], duration=True)
    dna = _annual_points(facts, _CONCEPTS["dna"], duration=True)
    intexp = _annual_points(facts, _CONCEPTS["interest_expense"], duration=True)
    divs = _annual_points(facts, _CONCEPTS["dividends_paid"], duration=True)
    sh = _annual_points(facts, _CONCEPTS["shares_diluted"], duration=True)
    cash = _annual_points(facts, _CONCEPTS["cash"], duration=False)
    ltd = _annual_points(facts, _CONCEPTS["long_term_debt"], duration=False)
    dcur = _annual_points(facts, _CONCEPTS["debt_current"], duration=False)
    ca = _annual_points(facts, _CONCEPTS["current_assets"], duration=False)
    cl = _annual_points(facts, _CONCEPTS["current_liabilities"], duration=False)

    # 레벨 지표는 최신 연간(10-K)을 쓴다. SEC XBRL 의 분기/YTD는 회사별 회계연도·
    # Q4 미분리·정정 등으로 TTM 합산이 일부 종목에서 값을 오염시켜(예: 회계연도 경계
    # 종목의 매출 왜곡) 정확성을 위해 연간값을 사용한다. (재무는 천천히 변한다.)
    gross_profit = _first(gp)
    if gross_profit is None and _first(cogs) is not None and f.revenue is not None:
        gross_profit = f.revenue - _first(cogs)
    op_income = _first(opinc)
    ocf_level = _first(ocf)
    capex_level = _first(capex)

    # 파생 지표(레벨)
    f.net_margin = _safe_div(f.net_income, f.revenue)
    f.roe = _safe_div(f.net_income, f.equity)
    f.roa = _safe_div(f.net_income, f.assets)
    f.debt_ratio = _safe_div(f.liabilities, f.assets)
    f.gross_margin = _safe_div(gross_profit, f.revenue)
    f.op_margin = _safe_div(op_income, f.revenue)
    f.current_ratio = _safe_div(_first(ca), _first(cl))
    f.interest_coverage = _safe_div(op_income, _first(intexp))
    if ocf_level is not None:
        f.fcf = ocf_level - (capex_level or 0.0)
    if op_income is not None:
        f.ebitda = op_income + (_first(dna) or 0.0)
    if _first(ltd) is not None or _first(dcur) is not None:
        f.total_debt = (_first(ltd) or 0.0) + (_first(dcur) or 0.0)
    f.cash = _first(cash)
    f.dividends_paid = abs(_first(divs)) if _first(divs) is not None else None
    f.revenue_cagr = _cagr(rev)
    f.eps_cagr = _cagr(eps)
    f.piotroski = _piotroski(rev, ni, assets, ocf, gp, ca, cl, ltd, sh)
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
