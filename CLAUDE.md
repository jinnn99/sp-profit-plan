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

