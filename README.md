# 미국 주식 종합분석 추천 엔진 (초보자용·장기투자)

S&P 500을 **5개 축(가치·품질·성장·추세·심리)**으로 종합 점수화해, 어떤 종목을 어떤
규칙으로 사고팔지 **근거와 함께** 정리하는 판단 보조 도구. 실거래 자동매매는 하지 않는다.
모든 데이터·분석은 **무료(비용 0원)** — 재무는 SEC EDGAR 공식 데이터, 뉴스 감성은
가벼운 키워드 방식(기본) 또는 선택형 무료 로컬 AI(FinBERT)를 쓴다.

## 비용 원칙

이 프로젝트의 운영 목표는 **월 플랫폼 비용 $0**이다. 유료 API, 결제 계정, free tier 초과 가능성,
always-on 서버, 유료 배포 플랫폼, 저장소/크론/트래픽 증가 등 비용 발생 가능성이 있는 변경은
먼저 사용자에게 경고하고 명시 승인을 받아야 한다. 자세한 작업자 규칙은 `AGENTS.md`와
`CLAUDE.md`에 기록되어 있다.

## 설치

```powershell
cd "C:\Users\jin\Desktop\주식관련AI"
pip install -r requirements.txt
# (선택) FinBERT 고품질 감성 분석을 쓸 거면:
pip install -r requirements-finbert.txt
# (선택) .env.example 을 .env 로 복사해 SEC_USER_AGENT / FINNHUB_API_KEY 등을 설정
```

## 사용법 — 종합분석 추천 (메인 기능)

```powershell
# S&P500 종합분석 → 추천 종목·진입/청산 규칙 HTML 리포트
python -m stock_ai recommend --top 10 --limit 40
#   --limit 40  : S&P500 표 앞부분이 아니라 섹터 균형 샘플 40종목 분석
#   --limit 0   : S&P500 전체(약 500종목) 분석 (첫 실행은 수 분~십수 분)
#   --no-sentiment : 감성분석 끄기(더 빠름)
#   --finbert   : FinBERT 감성분석 사용(RAM 8GB+ 권장)
#   --refresh   : S&P500/SEC 재무 캐시를 무시하고 새로 받기

# SEC EDGAR 공식 재무 지표 한 종목 조회
python -m stock_ai fundamentals --ticker AAPL
# 캐시 무시 후 갱신
python -m stock_ai fundamentals --ticker AAPL --refresh
```

리포트는 프로젝트 루트의 `S&P_수익&플랜.html` 로 생성된다. 앞으로 S&P500 추천 업데이트는
항상 이 파일을 덮어쓴다. 추천 종목 분석(순위·핵심 근거·리스크) + 종목별 카드
(5축 점수/신뢰도/강점·리스크) + 내 보유 종목 평가 패널이 담긴다.

## 사용법 — 단일 종목 백테스트

```powershell
# 1) 데이터 받기 (SQLite 캐싱)
python -m stock_ai fetch --ticker AAPL

# 2) 백테스트 + HTML 리포트 생성
python -m stock_ai backtest --ticker AAPL --strategy sma_cross --start 2015-01-01

# 단기/장기 이동평균 바꾸기
python -m stock_ai backtest -t MSFT -s sma_cross --fast 10 --slow 30

# RSI 평균회귀 전략
python -m stock_ai backtest -t AAPL -s rsi_reversion

# 전략 목록
python -m stock_ai strategies
```

리포트는 `reports/{티커}_{전략}.html` 로 생성된다. 브라우저로 열면
자산곡선·낙폭·매매 시점과 핵심 지표(CAGR·Sharpe·MDD·승률)를 볼 수 있다.

## 사용법 — 대시보드

```powershell
streamlit run app.py
```

브라우저에서 단일 종목 판단과 S&P500 추천을 실행할 수 있다. 빠른 분석 범위는
표 앞부분이 아니라 섹터를 고르게 섞은 샘플을 쓴다.

## 사용법 — 휴대폰에서 보기

영구 배포 주소:

https://sweetproduct.netlify.app

```powershell
python mobile_server.py
```

