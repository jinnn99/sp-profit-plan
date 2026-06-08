# 주식관련AI — 인수인계 (→ Codex)

작성일: 2026-06-09
프로젝트: `C:\Users\jin\Desktop\주식관련AI`
배포 주소(영구): https://sweetproduct.netlify.app
핵심 리포트 파일: `S&P_수익&플랜.html` (생성기가 덮어씀)
배포 대상 폴더: `mobile_app/`

> 이 문서는 2026-06-08 인수인계(`Documents\Codex\...\stock_ai_handoff_for_claude.md`) 이후
> Claude 세션에서 진행한 변경을 반영한 **현재 상태** 기준 문서다. 이전 문서를 대체한다.

---

## 0. 절대 규칙 (변경 금지)

- **비용 원칙이 최우선:** 이 앱은 월 플랫폼 비용 **$0 목표**로 운영한다. 유료 API, 결제 계정, free tier 초과 가능성, always-on 서버, 유료 배포 플랫폼, 저장소/크론/트래픽 증가 등 비용 발생 가능성이 있는 변경은 **구현·권장 전에 반드시 사용자에게 경고하고 명시 승인을 받아야 한다.** 비용 위험이 불확실하면 먼저 멈추고 질문한다.
- **리포트 업데이트 대상은 `S&P_수익&플랜.html` 한 파일.** 파일명(한글·`&`)은 바꾸지 않는다.
- **배포 대상은 `mobile_app/` 폴더.** Netlify에 이 폴더를 드롭한다.
- 생성기(`stock_ai/report/recommend_report.py`)가 **single source of truth**. 리포트는 여기서 찍어낸다.
- 사용자 요청으로 **면책/주의 문구는 전부 제거된 상태**(아래 9번 참고). 임의로 되살리지 말 것.

### 0.1 현재 비용/운영 방향

- 무료 우선 아키텍처: **GitHub Actions + Cloudflare Pages/Workers + Cloudflare D1/KV 동기화 코드**.
- 종합분석은 GitHub Actions로 주기 실행하고, 보유 종목 가격은 Cloudflare Worker에서 보수적으로 캐시해 조회한다.
- 유료로 전환될 수 있는 대표 위험: GitHub Actions 무료 시간 초과, Cloudflare 무료 한도 초과, 유료/실시간 시세 API 도입, always-on 서버(Render/Railway/VPS/Cloud Run min instance 등), 커스텀 도메인/고급 로그/스토리지 과다 사용.
- 다른 Codex/Claude 작업자는 비용 관련 변경을 최우선 검토 대상으로 삼고, 무료 경로를 먼저 제안한다.

---

## 1. 현재 리포트의 모습 (UI 상태)

페이지 구성(위→아래):
1. **히어로** — 모노 아이브로우(`S&P 500 · 종합분석 스크리너`) + 2줄 제목(`미국 주식 종합분석` / `추천 리포트`) + 리드 1문장 + **컨트롤 바**.
   - 컨트롤 바: `투자성향` 고정 라벨 + **토글 알약 3개**(Balance / Risk Taker / Conservative) + **↻ 갱신** 버튼 + `마지막 갱신 yyyy-mm-dd hh:mm`.
2. **추천 종목 분석** — 6열 표: `# / 종목 / 점수 / 신뢰도 / 핵심 근거 / 주요 리스크`.
   - 종목 칸: 티커 + 회사명 + **영어 업종**(예: Oil & gas exploration). 점수 칸은 점수만(비중 없음).
3. **종목별 상세** — 상단에 **공통 매매 규칙**(진입·청산 한 블록, 종목 공통) + 그 아래 **카드 그리드**(2열/모바일 1열).
   - 카드: 티커·회사명·업종·점수 / 현재가·신뢰도 / 5축 점수 막대 / 왜 추천?·리스크. (카드별 진입·청산 규칙은 없음 — 공통 블록으로 합침.)
4. **내 보유 종목** — 동기화 코드 + 수량/평균 매입가 입력 + 현재가·평가손익·상태 표시.
   - (히어로 메타줄·표 하단 안내문·푸터·면책배너는 사용자 요청으로 모두 제거됨.)

