"""뉴스 감성분석 — 두 가지 방식.

★이 PC는 RAM 이 작다(≈4GB). PyTorch/FinBERT 는 1~2GB 를 먹어 메모리 고갈로
시스템 블루스크린(0x50)을 일으킨다. 그래서 **기본은 가벼운 사전(lexicon) 방식**이고,
FinBERT 는 메모리가 충분한 PC에서만 옵션('finbert')으로 쓴다.

방식:
  - "lexicon" (기본·권장): 금융 긍·부정 키워드 사전으로 점수화. 메모리 거의 0, 의존성 0.
  - "finbert" (옵션·고품질·고메모리): ProsusAI/finbert 로컬 모델. RAM 8GB+ 권장.

감성점수 정의: 헤드라인별 점수의 평균 (−1 ~ +1).
"""
from __future__ import annotations

import hashlib
import json
import re

from stock_ai.config import settings

# ───────────────────────── 가벼운 사전(lexicon) 방식 ─────────────────────────
# 금융 헤드라인에서 자주 쓰이는 긍·부정 표현. (소문자 기준)
_POS = {
    "beat", "beats", "surge", "surges", "soar", "soars", "gain", "gains", "rise",
    "rises", "jump", "jumps", "rally", "rallies", "record", "high", "highs",
    "strong", "growth", "grow", "grows", "profit", "profits", "upgrade",
    "upgrades", "outperform", "boost", "boosts", "optimistic", "win", "wins",
    "expand", "expands", "raise", "raised", "raises", "top", "tops", "exceed",
    "exceeds", "bullish", "recovery", "rebound", "approval", "approved",
    "partnership", "dividend", "buyback", "upbeat", "positive", "wins",
    "milestone", "breakthrough", "demand", "momentum",
}
_NEG = {
    "miss", "misses", "missed", "plunge", "plunges", "drop", "drops", "fall",
    "falls", "fell", "slump", "slumps", "decline", "declines", "loss", "losses",
    "cut", "cuts", "downgrade", "downgrades", "lawsuit", "probe", "investigation",
    "weak", "weakness", "warning", "warn", "warns", "layoff", "layoffs",
    "bankruptcy", "fraud", "recall", "fear", "fears", "bearish", "crash",
    "slowdown", "default", "deficit", "halt", "halts", "sink", "sinks",
    "tumble", "tumbles", "concern", "concerns", "risk", "risks", "delay",
    "delays", "shortfall", "negative", "scandal", "selloff", "downturn",
}
_WORD_RE = re.compile(r"[a-z']+")


def lexicon_score_headlines(headlines: list[str]) -> float | None:
    """금융 키워드 사전으로 헤드라인 평균 감성점수(−1~+1). 비어 있으면 None."""
    if not headlines:
        return None
    scores = []
    for h in headlines:
        words = _WORD_RE.findall(h.lower())
        pos = sum(1 for w in words if w in _POS)
        neg = sum(1 for w in words if w in _NEG)
        if pos + neg > 0:
            scores.append((pos - neg) / (pos + neg))
        else:
            scores.append(0.0)  # 감성어 없으면 중립
    return sum(scores) / len(scores) if scores else None


# ───────────────────────── FinBERT (옵션·고메모리) ─────────────────────────
_pipeline = None
_sent_cache: dict[str, float] | None = None
_LABEL_SIGN = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}


def _cache_file():
    return settings.cache_path / "sentiment_cache.json"


def _load_cache() -> dict[str, float]:
    global _sent_cache
    if _sent_cache is None:
        f = _cache_file()
        try:
            _sent_cache = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except json.JSONDecodeError:
            _sent_cache = {}
    return _sent_cache


def _save_cache() -> None:
    if _sent_cache is not None:
        _cache_file().write_text(json.dumps(_sent_cache, ensure_ascii=False), encoding="utf-8")


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _get_pipeline():
    """FinBERT 파이프라인 지연 로딩. ⚠️ 메모리 1~2GB 사용(저사양 PC 금지)."""
    global _pipeline
    if _pipeline is None:
        import torch  # 무겁다 — finbert 선택 시에만 import
        torch.set_num_threads(1)  # 전 코어 점유로 인한 과열/불안정 완화
        from transformers import pipeline
        _pipeline = pipeline("text-classification", model=settings.finbert_model,
                             top_k=None, truncation=True)
    return _pipeline


def finbert_score_headlines(headlines: list[str]) -> float | None:
    """FinBERT 로 헤드라인 평균 감성점수(−1~+1). 결과는 캐싱."""
    if not headlines:
        return None
    cache = _load_cache()
    todo = [h for h in headlines if _key(h) not in cache]
    if todo:
        pipe = _get_pipeline()
        for text, scores in zip(todo, pipe(todo)):
            cache[_key(text)] = float(
                sum(_LABEL_SIGN.get(s["label"].lower(), 0.0) * s["score"] for s in scores))
        _save_cache()
    vals = [cache[_key(h)] for h in headlines]
    return sum(vals) / len(vals) if vals else None


# ───────────────────────── 공용 진입점 ─────────────────────────
def score_headlines(headlines: list[str], method: str = "lexicon") -> float | None:
    if method == "finbert":
        return finbert_score_headlines(headlines)
    return lexicon_score_headlines(headlines)


def get_sentiment(ticker: str, limit: int = 15, method: str = "lexicon") -> float | None:
    """종목 뉴스 감성점수(−1~+1). 기본은 가벼운 lexicon 방식."""
    from stock_ai.data.news import get_headlines

    return score_headlines(get_headlines(ticker, limit=limit), method=method)
