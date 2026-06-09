"""브라우저 가중치 슬라이더 재랭킹의 '서버==클라' 보장 명세 고정.

recommend_report.py 의 _RANK_JS(브라우저 JS)는 아래 순수 함수들을 1:1 미러링한다:
    JS composite()   <-> compute_composite()
    JS selectTop()   <-> select_from_universe()
    JS confidence()  <-> confidence_label()
이 테스트가 깨지면 JS 미러도 함께 어긋난 것이므로 양쪽을 같이 고쳐야 한다.
"""
import pytest

from stock_ai.analysis.factors import FactorRaw
from stock_ai.analysis.score import compute_scores
from stock_ai.analysis.recommend import (
    _AXES,
    build_recommendations,
    build_score_universe,
    compute_composite,
    confidence_label,
    select_from_universe,
)
from stock_ai.config import FACTOR_WEIGHT_PRESETS


def _raw(ticker, pe, roe, growth, mom, sent, sector="Tech", name=None):
    return FactorRaw(
        ticker=ticker, pe=pe, pb=pe / 5, roe=roe, net_margin=roe / 2,
        debt_ratio=0.4, revenue_growth=growth, eps_growth=growth,
        above_200d=mom, momentum_12m=mom, sentiment=sent, price=100.0,
        sector=sector, name=name or ticker,
    )


def _sample_raws():
    raws = [
        _raw("AAA", pe=6, roe=0.32, growth=0.30, mom=0.40, sent=0.8, sector="Tech"),
        _raw("BBB", pe=9, roe=0.28, growth=0.22, mom=0.30, sent=0.5, sector="Tech"),
        _raw("CCC", pe=14, roe=0.20, growth=0.14, mom=0.18, sent=0.2, sector="Tech"),
        _raw("DDD", pe=8, roe=0.26, growth=0.10, mom=0.05, sent=0.1, sector="Fin"),
        _raw("EEE", pe=11, roe=0.18, growth=0.08, mom=-0.05, sent=-0.1, sector="Fin"),
        _raw("FFF", pe=18, roe=0.12, growth=0.04, mom=-0.15, sent=-0.3, sector="Fin"),
        _raw("GGG", pe=7, roe=0.30, growth=0.26, mom=0.22, sent=0.4, sector="Health"),
        _raw("HHH", pe=22, roe=0.10, growth=-0.05, mom=-0.25, sent=-0.6, sector="Health"),
        # 같은 회사 이중상장(클래스만 다름) — 하나만 선택되어야 한다.
        _raw("FOX", pe=10, roe=0.24, growth=0.16, mom=0.20, sent=0.3, sector="Media",
             name="Fox Corporation (Class B)"),
        _raw("FOXA", pe=10, roe=0.24, growth=0.16, mom=0.20, sent=0.3, sector="Media",
             name="Fox Corporation (Class A)"),
    ]
    return raws


def _wlist(style):
    preset = FACTOR_WEIGHT_PRESETS[style]
    return [preset[a] for a in _AXES]


def test_compute_composite_matches_score_engine():
    """compute_composite(서브점수, 가중치) == score.compute_scores 의 composite."""
    raws = _sample_raws()
    for style in ("balanced", "momentum", "dividend"):
        df = compute_scores(raws, weights=FACTOR_WEIGHT_PRESETS[style])
        universe = {it["t"]: it for it in build_score_universe(df)}
        wl = _wlist(style)
        for ticker, item in universe.items():
            got = compute_composite(item["sc"], wl)
            want = float(df.loc[ticker, "composite"])
            # sc 는 0.1 단위로 반올림되어 미세 오차 가능.
            assert got == pytest.approx(want, abs=0.2), f"{style}/{ticker}: {got} != {want}"


def test_selection_matches_build_recommendations():
    """select_from_universe 의 순위가 build_recommendations 와 정확히 일치."""
    raws = _sample_raws()
    # 서브점수는 가중치 무관 → universe 는 한 번만 만들어도 모든 성향에 유효.
    base_df = compute_scores(raws, weights=FACTOR_WEIGHT_PRESETS["balanced"])
    universe = build_score_universe(base_df)
    for style in ("balanced", "momentum", "dividend"):
        df = compute_scores(raws, weights=FACTOR_WEIGHT_PRESETS[style])
        recs = build_recommendations(df, top_n=6, max_per_sector=2)
        server = [r.ticker for r in recs]
        client = select_from_universe(universe, _wlist(style), top_n=6, max_per_sector=2)
        assert client == server, f"{style}: {client} != {server}"


def test_double_listing_deduplicated():
    """이중상장(FOX/FOXA)은 클라 선정에서도 하나만 남아야 한다."""
    raws = _sample_raws()
    df = compute_scores(raws, weights=FACTOR_WEIGHT_PRESETS["balanced"])
    universe = build_score_universe(df)
    picked = select_from_universe(universe, _wlist("balanced"), top_n=10, max_per_sector=5)
    assert not ("FOX" in picked and "FOXA" in picked)


def test_confidence_label_spec():
    """JS confidence() 가 미러링하는 분기 명세를 고정."""
    assert confidence_label(0.4, 90) == "낮음(데이터 부족)"
    assert confidence_label(0.8, 80) == "비교적 높음"
    assert confidence_label(1.0, 65) == "보통"
    assert confidence_label(1.0, 40) == "낮음"
