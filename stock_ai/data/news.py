"""뉴스 헤드라인 수집 — 무료 소스(yfinance, 선택적으로 Finnhub).

감성분석(analysis/sentiment.py)에 넣을 최근 헤드라인 문자열 리스트를 모은다.
헤드라인은 종목당 캐싱한다(과도한 호출 방지).
"""
from __future__ import annotations

import json
import time

from stock_ai.config import settings


def _news_cache_file(ticker: str):
    d = settings.cache_path / "news"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{ticker.upper()}.json"


def _from_yfinance(ticker: str, limit: int) -> list[str]:
    """yfinance 의 뉴스에서 헤드라인 제목을 뽑는다(버전별 형식 차이 방어)."""
    import yfinance as yf

    titles: list[str] = []
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return titles
    for it in items:
        title = None
        if isinstance(it, dict):
            # 구버전: {'title': ...} / 신버전: {'content': {'title': ...}}
            title = it.get("title")
            if not title and isinstance(it.get("content"), dict):
                title = it["content"].get("title")
        if title:
            titles.append(str(title).strip())
        if len(titles) >= limit:
            break
    return titles


def _from_finnhub(ticker: str, limit: int) -> list[str]:
    """(선택) Finnhub 무료 키가 있으면 회사 뉴스 헤드라인을 추가로 받는다."""
    if not settings.finnhub_api_key:
        return []
    import datetime as dt

    import requests

    today = dt.date.today()
    frm = today - dt.timedelta(days=30)
    url = (
        "https://finnhub.io/api/v1/company-news"
        f"?symbol={ticker.upper()}&from={frm}&to={today}&token={settings.finnhub_api_key}"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return [str(d["headline"]).strip() for d in data[:limit] if d.get("headline")]
    except Exception:
        return []


def get_headlines(ticker: str, limit: int = 15, max_age_hours: float = 24.0,
                  refresh: bool = False) -> list[str]:
    """종목의 최근 헤드라인 리스트를 반환한다(캐싱).

    Args:
        limit: 최대 헤드라인 수.
        max_age_hours: 캐시 유효 시간(시간). 지나면 다시 받는다.
        refresh: True 면 캐시 무시하고 새로 받는다.
    """
    ticker = ticker.upper()
    cache = _news_cache_file(ticker)
    if cache.exists() and not refresh:
        try:
            blob = json.loads(cache.read_text(encoding="utf-8"))
            age = (time.time() - blob.get("ts", 0)) / 3600.0
            if age <= max_age_hours:
                return blob.get("headlines", [])
        except json.JSONDecodeError:
            pass

    headlines = _from_yfinance(ticker, limit)
    headlines += _from_finnhub(ticker, limit)
    # 중복 제거(순서 유지)
    seen = set()
    uniq = [h for h in headlines if not (h in seen or seen.add(h))][:limit]

    cache.write_text(json.dumps({"ts": time.time(), "headlines": uniq}, ensure_ascii=False),
                     encoding="utf-8")
    return uniq
