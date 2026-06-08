"""미국 주식 종합분석 대시보드 (Streamlit).

실행:
    streamlit run app.py
브라우저가 열리면 ① 종목 즉시 판단기 ② 전체 추천을 그 자리에서 라이브로 쓸 수 있다.

⚠️ 투자 자문 아님 · 수익 보장 없음 · '점쟁이'가 아니라 근거를 정리해 주는 '조수'.
메모리 안전: torch(FinBERT) 미사용, 가벼운 키워드 감성만 기본 사용.
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from stock_ai.analysis.judge import judge_ticker
from stock_ai.config import FACTOR_LABELS_KO, STYLE_LABELS_KO, FACTOR_WEIGHT_PRESETS
from stock_ai.runner import recommend_universe

st.set_page_config(page_title="미국 주식 종합분석 조수", page_icon="📊", layout="wide")

_COLOR = {"green": "#16a34a", "amber": "#f59e0b", "red": "#dc2626", "gray": "#6b7280"}

st.title("📊 미국 주식 종합분석 조수")
st.warning(
    "⚠️ **투자 자문이 아니며 수익을 보장하지 않습니다.** 이 도구는 미래를 맞히는 '점쟁이'가 아니라, "
    "그 순간의 공개 데이터(가격·SEC 재무·뉴스)를 종합해 **근거와 규칙**을 정리해 주는 '조수'입니다. "
    "최종 판단·책임은 본인에게 있습니다. 실제 매수 전 소액·모의로 검증하세요."
)

tab1, tab2 = st.tabs(["🔎 종목 즉시 판단", "🏆 전체 추천(S&P500)"])

# ───────────────────────── 탭 1: 종목 즉시 판단 ─────────────────────────
with tab1:
    st.subheader("티커를 입력하면 '지금' 데이터로 판단합니다")
    col_in, col_btn = st.columns([3, 1])
    with col_in:
        ticker = st.text_input("미국 티커 (예: AAPL, MSFT, NVDA)", value="AAPL",
                               label_visibility="collapsed").strip().upper()
    with col_btn:
        go = st.button("지금 판단", type="primary", use_container_width=True)

    if go and ticker:
        with st.spinner(f"{ticker} 의 최신 데이터를 가져와 분석 중…"):
            j = judge_ticker(ticker, live=True)

        st.markdown(
            f"<div style='padding:16px 20px;border-radius:12px;background:{_COLOR[j.color]}15;"
            f"border:2px solid {_COLOR[j.color]}'>"
            f"<span style='font-size:26px;font-weight:800;color:{_COLOR[j.color]}'>{j.verdict}</span>"
            f"<span style='color:#475569'> &nbsp; ({ticker}, 기준일 {j.as_of})</span><br>"
            f"<span style='font-size:15px'>{j.headline}</span></div>",
            unsafe_allow_html=True,
        )

        if j.verdict != "데이터부족":
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("현재가", f"${j.price:,.2f}")
            c2.metric("200일선 대비", f"{(j.price/j.sma200-1)*100:+.1f}%" if j.sma200 else "—")
            c3.metric("RSI(14)", f"{j.rsi:.0f}")
            c4.metric("P/E", f"{j.pe:.1f}" if j.pe == j.pe else "—")
            c5.metric("ROE", f"{j.roe*100:.0f}%" if j.roe == j.roe else "—")

            st.markdown("#### 🧩 종합 근거")
            for r in j.reasons:
                st.markdown(f"- {r}")

            colA, colB = st.columns(2)
            with colA:
                st.markdown("#### 🟢 매수(진입) 규칙")
                for r in j.entry_rules:
                    st.markdown(f"- {r}")
            with colB:
                st.markdown("#### 🔴 매도(청산) 규칙")
                for r in j.exit_rules:
                    st.markdown(f"- {r}")
        st.caption("※ 이 판단은 예측이 아니라 추세·재무·심리를 종합한 '규칙 기반 신호'입니다.")

# ───────────────────────── 탭 2: 전체 추천 ─────────────────────────
with tab2:
    st.subheader("S&P500을 종합분석해 후보를 추립니다")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        style = st.selectbox("투자 성향", list(FACTOR_WEIGHT_PRESETS.keys()),
                             format_func=lambda s: STYLE_LABELS_KO.get(s, s))
    with c2:
        top = st.slider("추천 종목 수", 5, 20, 10)
    with c3:
        limit = st.selectbox("분석 범위", [40, 100, 0],
                             format_func=lambda x: "전체 503종목(수 분)" if x == 0 else f"섹터 균형 {x}종목(빠름)")

    if st.button("분석 실행", type="primary"):
        with st.spinner("종합분석 중… (전체는 수 분 걸릴 수 있습니다)"):
            recs, score_df, portfolio, report = recommend_universe(
                top_n=top, limit=(limit or None), sentiment_method="lexicon",
                weights=FACTOR_WEIGHT_PRESETS[style], style=style,
                make_report=True, progress=False,
            )
        if not recs:
            st.error("추천 종목을 만들지 못했습니다(데이터 부족).")
        else:
            # 정직한 백테스트 핵심 지표
            if portfolio is not None:
                m = portfolio.metrics
                sel = m.get("선택초과_총수익률")
                oos = getattr(portfolio, "oos_metrics", None)
                msg = (f"**선택 초과수익(전략 − 동일가중): "
                       f"{('+' if (sel or 0)>=0 else '')}{(sel or 0)*100:.1f}%p** "
                       f"— 둘 다 같은 생존편향을 공유하므로 이 차이만이 '선택'의 가치입니다.")
                if oos and "선택초과_총수익률" in oos:
                    o = oos["선택초과_총수익률"]
                    msg += f" (아웃오브샘플: {('+' if o>=0 else '')}{o*100:.1f}%p)"
                st.info(msg)
                st.caption(f"절대수익(생존편향으로 부풀려짐, 참고만): 전략 {m.get('총수익률',0)*100:.0f}% · "
                           f"동일가중 {m.get('동일가중_총수익률',0)*100:.0f}% · SPY {m.get('벤치마크_총수익률',0)*100:.0f}%")

            st.markdown(f"#### 🏆 추천 상위 {len(recs)}종목 — {STYLE_LABELS_KO.get(style, style)}")
            import pandas as pd
            tbl = pd.DataFrame([{
                "티커": r.ticker, "회사": r.name, "섹터": r.sector,
                "종합점수": round(r.composite), "제안비중": f"{r.suggested_weight*100:.0f}%",
                "신뢰도": r.confidence,
            } for r in recs])
            st.dataframe(tbl, use_container_width=True, hide_index=True)

            for r in recs:
                with st.expander(f"{r.ticker} · {r.name}  —  종합 {r.composite:.0f}점 / 신뢰도 {r.confidence}"):
                    subs = " · ".join(
                        f"{FACTOR_LABELS_KO[a]} {r.sub_scores.get(a):.0f}"
                        for a in ["value", "quality", "growth", "trend", "sentiment"]
                        if r.sub_scores.get(a) == r.sub_scores.get(a)
                    )
                    st.markdown(f"**5축 점수:** {subs}")
                    cA, cB = st.columns(2)
                    with cA:
                        st.markdown("**👍 왜 추천**")
                        for w in r.why:
                            st.markdown(f"- {w}")
                        st.markdown("**🟢 진입 규칙**")
                        for w in r.entry_rules:
                            st.markdown(f"- {w}")
                    with cB:
                        st.markdown("**⚠️ 리스크**")
                        for w in r.risks:
                            st.markdown(f"- {w}")
                        st.markdown("**🔴 청산 규칙**")
                        for w in r.exit_rules:
                            st.markdown(f"- {w}")
            if report:
                st.caption(f"상세 HTML 리포트도 생성됨: {report}")

st.divider()
st.caption(f"갱신 {dt.datetime.now():%Y-%m-%d %H:%M} · 데이터: yfinance(가격), SEC EDGAR(재무), "
           "뉴스 키워드 감성 · 모든 데이터 무료")