### 인터랙션 (정적 배포에서 동작, 서버 불필요)
- **투자성향 토글**: 3개 성향 순위를 빌드시 미리 계산해 `window.REPORT_DATA`(JSON)로 심음 → 클릭 시 JS가 표 `tbody`(id=`analysis-body`)와 카드(id=`cards`)의 `innerHTML`을 교체. 선택은 `localStorage('sp_style')`에 기억.
- **갱신 버튼**: 서비스워커 `update()` 후 `location.reload()` → **최신 배포본 로드**. 종합분석 순위는 GitHub Actions 재실행+Cloudflare Pages 배포로 갱신.
- **내 보유 종목**: `window.HOLDING_UNIVERSE`에 분석 종목의 티커/회사명/업종/가격을 심고, `/api/quotes`에서 5분 캐시 가격을 받아 평가손익을 갱신. 동기화 코드는 `/api/sync-code`, `/api/holdings/{code}`가 Cloudflare D1에 저장.
- JS·토글 데이터는 `recommend_report.py`의 `_TOGGLE_JS`, 보유 종목은 `_HOLDINGS_JS` + `build_recommend_report()`에서 생성.

---

## 2. 디자인 시스템 (Anthropic풍)

`recommend_report.py`의 `_STYLE`(CSS) + 본문 템플릿에 모두 들어있음. 토큰:

- 배경 `--paper:#f3f1ea`(따뜻한 아이보리), 카드 `--card:#fcfbf8`, 잉크 `--ink:#1c1b17`, 보조 `--body:#5e5c54`, 뮤트 `--mute:#8c887e`, 헤어라인 `--line:#e6e1d6`.
- 악센트(코랄/클레이): `--clay:#c0603d`, `--clay-soft:#d79a78`, `--clay-weak:#c2bbab`. 다크밴드 `--charcoal:#26231f`.
- **폰트**: 본문/라벨/한국어 헤더 = **Inter**(한국어는 Malgun Gothic 폴백, 헤더는 700). 영어 티커·점수만 **Newsreader(세리프)** 악센트(`.tk/.sc/.rank-ticker/.composite`). 모노는 사용 안 함.
  - ⚠️ Newsreader는 라틴 전용 → **한국어 헤더는 반드시 Inter(sans)로**. (세리프로 두면 얇은 시스템 세리프로 폴백돼 어색함. 이미 수정됨.)
- **점수 막대**: 코랄 농담 — `hi`(≥60) `--clay`, `mid`(40–59) `--clay-soft`, `lo`(<40) `--clay-weak`. (`_bar()`가 tier 클래스 부여.)
- **표 안정화**: `table.analysis{ table-layout:fixed }` + `<colgroup>`(6/24/9/12/24/25%)로 **성향을 바꿔도 열 위치 고정**. 한국어 줄바꿈은 `word-break:keep-all`.
- 여백은 한 차례 축소된 상태(섹션 64px 등).

---

## 3. 데이터 → 리포트 파이프라인

```powershell
cd "C:\Users\jin\Desktop\주식관련AI"
python -m stock_ai recommend --top 10 --limit 0 --no-sentiment   # 전체 S&P500, 감성 off
python export_mobile_app.py                                       # mobile_app/ + zip 동기화
```
- `recommend`가 `S&P_수익&플랜.html`을 덮어씀. 워밍된 캐시면 네트워크 없이 ~5–7분(503종목 5축 점수 계산).
- `runner.recommend_universe()`가 **raws(무거운 부분)를 1회만** 만들고, 가중치만 바꿔 **3개 성향**(balanced/momentum/dividend)을 산출 → `build_recommend_report(style_recs=..., default_style=...)`로 전달.
- 캐시 위치 `data_cache/`(가격 SQLite + EDGAR JSON + sp500.csv), 기본 7일 TTL, `--refresh`로 강제 갱신.

### CSS/마크업만 바꿀 때 (빠른 경로, 재분석 회피)
데이터가 그대로면 6분 재생성 대신: 생성기를 고친 뒤, 라이브 HTML의 `<style>`를 새 `_STYLE`로 치환 + 필요한 마크업만 문자열 치환 → `export_mobile_app.py`. (이번 세션에서 쓴 방식.) 단 **생성기와 라이브 HTML이 어긋나지 않게** 주의. 안전하게 가려면 그냥 `recommend` 재실행.

---

## 4. 투자성향 매핑

`recommend_report.py` 상단:
```python
_STYLE_LABELS_UX = {"balanced": "Balance", "momentum": "Risk Taker", "dividend": "Conservative"}
_UX_ORDER = ["balanced", "momentum", "dividend"]
```
- 내부 프리셋은 `stock_ai/config.py`의 `FACTOR_WEIGHT_PRESETS`(balanced/value/growth/dividend/momentum).
- runner도 동일한 `ux_order = ["balanced","momentum","dividend"]`로 3개 계산. **두 곳을 함께** 바꿔야 일관됨.

## 5. 영어 업종 설명

