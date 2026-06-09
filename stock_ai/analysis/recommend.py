"""추천 엔진 — 종합점수표 → 후보 선정 + 진입/청산 규칙 + 한국어 근거.

★중요: 여기서 만드는 것은 '예측'이 아니라 '규칙과 근거'다.
초보자가 스스로 판단할 수 있도록 모든 추천에 근거·리스크·진입/청산 규칙·제안 비중을 붙인다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from stock_ai.config import FACTOR_LABELS_KO

_AXES = ["value", "quality", "growth", "trend", "sentiment"]

# "(Class A)", "Class C", " - Class B" 같은 주식 종류 표기 제거용
_CLASS_RE = re.compile(r"[\s\-]*\(?\bclass\s+[a-c]\b\)?", re.IGNORECASE)


def _company_key(name: str, ticker: str) -> str:
    """같은 회사(클래스만 다른 이중상장)를 하나로 묶기 위한 키.

    예: 'Fox Corporation (Class A)' / '(Class B)' → 'fox corporation'
        'Alphabet Inc. (Class A)' / '(Class C)' → 'alphabet inc.'
    이름이 없으면 티커로 대체.
    """
    if name:
        base = _CLASS_RE.sub("", str(name)).strip().rstrip(" .,").lower()
        if base:
            return base
    return ticker.upper()


@dataclass
class Recommendation:
    ticker: str
    name: str
    sector: str
    price: float
    composite: float
    sub_scores: dict[str, float]          # 축 → 0~100
    coverage: float
    suggested_weight: float               # 0~1 (포트폴리오 내 제안 비중)
    confidence: str                       # 낮음 / 보통 / 비교적 높음
    why: list[str] = field(default_factory=list)        # 추천 이유(강점)
    risks: list[str] = field(default_factory=list)      # 리스크(약점)
    entry_rules: list[str] = field(default_factory=list)
    exit_rules: list[str] = field(default_factory=list)


def _confidence(coverage: float, composite: float) -> str:
    """데이터 커버리지와 점수로 신뢰도 라벨을 보수적으로 매긴다."""
    if coverage < 0.6:
        return "낮음(데이터 부족)"
    if composite >= 75 and coverage >= 0.8:
        return "비교적 높음"
    if composite >= 60:
        return "보통"
    return "낮음"


def _why_and_risks(row: pd.Series) -> tuple[list[str], list[str]]:
    """축별 점수에서 강점(why)·약점(risks)을 한국어 문장으로 만든다."""
    subs = {a: row.get(f"score_{a}") for a in _AXES}
    valid = {a: v for a, v in subs.items() if pd.notna(v)}
    why, risks = [], []

    # 강점: 상위 2개 축(>=60)
    for axis, v in sorted(valid.items(), key=lambda kv: kv[1], reverse=True)[:2]:
        if v >= 60:
            why.append(f"{FACTOR_LABELS_KO[axis]} 점수 상위권({v:.0f}점)")
    # 약점: 하위 축(<40)
    for axis, v in sorted(valid.items(), key=lambda kv: kv[1])[:2]:
        if v < 40:
            risks.append(f"{FACTOR_LABELS_KO[axis]}가 약함({v:.0f}점)")

    # 구체 리스크: 부채·적자·추세
    if pd.notna(row.get("debt_ratio")) and row["debt_ratio"] > 0.7:
        risks.append(f"부채비율 높음({row['debt_ratio']*100:.0f}%)")
    if pd.notna(row.get("above_200d")) and row["above_200d"] < 0:
        risks.append("현재가가 200일 평균선 아래(하락 추세 가능)")
    if row.get("coverage", 1.0) < 0.8:
        risks.append("일부 데이터 결손(아래 점수의 신뢰도 주의)")

    if not why:
        why.append("뚜렷한 최상위 강점은 없으나 종합점수가 집단 내 상위")
    return why, risks


def _entry_rules(row: pd.Series) -> list[str]:
    """장기투자용 진입(매수 시점) 규칙 — 분할매수 기본."""
    rules = ["한 번에 사지 말고 3회 이상 나눠 분할매수(평균단가 분산)"]
    above = row.get("above_200d")
    if pd.notna(above):
        if above >= -0.02:
            rules.append("현재가가 200일선 위/근처 → 지금부터 분할매수 고려 가능")
        else:
            rules.append("현재가가 200일선 아래 → 추세 회복(200일선 회복) 확인 후 진입 권장")
    rules.append("단기 급등 직후(과열)라면 눌림목까지 기다리기")
    return rules


def _exit_rules() -> list[str]:
    """장기투자용 청산(매도 시점) 규칙 — '예측'이 아니라 '규칙'."""
    return [
        "트레일링 손절: 매수 후 고점 대비 -20% 하락하면 기계적으로 매도",
        "추세 이탈: 종가가 200일 평균선을 의미 있게 하향 이탈하면 비중 축소",
        "펀더멘털 악화: 다음 분석에서 종합점수가 컷오프(예: 50점) 아래로 내려가면 교체",
        "※ 이 규칙들은 '고점 예측'이 아니라 손실을 제한하기 위한 사전 약속이다",
    ]


def build_recommendations(
    score_df: pd.DataFrame,
    top_n: int = 10,
    max_per_sector: int = 3,
    max_weight: float = 0.10,
    min_coverage: float = 0.4,
) -> list[Recommendation]:
    """종합점수표에서 추천 종목 리스트를 만든다(섹터 분산 + 비중 제안).

    Args:
        top_n: 추천 종목 수.
        max_per_sector: 한 섹터 최대 종목 수(분산).
        max_weight: 종목당 최대 제안 비중.
        min_coverage: 이 미만 데이터 커버리지 종목은 제외.
    """
    if score_df is None or score_df.empty:
        return []

    pool = score_df[score_df["coverage"] >= min_coverage].copy()
    pool = pool.sort_values("composite", ascending=False)

    # 섹터 분산 + 이중상장(같은 회사) 중복 제거 그리디 선택
    selected = []
    sector_count: dict[str, int] = {}
    seen_companies: set[str] = set()
    for ticker, row in pool.iterrows():
        # 같은 회사가 이미 뽑혔으면 건너뜀 (FOX/FOXA, GOOG/GOOGL 등)
        ckey = _company_key(row.get("name", ""), ticker)
        if ckey in seen_companies:
            continue
        sector = row.get("sector") or "Unknown"
        if sector_count.get(sector, 0) >= max_per_sector:
            continue
        selected.append((ticker, row))
        seen_companies.add(ckey)
        sector_count[sector] = sector_count.get(sector, 0) + 1
        if len(selected) >= top_n:
            break

    if not selected:
        return []

    # 동일가중(상한 적용). 합이 1 미만이면 나머지는 현금 권유.
    n = len(selected)
    weight = min(1.0 / n, max_weight)

    recs: list[Recommendation] = []
    for ticker, row in selected:
        subs = {a: (float(row[f"score_{a}"]) if pd.notna(row[f"score_{a}"]) else float("nan"))
                for a in _AXES}
        why, risks = _why_and_risks(row)
        recs.append(Recommendation(
            ticker=ticker,
            name=str(row.get("name", "")),
            sector=str(row.get("sector", "")),
            price=float(row.get("price")) if pd.notna(row.get("price")) else float("nan"),
            composite=float(row["composite"]),
            sub_scores=subs,
            coverage=float(row.get("coverage", np.nan)),
            suggested_weight=weight,
            confidence=_confidence(float(row.get("coverage", 0)), float(row["composite"])),
            why=why,
            risks=risks,
            entry_rules=_entry_rules(row),
            exit_rules=_exit_rules(),
        ))
    return recs


def cash_buffer(recs: list[Recommendation]) -> float:
    """추천 비중 합 외 현금 권유 비율."""
    invested = sum(r.suggested_weight for r in recs)
    return max(0.0, 1.0 - invested)


# ──────────────────────────────────────────────────────────────────────────
# 클라이언트 가중치 슬라이더용 — "서버 순위 == 브라우저 순위" 보장 코어.
#
# 5축 서브점수(score_*)는 가중치와 무관한 횡단면 백분위라 한 번만 계산되고 고정이다.
# 종합점수·종목 선정·신뢰도만 가중치에 의존하므로, 아래 세 순수 함수만 브라우저 JS로
# 그대로 포팅하면(_RANK_JS) 어떤 가중치에서도 서버 결과와 수학적으로 동일하다.
# 이 명세는 tests/test_rank_parity.py 가 score.py/build_recommendations 와 대조해 고정한다.
# ──────────────────────────────────────────────────────────────────────────

def compute_composite(sub_scores: list, weights: list) -> float:
    """축 점수(0~100, 결측은 None)와 가중치 → 종합점수.

    score.compute_scores 와 동일한 규칙: 결측 축은 분모(가중치 합)에서 제외한 가중 평균.
    JS computeComposite 가 1:1로 미러링한다.
    """
    num = 0.0
    den = 0.0
    for v, w in zip(sub_scores, weights):
        if v is None or v != v:  # None 또는 NaN
            continue
        num += float(v) * float(w)
        den += float(w)
    return num / den if den > 0 else float("nan")


def confidence_label(coverage: float, composite: float) -> str:
    """_confidence 의 공개 래퍼(JS confidence 가 미러링)."""
    return _confidence(coverage, composite)


def select_from_universe(
    universe: list[dict],
    weights: list[float],
    top_n: int = 10,
    max_per_sector: int = 3,
    min_coverage: float = 0.4,
) -> list[str]:
    """임베드용 universe(압축 dict 리스트)에서 가중치로 재선정한 티커 순서.

    build_recommendations 의 그리디 선택(섹터 분산 + 이중상장 제거)을 그대로 재현한다.
    JS select() 가 1:1로 미러링한다. 반환은 선택된 티커 리스트(순위 순).
    """
    scored = []
    for item in universe:
        cov = item.get("cov", 0.0) or 0.0
        if cov < min_coverage:
            continue
        comp = compute_composite(item.get("sc", []), weights)
        if comp != comp:  # NaN
            continue
        scored.append((comp, item))
    # composite 내림차순. 극히 드문 동점은 티커로 안정 정렬(JS와 동일 규칙).
    scored.sort(key=lambda cv: (-cv[0], cv[1].get("t", "")))

    selected: list[str] = []
    sector_count: dict[str, int] = {}
    seen_companies: set[str] = set()
    for _, item in scored:
        ticker = str(item.get("t", "")).upper()
        ckey = _company_key(item.get("n", ""), ticker)
        if ckey in seen_companies:
            continue
        sector = item.get("s") or "Unknown"
        if sector_count.get(sector, 0) >= max_per_sector:
            continue
        selected.append(ticker)
        seen_companies.add(ckey)
        sector_count[sector] = sector_count.get(sector, 0) + 1
        if len(selected) >= top_n:
            break
    return selected


def build_score_universe(score_df: pd.DataFrame, min_coverage: float = 0.4) -> list[dict]:
    """종합점수표 → 브라우저 슬라이더용 압축 종목 데이터.

    키는 임베드 용량을 줄이려 짧게 쓴다:
        t=ticker, n=name, s=sector, p=price, cov=coverage,
        sc=[value,quality,growth,trend,sentiment](0~100 또는 None),
        why=강점 문장, risks=리스크 문장.
    why/risks 는 가중치와 무관하므로 여기서 한 번만 만들어 심는다(JS 재계산 불필요).
    """
    if score_df is None or score_df.empty:
        return []
    out: list[dict] = []
    for ticker, row in score_df.iterrows():
        cov = row.get("coverage")
        cov = float(cov) if pd.notna(cov) else 0.0
        if cov < min_coverage:
            continue
        sc = []
        for a in _AXES:
            v = row.get(f"score_{a}")
            sc.append(round(float(v), 1) if pd.notna(v) else None)
        price = row.get("price")
        why, risks = _why_and_risks(row)
        out.append({
            "t": str(ticker).upper(),
            "n": str(row.get("name", "") or ""),
            "s": str(row.get("sector", "") or ""),
            "p": float(price) if pd.notna(price) else None,
            "cov": round(cov, 3),
            "sc": sc,
            "why": why,
            "risks": risks,
        })
    return out
