# Claude Code Instructions

## Cost Guardrail — Highest Priority

This project must be operated with a **$0 monthly platform-cost target** unless the user explicitly approves otherwise.

Before proposing or implementing any change that could create paid usage, require billing setup, exceed a free tier, add a paid API, increase scheduled job frequency, store more cloud data, enable always-on compute, or make external calls at materially higher volume, **warn the user first and get explicit approval**.

This rule is the top operational priority for future Claude Code sessions working on this app. Do not treat cost as an afterthought. If a feature has both a free and paid architecture, present the free path first and clearly label any paid risk.

Current preferred free architecture:
- GitHub Actions for scheduled Python analysis.
- Cloudflare Pages/Workers for app hosting and lightweight APIs.
- Cloudflare D1/KV for sync-code based holdings storage.
- Free or best-effort quote data with conservative caching.

Avoid by default:
- Always-on paid servers.
- Paid market-data APIs.
- Paid Render/Railway/Vercel/Cloud Run configurations.
- Aggressive cron schedules that could exceed GitHub Actions free minutes.
- Features that require automatic cross-device account sync through a paid backend.

If cost risk is uncertain, stop and ask before proceeding.

---

## Project Snapshot For Claude Review

Review date baseline: 2026-06-09.

Local project path:
- `C:\Users\jin\Desktop\주식관련AI`

Public GitHub repository:
- `https://github.com/jinnn99/sp-profit-plan`

Current production-style Cloudflare deployment:
- `https://sweetproduct.pages.dev`

Legacy/static Netlify deployment:
- `https://sweetproduct.netlify.app`
- Treat this as a legacy/static preview unless the user explicitly says they still want Netlify as the main deploy target. The sync-code and quote API are now designed for Cloudflare Pages Functions on the same origin.

Main generated report:
- `S&P_수익&플랜.html`
- This is a generated artifact. Do not rename it. The generator overwrites it.

Mobile/PWA deploy folder:
- `mobile_app/`
- `export_mobile_app.py` regenerates this folder from the report, manifest, service worker, icons, and headers.

Single source of truth for the main PWA report UI:
- `stock_ai/report/recommend_report.py`
- Design, markup, CSS, investment-style toggle data, holdings UI, and client-side JS are all generated from here.

## What The App Does

This is a Korean-language S&P 500 analysis PWA. It scores stocks across five axes:
- value
- quality
- growth
- trend
- sentiment

It produces a judgment-support report with:
- top recommended tickers
- score and confidence
- key reasons and main risks
- common entry/exit rules
- per-stock detail cards
- a holdings panel where the user enters owned ticker, quantity, and average cost
- profit/loss and status display based on cached quote API prices

Important tone rule:
- Avoid language that sounds like personalized investment advice.
- Keep wording as a judgment-support tool.
- The user intentionally removed broad disclaimer/footer/note panels. Do not add them back unless the user explicitly asks.

## Current Architecture

Free target architecture:
- GitHub Actions builds the analysis on a schedule and on relevant pushes.
- Cloudflare Pages hosts `mobile_app/` as a static PWA.
- Cloudflare Pages Functions serve API routes under `/api`.
- Cloudflare D1 stores sync-code based holdings and quote cache.
- Quote data uses free/best-effort Yahoo chart fallback with conservative 5-minute cache.

Cloudflare resources currently connected:
- Pages project: `sweetproduct`
- Pages URL: `https://sweetproduct.pages.dev`
- D1 database name: `sp-profit-plan-holdings`
- D1 database id is recorded locally in `cloudflare-connection.json`; this file is intentionally gitignored.

GitHub repository secrets currently expected:
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_D1_DATABASE_ID`

GitHub repository variable:
- `CF_PAGES_PROJECT_NAME=sweetproduct`

## Current API Surface

Cloudflare Pages Function file:
- `functions/api/[[path]].js`

Routes:
- `GET /api/health`
- `POST /api/sync-code`
- `GET /api/holdings/{code}`
- `PUT /api/holdings/{code}`
- `GET /api/quotes?symbols=AAPL,MSFT`

Storage:
- `migrations/0001_holdings.sql`
- D1 tables: `holdings`, `quote_cache`

Important quote behavior:
- Old Yahoo quote endpoint can return Unauthorized.
- The worker has a Yahoo chart fallback and marks returned quotes with `source: "yahoo-chart"`.
- Quote TTL is 300 seconds.
- Do not switch to paid market data without warning the user first.

## Build And Deploy

Local full build:

```powershell
cd "C:\Users\jin\Desktop\주식관련AI"
python -m stock_ai recommend --top 10 --limit 0 --no-sentiment
python export_mobile_app.py
```

Tests:

```powershell
pytest -q
```

GitHub Actions workflow:
- `.github/workflows/cloudflare-pages.yml`
- Triggered by `workflow_dispatch`, relevant pushes, and schedule.
- Schedule is KST 09:00, 13:00, 17:00, 21:00.
- The workflow builds the report, exports `mobile_app/`, writes a temporary `wrangler.toml` with D1 binding `DB`, and deploys to Cloudflare Pages.
- `compatibility_date` is pinned to `2025-01-01` because a future date caused Cloudflare deployment failure on UTC runners.

Last known verified state:
- GitHub Actions deploy succeeded after commit `aabbc96 Add quote API chart fallback`.
- `https://sweetproduct.pages.dev/` returned HTTP 200.
- `https://sweetproduct.pages.dev/api/health` returned `{ "ok": true }`.
- `https://sweetproduct.pages.dev/api/quotes?symbols=AAPL,MSFT` returned prices from `yahoo-chart`.
- `POST /api/sync-code` created a sync code and stored holdings in D1.