`recommend_report.py`의 `_INDUSTRY` dict(티커→영어 업종). 없으면 GICS 섹터로 폴백.
- TODO: momentum/dividend에서 새로 뜨는 종목(MU·WDC·LRCX·TROW·DOW·VRT·FIX·REGN 등)이 폴백 중 → 필요시 채우기.

## 6. PWA / 매니페스트 / 아이콘

- `manifest.webmanifest`(root): `name="S&P 수익 플랜"`(유지), **`short_name="수익&플랜"`**(홈 라벨), `theme_color=#f3f1ea`, `background_color=#faf9f5`.
- HTML `<meta name="apple-mobile-web-app-title" content="수익&플랜">`(iOS 홈 라벨).
- 아이콘: 사용자 제공 `app_icon-192.png`/`app_icon-512.png`(아이보리+코랄 S&P) + `app_icon.svg`(마스커블). `export_mobile_app.py`가 `mobile_app/`로 복사.
- ⚠️ 설치된 기기는 OS가 이름·아이콘을 캐시 → 변경 확인하려면 **삭제 후 재설치**.

## 7. 코드 개선(이전 리뷰 반영, 유지할 것)

- `stock_ai/data/fundamentals.py`: SEC 네트워크 호출 뒤 `time.sleep(0.12)`(콜드런 rate-limit 보호).
- `stock_ai/runner.py`: 포트폴리오 백테스트는 `validate=True`일 때만(기본 off, 리포트 미표시).
- 죽은 코드 정리(backtest `prev_close`, recommend의 빈 `pe` 분기).

## 8. 배포 절차 (Netlify, 같은 주소)

1. `python export_mobile_app.py`로 `mobile_app/` 최신화.
2. 현재 권장 배포는 Cloudflare Pages: `.github/workflows/cloudflare-pages.yml`이 `mobile_app/`를 배포.
3. Cloudflare Pages 프로젝트에는 `functions/api/[[path]].js`와 D1 binding `DB`를 연결해야 동기화 코드/가격 API가 동작.
4. Netlify 수동 배포도 가능하지만, 그 경우 Cloudflare API가 같은 origin에 없으면 동기화 기능은 별도 Worker 라우팅이 필요하다.

## 9. 사용자 요청으로 "제거된" 것들 (되살리지 말 것)

- 히어로 **면책 배너**, **포트폴리오 요약 패널**, 표 **비중 열**, 표 하단 **안내문(note)**, **푸터(생성일·투자자문 아님)**, 히어로 **메타줄(날짜·분석/유니버스)**.
- 결과적으로 **면책 문구가 0개**다. (판단보조 도구 톤상 한 줄 권장했으나 사용자가 보류. Codex가 임의로 추가하지 말 것 — 필요시 사용자 확인.)

## 10. 남은 일 / 참고

- [x] `_INDUSTRY`에 momentum/dividend 신규 종목 일부 업종 채우기(MU/WDC/LRCX/TROW/DOW/VRT/FIX/REGN).
- [ ] (선택) `design_mockup_anthropic.html`(시안 잔재) 삭제 가능.
- [ ] (선택) `make_icon.py`는 삭제됨. 아이콘 재생성 시 SVG→PNG는 `svglib`(이번에 설치)로 가능.
- [ ] (선택) README.md의 디자인 설명/`--style`은 구버전 기준 — 갱신 필요.
- [ ] Cloudflare 실제 배포 전 D1 생성/마이그레이션/binding 연결 필요. 유료 기능은 쓰지 말 것.
- [ ] 진짜 실시간 시세는 유료 API 가능성이 높으므로 사용자 승인 전 도입 금지. 현재는 무료 quote + 5분 캐시.
- 테스트: `pytest -q` → 15 passed.

## 11. 핵심 파일

- `stock_ai/report/recommend_report.py` — 디자인·토글·업종·매매규칙·CSS 전부 (가장 중요).
- `stock_ai/runner.py` — 3성향 산출 오케스트레이션.
- `stock_ai/config.py` — 가중치 프리셋.
- `functions/api/[[path]].js` — Cloudflare Pages Functions API(동기화 코드, 보유 목록, 가격 캐시).
- `migrations/0001_holdings.sql` — Cloudflare D1 테이블.
- `.github/workflows/cloudflare-pages.yml` — 무료 예약 빌드/배포.
- `export_mobile_app.py` — 배포 패키지 빌더.
- `manifest.webmanifest`, `sw.js`, `app_icon*` — PWA.
- `S&P_수익&플랜.html` — 산출물(직접 편집은 빠른 CSS 경로일 때만).