같은 와이파이에 연결된 휴대폰에서 터미널에 표시되는 `PHONE:` 주소로 접속한다.
`S&P_수익&플랜.html` 은 모바일 반응형/PWA-ready 리포트다. 홈 화면 추가와 오프라인 캐시는
HTTPS 호스팅 또는 localhost 같은 보안 출처에서 완전히 동작한다.

## HTTPS 배포용 앱 폴더 만들기

```powershell
python export_mobile_app.py
```

`mobile_app/` 폴더가 생성된다. 이 폴더의 내용물을 Cloudflare Pages, Netlify Drop,
GitHub Pages 같은 HTTPS 정적 호스팅에 올리면 휴대폰에서 홈 화면 추가가 가능한 앱처럼 쓸 수 있다.
동시에 `S&P_수익&플랜_mobile_app.zip` 도 생성되므로, ZIP 업로드를 지원하는 서비스에서는 이 파일을
그대로 사용하면 된다. 자세한 순서는 `MOBILE_DEPLOY.md` 에 기록해 두었다.

## 무료 운영 구조 — GitHub Actions + Cloudflare

권장 무료 구조:

- GitHub Actions: 하루 4회(KST 09/13/17/21) `recommend`를 실행해 리포트와 PWA를 재생성.
- Cloudflare Pages: `mobile_app/` 정적 PWA 배포.
- Cloudflare Pages Functions/Workers: `/api/holdings`, `/api/sync-code`, `/api/quotes` 제공.
- Cloudflare D1: 동기화 코드별 보유 종목 저장.
- 가격 조회: 무료/best-effort quote endpoint를 5분 캐시로 사용. 유료 시세 API는 기본 사용하지 않는다.

필요 설정:

1. Cloudflare에서 무료 D1 database를 만들고 `migrations/0001_holdings.sql`을 적용한다.
2. Pages 프로젝트에 D1 binding 이름을 `DB`로 연결한다.
3. GitHub repository secrets에 `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`를 넣는다.
4. 필요하면 repository variable `CF_PAGES_PROJECT_NAME`에 Pages 프로젝트명을 넣는다. 없으면 `sweetproduct`를 쓴다.
5. `.github/workflows/cloudflare-pages.yml`이 예약 실행과 수동 실행을 담당한다.

동기화 코드는 로그인 없이 모바일과 PC의 보유 목록을 연결하기 위한 키다. 한 기기에서 `코드 만들기`를
누르고 다른 기기에서 같은 코드를 입력하면 같은 보유 목록을 불러온다.

## 구조

```
stock_ai/
├─ config.py        설정·API키 (.env)
├─ data/prices.py   yfinance OHLCV + SQLite 캐싱
├─ features/        기술적 지표 (SMA/EMA/RSI/MACD, 순수 pandas)
├─ strategy/        전략 인터페이스 + 예시(sma_cross, rsi_reversion)
├─ engine/          백테스트 엔진 (미래참조 방지·수수료·슬리피지)
├─ report/          성과지표 + plotly HTML 리포트
├─ runner.py        데이터→전략→백테스트→리포트 오케스트레이션
└─ cli.py           명령줄 인터페이스 (typer)
```

## 설계 원칙 (검증 신뢰성)

- **미래참조 방지**: 신호는 종가까지 정보로 만들고 **다음 봉 시가**에 체결.
- **거래비용 반영**: 수수료(기본 0.1%) + 슬리피지(0.05%)를 매매 시 차감.
- **벤치마크 비교**: 모든 결과를 Buy & Hold 와 나란히 보여줌.
- **빠른 추천의 표 순서 편향 완화**: `--limit` 사용 시 S&P500 표의 앞 N개가 아니라 섹터 균형 샘플을 분석.
- **캐시 최신성**: S&P500/CIK/SEC 재무 캐시는 기본 7일 후 갱신 시도, 실패하면 기존 캐시 사용.

## 테스트

```powershell
pytest -q
```

## 로드맵

- Phase 1 (현재): 단일 종목 기술적 전략 백테스트 + HTML 리포트 ✅
- Phase 2: 기본적 지표(PER·PBR 등) + 멀티팩터 추천 ✅
- Phase 3: 무료 Cloudflare 동기화 코드 + 보유 종목 평가
- Phase 4: 뉴스·공시 감성 고도화(FinBERT/외부 API 선택)
- Phase 5: 워크포워드/아웃오브샘플 검증, 파라미터 최적화