## Key Files To Review

Main report/PWA:
- `stock_ai/report/recommend_report.py`
- `stock_ai/runner.py`
- `stock_ai/config.py`
- `export_mobile_app.py`
- `manifest.webmanifest`
- `sw.js`

Cloudflare/GitHub:
- `functions/api/[[path]].js`
- `migrations/0001_holdings.sql`
- `.github/workflows/cloudflare-pages.yml`
- `cloudflare/wrangler.example.toml`
- `scripts/connect_cloudflare.ps1`
- `scripts/interactive_cloudflare_connect.ps1`
- `scripts/finish_github_secrets.ps1`

Legacy/supplemental:
- `app.py` Streamlit dashboard
- `stock_ai/report/html_report.py` single-stock backtest report, separate from the main PWA generator
- `reports/` generated reports are ignored
- `data_cache/` generated market/SEC cache is ignored

## Review Priorities For Claude

When reviewing the whole program, prioritize:

1. Cost risk
   - Any paid API, billing requirement, always-on compute, aggressive schedules, high-volume external calls, or free-tier risk must be flagged first.

2. Cloudflare API correctness
   - D1 binding name must remain `DB`.
   - `/api/quotes` should keep cache behavior and robust fallback.
   - `/api/holdings/{code}` should validate sync code and holdings data.
   - Service worker must not cache `/api/` responses.

3. Generated-report consistency
   - Do not manually patch only `S&P_수익&플랜.html` unless it is a temporary fast path.
   - Persistent UI/design changes belong in `stock_ai/report/recommend_report.py`.

4. Mobile/PWA behavior
   - `export_mobile_app.py` must copy the report to `mobile_app/index.html`.
   - `_headers` should keep `/api/*` no-store.
   - `sw.js` should bypass `/api/`.

5. UI rules preserved by user request
   - Do not restore the removed disclaimer/notice/footer/meta/portfolio-weight panels.
   - Keep the holdings panel in the old glossary position.

6. Tests and deployment
   - Run `pytest -q` for Python changes.
   - For Cloudflare changes, verify with GitHub Actions or with deployed API smoke tests.

## Known Caveats

- `node.exe` on this Windows machine may be inaccessible from Codex, so Worker JavaScript syntax is usually validated through Wrangler during GitHub Actions deployment.
- Free quote sources can become unreliable. Improve fallbacks only within the free-cost rule unless the user explicitly approves paid market data.
- Cross-device sync is code-based, not account-based. Do not introduce user accounts or paid auth infrastructure without explicit approval.
- Sync codes are bearer secrets by design: `/api/holdings/{code}` has no auth and CORS is `*`, so anyone holding a code can read/write that record. This is an accepted trade-off for a personal, login-free tool. Abuse (mass `sync-code` creation) can only exhaust the D1 free write quota, which fails closed without billing — it cannot incur charges. Do not add accounts/paid auth to "fix" this without explicit approval.
- D1 migrations are NOT auto-applied. `wrangler pages deploy` only uploads the static app and bindings; it does not run `migrations/`. The current `holdings`/`quote_cache` tables were applied once during setup. If you add a new migration, apply it manually (e.g. `wrangler d1 migrations apply sp-profit-plan-holdings`) — the scheduled deploy will not do it.
- Quote fetching uses the Yahoo chart endpoint as the primary path (the old v7 quote endpoint returns Unauthorized and was removed). The `/api/quotes` symbol cap is 20 and chart fetches run in chunks of 8 to stay well under Cloudflare's free-plan 50-external-subrequest-per-invocation limit. Do not raise the cap or un-chunk without rechecking that limit.
- Interactive re-ranking: the report has a weight-slider that re-ranks ALL analyzed stocks client-side, plus a 5-axis radar per card. The browser JS (`_RANK_JS` in `recommend_report.py`) MIRRORS pure Python functions in `analysis/recommend.py` — `composite()↔compute_composite()`, `selectTop()↔select_from_universe()`, `confidence()↔confidence_label()`, `companyKey()↔_company_key()`. Sub-scores are weight-independent percentiles, so client ranking is mathematically identical to the server's. If you change scoring/selection on one side, change the other AND `tests/test_rank_parity.py`. This is pure client compute (embedded `window.SCORE_UNIVERSE`), no new network/API — $0. The weight panel is collapsible and gated: results render only when the five sliders sum to exactly 100 (`_RANK_JS` render()), shown by the `합계 NN/100` indicator. All three presets sum to 100.
- Mobile layout: on narrow screens (`@media max-width:720px`) the three sections become a horizontal swipe pager (`scroll-snap`) with a top tab bar `[추천 분석][종목 상세][내 보유]` (`_PAGER_JS` + `IntersectionObserver`); the controls/weights sit in a shared collapsible header above the tabs. Desktop (≥721px) keeps the original vertical stack (tab bar hidden, pager is normal block flow). All one generator (`recommend_report.py`), CSS-only responsive — $0.
- The GitHub Actions workflow caches `data_cache/` weekly via `actions/cache` to avoid re-scraping all of SEC/Yahoo on every scheduled run. Keep within the default 10GB Actions cache limit; raising it is a cost risk requiring approval.
