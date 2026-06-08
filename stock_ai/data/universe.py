"""투자 유니버스 — S&P 500 구성종목 + 티커→CIK(SEC 식별번호) 매핑.

- S&P 500 목록: Wikipedia 표에서 가져온다(무료). 실패 시 소형 폴백 목록 사용.
- 티커→CIK: SEC 공식 `company_tickers.json` (EDGAR 재무 조회에 필요).
모두 캐싱해 반복 네트워크 호출을 피한다.
"""
from __future__ import annotations

import json
import time
from io import StringIO

import pandas as pd
import requests

from stock_ai.config import settings

_SP500_WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"

# Wikipedia 가 막혔을 때를 대비한 최소 폴백(대형 우량주)
_FALLBACK = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "JNJ",
    "WMT", "PG", "MA", "HD", "KO", "PEP", "COST", "MRK", "ABBV", "AVGO",
]


def _sp500_cache_file():
    return settings.cache_path / "sp500.csv"


def _cik_cache_file():
    return settings.cache_path / "ticker_cik.json"


def _cache_fresh(path, max_age_hours: float | None) -> bool:
    if max_age_hours is None:
        return True
    return (time.time() - path.stat().st_mtime) <= max_age_hours * 3600.0


def get_sp500(refresh: bool = False, max_age_hours: float | None = 24 * 7) -> pd.DataFrame:
    """S&P 500 구성종목 데이터프레임을 반환한다.

    Returns:
        컬럼: ticker, name, sector (가능한 경우).
    """
    cache = _sp500_cache_file()
    cached_df = None
    if cache.exists() and not refresh:
        cached_df = pd.read_csv(cache)
        if _cache_fresh(cache, max_age_hours):
            return cached_df

    try:
        # Wikipedia 는 봇 차단이 있어 User-Agent 를 넣어 직접 받아 파싱한다.
        resp = requests.get(_SP500_WIKI, headers={"User-Agent": settings.sec_user_agent}, timeout=30)
        resp.raise_for_status()
        # pandas 2.2+ 는 원시 HTML 문자열을 직접 받지 않으므로 StringIO 로 감싼다.
        tables = pd.read_html(StringIO(resp.text))

        # 'Symbol'/'Ticker' 컬럼을 가진 표를 찾는다(표 순서가 바뀌어도 안전).
        df = None
        for t in tables:
            cols = {str(c) for c in t.columns}
            if "Symbol" in cols or "Ticker" in cols:
                df = t
                break
        if df is None:
            raise ValueError("S&P500 구성종목 표를 찾지 못함")

        df = df.rename(columns={
            "Symbol": "ticker", "Ticker": "ticker",
            "Security": "name", "Company": "name",
            "GICS Sector": "sector", "Sector": "sector",
        })
        df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False)  # BRK.B → BRK-B
        keep = [c for c in ["ticker", "name", "sector"] if c in df.columns]
        df = df[keep].dropna(subset=["ticker"])
        if "name" not in df.columns:
            df["name"] = df["ticker"]
        if "sector" not in df.columns:
            df["sector"] = "Unknown"
        df.to_csv(cache, index=False)
        return df
    except Exception as e:  # 네트워크/파싱 실패 시 폴백 (에러 메시지는 짧게)
        if cached_df is not None:
            print(f"[universe] S&P500 갱신 실패({str(e)[:120]}). 기존 캐시 사용.")
            return cached_df
        print(f"[universe] S&P500 목록 수집 실패({str(e)[:120]}). 폴백 {len(_FALLBACK)}종목 사용.")
        return pd.DataFrame({"ticker": _FALLBACK, "name": _FALLBACK, "sector": "Unknown"})


def get_ticker_cik_map(refresh: bool = False, max_age_hours: float | None = 24 * 7) -> dict[str, str]:
    """티커 → CIK(10자리 0패딩 문자열) 매핑을 반환한다.

    SEC EDGAR companyfacts 호출에 CIK 가 필요하다.
    """
    cache = _cik_cache_file()
    cached = None
    if cache.exists() and not refresh:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if _cache_fresh(cache, max_age_hours):
            return cached

    try:
        resp = requests.get(_SEC_TICKERS, headers={"User-Agent": settings.sec_user_agent}, timeout=30)
        resp.raise_for_status()
        raw = resp.json()  # {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        mapping: dict[str, str] = {}
        for row in raw.values():
            ticker = str(row["ticker"]).upper().replace(".", "-")
            mapping[ticker] = str(row["cik_str"]).zfill(10)
        cache.write_text(json.dumps(mapping), encoding="utf-8")
        return mapping
    except Exception:
        if cached is not None:
            return cached
        raise


def get_cik(ticker: str) -> str | None:
    """단일 티커의 CIK 를 반환(없으면 None)."""
    return get_ticker_cik_map().get(ticker.upper().replace(".", "-"))
