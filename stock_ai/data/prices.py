"""가격(OHLCV) 데이터 수집 + SQLite 캐싱.

- yfinance 로 미국주식 일봉을 받아 SQLite 에 저장한다.
- 같은 종목을 다시 요청하면 캐시를 우선 사용하고, 모자란 기간만 추가로 받는다.
- 컬럼은 소문자 open/high/low/close/volume 로 표준화한다.
- 수정주가(adjusted) 기준을 쓴다(배당·액면분할 반영) → 장기 백테스트 왜곡 방지.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pandas as pd

from stock_ai.config import settings

# 표준 컬럼 순서
_COLUMNS = ["open", "high", "low", "close", "volume"]


def _connect() -> sqlite3.Connection:
    """SQLite 연결을 연다. 테이블이 없으면 만든다."""
    conn = sqlite3.connect(settings.db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prices (
            ticker TEXT NOT NULL,
            date   TEXT NOT NULL,   -- ISO 날짜 (YYYY-MM-DD)
            open   REAL,
            high   REAL,
            low    REAL,
            close  REAL,
            volume REAL,
            PRIMARY KEY (ticker, date)
        )
        """
    )
    return conn


def _download(ticker: str, start: str | None, end: str | None) -> pd.DataFrame:
    """yfinance 로 일봉을 내려받아 표준 형식으로 반환한다.

    auto_adjust=True 로 수정주가를 받는다. 반환 인덱스는 tz 없는 날짜.
    """
    import yfinance as yf

    raw = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        actions=False,
        timeout=30,   # 네트워크 행(무한 대기) 방지
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=_COLUMNS)

    # yfinance 가 단일 종목에도 MultiIndex 컬럼을 줄 때가 있어 평탄화한다.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.rename(columns=str.lower)
    raw = raw[[c for c in _COLUMNS if c in raw.columns]].copy()
    raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
    raw.index.name = "date"
    return raw.dropna(how="all")


def _read_cache(conn: sqlite3.Connection, ticker: str) -> pd.DataFrame:
    """캐시에 저장된 해당 종목 데이터를 모두 읽어온다."""
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM prices "
        "WHERE ticker = ? ORDER BY date",
        conn,
        params=(ticker,),
        parse_dates=["date"],
    )
    if df.empty:
        return df
    return df.set_index("date")


def _write_cache(conn: sqlite3.Connection, ticker: str, df: pd.DataFrame) -> None:
    """데이터프레임을 캐시에 upsert(있으면 교체)한다."""
    rows = [
        (ticker, idx.strftime("%Y-%m-%d"),
         float(r.open), float(r.high), float(r.low), float(r.close), float(r.volume))
        for idx, r in df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO prices "
        "(ticker, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


def get_prices(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """종목의 일봉 OHLCV 를 반환한다 (캐시 우선).

    Args:
        ticker: 미국주식 티커 (예: "AAPL").
        start: 시작일 "YYYY-MM-DD" (None 이면 가능한 전체).
        end: 종료일 "YYYY-MM-DD" (None 이면 오늘까지).
        use_cache: True 면 캐시에 충분히 있을 때 네트워크를 건너뛴다.

    Returns:
        date 인덱스 + open/high/low/close/volume 컬럼 데이터프레임.
    """
    ticker = ticker.upper().strip()
    conn = _connect()
    try:
        cached = _read_cache(conn, ticker) if use_cache else pd.DataFrame()

        # 캐시가 요청 구간을 충분히 덮는지 판단
        need_download = True
        if not cached.empty:
            have_start = cached.index.min()
            have_end = cached.index.max()
            req_start = pd.Timestamp(start) if start else have_start
            req_end = pd.Timestamp(end) if end else pd.Timestamp(datetime.now().date())
            # 캐시가 요청 시작 이전 ~ 요청 종료 근처(5일 여유)까지 있으면 재다운로드 불필요
            if have_start <= req_start and have_end >= (req_end - pd.Timedelta(days=5)):
                need_download = False

        if need_download:
            fresh = _download(ticker, start, end)
            if not fresh.empty:
                _write_cache(conn, ticker, fresh)
            cached = _read_cache(conn, ticker)

        if cached.empty:
            raise ValueError(
                f"'{ticker}' 데이터를 가져오지 못했습니다. 티커·기간·네트워크를 확인하세요."
            )

        # 요청 구간으로 잘라 반환
        out = cached
        if start:
            out = out[out.index >= pd.Timestamp(start)]
        if end:
            out = out[out.index <= pd.Timestamp(end)]
        return out.copy()
    finally:
        conn.close()
