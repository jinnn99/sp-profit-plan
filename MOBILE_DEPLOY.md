# 모바일 앱처럼 사용하기

이 프로젝트의 모바일 버전은 정적 PWA 방식이다. 앱스토어에 올리는 네이티브 앱은 아니지만,
HTTPS 주소로 열면 휴대폰 홈 화면에 추가해서 앱처럼 사용할 수 있다.

현재 영구 배포 주소:

https://sweetproduct.netlify.app

무료 운영의 권장 목표 구조는 GitHub Actions + Cloudflare Pages/Workers + D1 동기화 코드다.
비용이 생길 수 있는 유료 API/서버/플랜은 사용자 승인 전 사용하지 않는다.

## 1. 배포 패키지 만들기

```powershell
cd "C:\Users\jin\Desktop\주식관련AI"
python export_mobile_app.py
```

생성 결과:

- `mobile_app/`: HTTPS 정적 호스팅에 올릴 폴더
- `S&P_수익&플랜_mobile_app.zip`: 업로드용 압축 파일

## 2. 권장 배포 방법: Cloudflare Pages

동기화 코드와 준실시간 가격 API까지 쓰려면 Cloudflare Pages Functions와 D1 binding이 필요하다.

1. Cloudflare Pages 프로젝트를 만든다.
2. 무료 D1 database를 만들고 `migrations/0001_holdings.sql`을 적용한다.
3. Pages 프로젝트에 D1 binding 이름을 `DB`로 연결한다.
4. GitHub secrets에 `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`를 설정한다.
5. 필요하면 GitHub repository variable `CF_PAGES_PROJECT_NAME`에 Pages 프로젝트명을 넣는다.
6. `.github/workflows/cloudflare-pages.yml`을 수동 실행하거나 예약 실행을 기다린다.
7. 배포 주소를 휴대폰에서 열고 Chrome 또는 Safari 메뉴에서 `홈 화면에 추가`를 누른다.

## 3. 정적 미리보기: Netlify Drop / GitHub Pages

Netlify Drop이나 GitHub Pages도 정적 PWA 확인용으로는 사용할 수 있다. 핵심은 `mobile_app`
폴더 안의 파일들이 웹사이트 루트에 올라가야 한다는 점이다.

단, 정적 폴더만 올리면 `/api/sync-code`, `/api/holdings`, `/api/quotes`가 함께 배포되지 않는다.
이 경우 보유 종목 입력은 로컬 백업 중심으로 동작하고, 모바일/PC 동기화는 Cloudflare API 라우팅을
별도로 연결해야 한다.

Netlify Drop 기준:

1. https://app.netlify.com/drop 에 접속한다.
2. `mobile_app` 폴더를 끌어다 놓는다.
3. 배포가 끝나면 생성된 HTTPS 주소를 휴대폰에서 연다.
4. Chrome 또는 Safari 메뉴에서 `홈 화면에 추가`를 누른다.

## 4. 보고서를 갱신한 뒤 다시 배포하기

```powershell
python -m stock_ai recommend --top 10 --limit 0 --no-sentiment
python export_mobile_app.py
```

첫 번째 명령은 `S&P_수익&플랜.html`을 갱신하고, 두 번째 명령은 모바일 배포 폴더와 ZIP을 다시 만든다.
Cloudflare Pages 운영 시에는 GitHub Actions가 이 과정을 예약 실행한다. Netlify 수동 운영 시에는
`Production deploys` 영역에 `mobile_app` 폴더를 다시 끌어다 놓으면 같은 주소가 최신 리포트로 갱신된다.

## 5. 로컬에서 휴대폰으로 미리보기

```powershell
python mobile_server.py
```

출력되는 `PHONE:` 주소를 같은 Wi-Fi에 연결된 휴대폰에서 열면 된다. 다만 로컬 IP 접속은
설치형 PWA 기능이 제한될 수 있으므로, 홈 화면 추가까지 제대로 확인하려면 HTTPS 배포 주소를 사용한다.
