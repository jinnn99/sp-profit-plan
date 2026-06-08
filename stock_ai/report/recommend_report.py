"""초보자용 추천 HTML 리포트 (Anthropic풍 — 따뜻한 종이 + 코랄 악센트 + 세리프).

구성:
1. 화이트(아이보리) 히어로 — 두 줄 세리프 헤드라인 + 모노/산세 라벨
2. 추천 종목 분석(6열 표, 가로 스크롤 없음 · 영어 업종 표기)
3. 공통 매매 규칙(진입·청산을 한 블록으로 — 종목 공통)
4. 종목별 카드(5축 점수 + 강점·리스크), 코랄 농담으로 점수 신호 표현
5. 내 보유 종목(동기화 코드 + 준실시간 가격 기준 평가손익)

디자인 원칙(요약):
- 따뜻한 아이보리 종이 + 코랄/클레이 단일 악센트, 세리프 헤드라인 + 산세 본문.
- 한국어 word-break:keep-all 로 단어 중간 줄바꿈 방지.
- 점수 막대는 코랄 농담(강=진한 코랄, 중=연한 클레이, 약=뮤트)으로 한 색 계열 신호.
"""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from stock_ai.analysis.recommend import Recommendation
from stock_ai.config import FACTOR_LABELS_KO, PROJECT_ROOT

_AXES = ["value", "quality", "growth", "trend", "sentiment"]
DEFAULT_RECOMMEND_REPORT = PROJECT_ROOT / "S&P_수익&플랜.html"

# 투자성향 토글(클라이언트 전환): 내부 프리셋 → UX 라벨, 표시 순서
_STYLE_LABELS_UX = {"balanced": "Balance", "momentum": "Risk Taker", "dividend": "Conservative"}
_UX_ORDER = ["balanced", "momentum", "dividend"]

# 종목 → 영어 업종 한 줄 설명(없으면 GICS 섹터로 폴백). 자주 추천되는 종목 위주.
_INDUSTRY = {
    "APA": "Oil & gas exploration", "FOX": "Media & broadcasting", "FOXA": "Media & broadcasting",
    "EIX": "Electric utility", "INCY": "Biopharmaceuticals", "CF": "Nitrogen fertilizer",
    "FSLR": "Solar manufacturing", "NEM": "Gold mining", "KEY": "Regional banking",
    "GOOGL": "Search & advertising", "GOOG": "Search & advertising", "EXE": "Natural gas",
    "AAPL": "Consumer electronics", "MSFT": "Software & cloud", "AMZN": "E-commerce & cloud",
    "NVDA": "Semiconductors", "META": "Social media & ads", "TSLA": "Electric vehicles",
    "JPM": "Banking", "V": "Payments", "MA": "Payments", "JNJ": "Pharmaceuticals & devices",
    "XOM": "Oil & gas", "CVX": "Oil & gas", "WMT": "Retail", "PG": "Consumer goods",
    "KO": "Beverages", "PEP": "Food & beverages", "COST": "Wholesale retail", "HD": "Home improvement retail",
    "MRK": "Pharmaceuticals", "ABBV": "Pharmaceuticals", "AVGO": "Semiconductors", "LLY": "Pharmaceuticals",
    "UNH": "Health insurance", "BAC": "Banking", "WFC": "Banking", "DIS": "Media & entertainment",
    "NFLX": "Streaming media", "CRM": "Enterprise software", "ADBE": "Software", "INTC": "Semiconductors",
    "AMD": "Semiconductors", "QCOM": "Semiconductors", "TXN": "Semiconductors", "ORCL": "Enterprise software",
    "PFE": "Pharmaceuticals", "TMO": "Life sciences", "NKE": "Apparel & footwear", "MCD": "Restaurants",
    "T": "Telecom", "VZ": "Telecom", "CMCSA": "Media & telecom", "UPS": "Logistics", "CAT": "Construction machinery",
    "BA": "Aerospace", "GE": "Industrial conglomerate", "HON": "Industrial tech", "UNP": "Railroads",
    "MU": "Memory semiconductors", "WDC": "Data storage", "LRCX": "Semiconductor equipment",
    "TROW": "Asset management", "DOW": "Commodity chemicals", "VRT": "Data center infrastructure",
    "FIX": "Building systems services", "REGN": "Biotechnology",
}


def _industry(ticker: str, sector: str) -> str:
    return _INDUSTRY.get((ticker or "").upper(), sector or "")


# ── Anthropic풍 디자인 토큰 + 컴포넌트 스타일 (변수로 주입하므로 중괄호 그대로 사용) ──
_STYLE = """
  :root{
    --paper:#f3f1ea; --card:#fcfbf8; --ink:#1c1b17; --body:#5e5c54; --mute:#8c887e;
    --line:#e6e1d6; --line-soft:#efebe1; --line-strong:#d6cfbf;
    --clay:#c0603d; --clay-soft:#d79a78; --clay-weak:#c2bbab; --charcoal:#26231f; --cream:#f3efe6;
    --serif:'Newsreader',Georgia,'Times New Roman',serif;
    --sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI','Malgun Gothic',sans-serif;
    --gut:32px; --maxw:1080px;
    --sh:0 1px 2px rgba(40,33,24,.04), 0 14px 34px -18px rgba(60,45,30,.20);
  }
  *{ box-sizing:border-box; }
  html{ -webkit-text-size-adjust:100%; }
  body{ margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans);
    font-size:17px; line-height:1.6; font-weight:400; overflow-x:hidden;
    word-break:keep-all; overflow-wrap:break-word; line-break:strict;
    -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; }
  .wrap{ width:100%; max-width:var(--maxw); margin:0 auto; padding:0 var(--gut) 72px; }

  .eyebrow{ font-family:var(--sans); font-size:12px; font-weight:600; letter-spacing:.14em;
    text-transform:uppercase; color:var(--clay); margin:0 0 18px; display:flex; align-items:center; gap:9px; }
  .eyebrow::before{ content:""; width:18px; height:2px; border-radius:2px; background:var(--clay); flex:none; }

  /* 히어로 */
  .hero{ padding:52px 0 4px; }
  .hero h1{ font-family:var(--sans); font-weight:700; font-size:clamp(2.6rem,6.2vw,4.4rem);
    line-height:1.12; letter-spacing:-.02em; margin:0 0 16px; max-width:18ch; }
  .hero h1 em{ font-style:normal; color:var(--clay); }
  .hero .lead{ font-size:20px; line-height:1.55; color:var(--body); margin:0; max-width:52ch; }

  /* 투자성향 토글 + 갱신 */
  .controls{ display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-top:22px; }
  .ctl-label{ font-size:13px; font-weight:600; color:var(--mute); }
  .style-toggle{ display:inline-flex; gap:4px; background:var(--card); border:1px solid var(--line);
    border-radius:999px; padding:4px; box-shadow:var(--sh); }
  .style-pill{ font-family:var(--sans); font-size:13px; font-weight:600; color:var(--body); background:transparent;
    border:none; border-radius:999px; padding:8px 16px; cursor:pointer; letter-spacing:.01em;
    transition:background .15s, color .15s; }
  .style-pill:hover{ color:var(--ink); }
  .style-pill.active{ background:var(--clay); color:#fff; }
  .refresh-btn{ font-family:var(--sans); font-size:13px; font-weight:600; color:var(--ink); background:var(--card);
    border:1px solid var(--line); border-radius:999px; padding:8px 16px; cursor:pointer; box-shadow:var(--sh); }
  .refresh-btn:hover{ background:#f0ece2; }
  .refresh-btn:disabled{ opacity:.6; cursor:default; }
  .upd{ font-size:12px; color:var(--mute); margin-left:4px; }

  .section{ margin-top:64px; }
  .section > .eyebrow{ margin-bottom:14px; }
  h2.title{ font-family:var(--sans); font-weight:700; font-size:clamp(1.8rem,3.4vw,2.7rem);
    line-height:1.2; letter-spacing:-.02em; margin:0; }
  .sub{ font-size:18px; color:var(--body); margin:12px 0 0; max-width:58ch; }

  /* 표 카드 */
  .surface{ margin-top:20px; background:var(--card); border:1px solid var(--line);
    border-radius:20px; box-shadow:var(--sh); padding:8px 26px; }
  .table-wrap{ display:block; width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch; }
  table{ border-collapse:collapse; width:100%; font-size:15px; }
  .table-wrap > table{ min-width:0; }
  table.analysis{ table-layout:fixed; }
  thead th{ font-family:var(--sans); font-size:11px; font-weight:600; letter-spacing:.09em;
    text-transform:uppercase; color:var(--mute); text-align:left; padding:20px 14px 14px;
    border-bottom:1px solid var(--line-strong); }
  thead th.num{ text-align:right; }
  tbody td{ padding:12px 14px; border-bottom:1px solid var(--line-soft); vertical-align:top; color:var(--body); }
  tbody tr:last-child td{ border-bottom:none; }
  td.num{ text-align:right; font-variant-numeric:tabular-nums; }
  .analysis td .tk{ font-family:var(--serif); font-weight:520; font-size:18px; color:var(--ink); letter-spacing:-.01em; }
  .analysis td .sc{ font-family:var(--serif); font-weight:520; font-size:18px; color:var(--clay); }
  .analysis td span{ color:var(--mute); font-size:12.5px; }
  .analysis td .ind{ display:inline-block; margin-top:3px; color:var(--clay); font-weight:500;
    font-size:11px; letter-spacing:.04em; text-transform:uppercase; }

  /* 공통 매매 규칙 */
  .rules{ margin-top:22px; background:var(--card); border:1px solid var(--line); border-radius:20px;
    box-shadow:var(--sh); padding:22px 28px; }
  .rules-head{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
  .rules-title{ font-family:var(--sans); font-weight:700; font-size:19px; letter-spacing:-.01em; margin:0; color:var(--ink); }
  .rules-note{ font-size:13px; color:var(--mute); }
  .rules-cols{ display:grid; grid-template-columns:1fr 1fr; gap:30px; margin-top:18px; }
  .rules-cols h5{ font-family:var(--sans); font-size:11px; letter-spacing:.1em; text-transform:uppercase;
    font-weight:600; color:var(--clay); margin:0 0 10px; }
  .rules-cols ul{ margin:0; padding-left:18px; font-size:14.5px; line-height:1.6; color:var(--body); }
  .rules-cols ul li{ margin:6px 0; }

  /* 종목 카드 */
  .cards{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; margin-top:22px; }
  .card{ background:var(--card); border:1px solid var(--line); border-radius:20px;
    box-shadow:var(--sh); padding:22px 26px; }
  .card-head{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
  .rank-ticker{ font-family:var(--serif); font-weight:520; font-size:30px; letter-spacing:-.015em; line-height:1; }
  .rank-name{ flex:1; font-size:13px; color:var(--mute); }
  .composite{ font-family:var(--serif); font-weight:520; font-size:30px; color:var(--clay); line-height:1; }
  .card-meta{ font-size:14px; color:var(--body); margin:10px 0 14px; }
  .card-meta b{ color:var(--ink); font-weight:600; }
  table.subs{ width:100%; max-width:440px; font-size:13px; }
  table.subs td{ border:none; padding:5px 12px 5px 0; }
  td.axis{ width:36px; white-space:nowrap; color:var(--mute); }
  .bar{ position:relative; width:100%; max-width:300px; height:18px; background:#ece6da; border-radius:999px; }
  .bar .fill{ position:absolute; left:0; top:0; height:100%; border-radius:999px; }
  .fill.hi{ background:var(--clay); } .fill.mid{ background:var(--clay-soft); } .fill.lo{ background:var(--clay-weak); }
  .barlabel{ position:absolute; right:9px; top:0; font-size:11px; line-height:18px; color:var(--ink);
    font-variant-numeric:tabular-nums; font-weight:600; }
  .na{ color:var(--clay-weak); font-size:12px; }
  .cols{ display:grid; grid-template-columns:1fr 1fr; gap:24px; margin-top:16px; }
  .cols h4{ font-family:var(--sans); font-size:11px; letter-spacing:.1em; text-transform:uppercase;
    font-weight:600; color:var(--clay); margin:0 0 9px; }
  .cols ul{ margin:0; padding-left:18px; font-size:14px; line-height:1.55; color:var(--body); }
  .cols ul li{ margin:5px 0; }

  /* 내 보유 종목 */
  .holdings .sub{ max-width:none; }
  .holding-shell{ margin-top:20px; background:var(--card); border:1px solid var(--line);
    border-radius:20px; box-shadow:var(--sh); padding:24px 28px; }
  .sync-panel{ display:grid; grid-template-columns:minmax(160px,.8fr) minmax(220px,1fr) auto auto;
    gap:10px; align-items:end; margin-bottom:20px; padding-bottom:18px; border-bottom:1px solid var(--line-soft); }
  .sync-code{ min-height:42px; border:1px solid var(--line-soft); border-radius:14px; background:#faf8f2; padding:10px 14px; }
  .sync-code span{ display:block; font-size:10px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--mute); }
  .sync-code b{ display:block; margin-top:2px; font-family:var(--serif); font-size:20px; font-weight:520; color:var(--ink); letter-spacing:.02em; }
  .sync-form{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px; align-items:end; }
  .sync-state,.price-stamp{ font-size:12px; color:var(--mute); }
  .price-stamp{ margin-top:10px; text-align:right; }
  .holding-summary{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:20px; }
  .sum-card{ border:1px solid var(--line-soft); border-radius:14px; padding:14px 16px; background:#faf8f2; }
  .sum-card span{ display:block; font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--mute); }
  .sum-card b{ display:block; margin-top:5px; font-family:var(--serif); font-size:23px; font-weight:520; color:var(--ink);
    line-height:1.1; font-variant-numeric:tabular-nums; }
  .sum-card.gain b,.gain{ color:#527145; } .sum-card.loss b,.loss{ color:#b0523b; } .flat{ color:var(--body); }
  .holding-form{ display:grid; grid-template-columns:minmax(180px,1.4fr) minmax(110px,.7fr) minmax(130px,.8fr) auto;
    gap:10px; align-items:end; margin-bottom:16px; }
  .field label{ display:block; margin:0 0 5px; font-size:11px; font-weight:600; letter-spacing:.08em;
    text-transform:uppercase; color:var(--mute); }
  .field input{ width:100%; min-height:42px; border:1px solid var(--line); border-radius:12px; background:#fffefb;
    color:var(--ink); font-family:var(--sans); font-size:14px; padding:9px 12px; outline:none; }
  .field input:focus{ border-color:var(--clay-soft); box-shadow:0 0 0 3px rgba(192,96,61,.12); }
  .holding-add,.mini-btn{ border:none; background:var(--clay); color:#fff; font-family:var(--sans);
    font-size:13px; font-weight:600; border-radius:999px; min-height:42px; padding:0 18px; cursor:pointer; }
  .holding-add:hover,.mini-btn:hover{ background:#a95035; }
  .mini-btn.secondary{ background:#fffefb; color:var(--ink); border:1px solid var(--line); }
  .mini-btn.secondary:hover{ background:#f0ece2; }
  .holding-table{ width:100%; table-layout:fixed; }
  .holding-table th{ font-family:var(--sans); font-size:11px; font-weight:600; letter-spacing:.08em;
    text-transform:uppercase; color:var(--mute); text-align:left; padding:14px 10px; border-bottom:1px solid var(--line-strong); }
  .holding-table td{ padding:12px 10px; border-bottom:1px solid var(--line-soft); vertical-align:middle; color:var(--body); }
  .holding-table tr:last-child td{ border-bottom:none; }
  .holding-table .tk{ font-family:var(--serif); font-size:20px; font-weight:520; color:var(--ink); }
  .holding-table .name{ display:block; color:var(--mute); font-size:12px; line-height:1.35; }
  .holding-table input{ width:100%; border:1px solid var(--line); border-radius:10px; background:#fffefb;
    padding:8px 9px; font-family:var(--sans); color:var(--ink); }
  .status-pill{ display:inline-flex; align-items:center; justify-content:center; min-width:54px; border-radius:999px;
    padding:5px 10px; font-size:12px; font-weight:600; background:#eee8dd; color:var(--body); }
  .status-pill.gain{ background:#e3eadb; color:#527145; } .status-pill.loss{ background:#f0dfd7; color:#b0523b; }
  .delete-btn{ width:32px; height:32px; border-radius:50%; border:1px solid var(--line); background:#fffefb;
    color:var(--mute); cursor:pointer; font-size:18px; line-height:1; }
  .delete-btn:hover{ color:var(--clay); border-color:var(--clay-soft); }
  .empty-holdings{ border:1px dashed var(--line-strong); border-radius:14px; padding:22px; text-align:center;
    color:var(--mute); font-size:14px; }

  @media (max-width:768px){
    :root{ --gut:18px; }
    .hero{ padding:52px 0 4px; }
    .section{ margin-top:64px; }
    .table-wrap{ overflow-x:visible; }
    table.analysis, table.analysis thead, table.analysis tbody, table.analysis tr, table.analysis td{ display:block; width:100%; }
    table.analysis thead{ display:none; }
    table.analysis tr{ padding:16px 0; border-bottom:1px solid var(--line); }
    table.analysis tbody tr:last-child{ border-bottom:none; }
    table.analysis td{ display:grid; grid-template-columns:96px minmax(0,1fr); gap:12px; border:none; padding:5px 0; }
    table.analysis td::before{ font-family:var(--sans); font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--mute); font-weight:600; }
    table.analysis td:nth-child(1)::before{ content:"#"; }
    table.analysis td:nth-child(2)::before{ content:"종목"; }
    table.analysis td:nth-child(3)::before{ content:"점수"; }
    table.analysis td:nth-child(4)::before{ content:"신뢰도"; }
    table.analysis td:nth-child(5)::before{ content:"핵심 근거"; }
    table.analysis td:nth-child(6)::before{ content:"주요 리스크"; }
    table.analysis td.num{ text-align:left; }
    .rules{ padding:22px; }
    .rules-cols{ grid-template-columns:1fr; gap:18px; }
    .cards{ grid-template-columns:1fr; gap:18px; }
    .cols{ grid-template-columns:1fr; gap:18px; }
    table.subs{ max-width:none; }
    .holding-shell{ padding:22px; }
    .sync-panel{ grid-template-columns:1fr; }
    .sync-form{ grid-template-columns:1fr; }
    .sync-panel .mini-btn{ width:100%; }
    .price-stamp{ text-align:left; }
    .holding-summary{ grid-template-columns:1fr 1fr; }
    .holding-form{ grid-template-columns:1fr; }
    .holding-add{ width:100%; }
    .holding-table,.holding-table thead,.holding-table tbody,.holding-table tr,.holding-table td{ display:block; width:100%; }
    .holding-table thead{ display:none; }
    .holding-table tr{ padding:14px 0; border-bottom:1px solid var(--line); }
    .holding-table tbody tr:last-child{ border-bottom:none; }
    .holding-table td{ display:grid; grid-template-columns:96px minmax(0,1fr); gap:12px; border:none; padding:5px 0; }
    .holding-table td::before{ font-family:var(--sans); font-size:11px; text-transform:uppercase; letter-spacing:.06em;
      color:var(--mute); font-weight:600; }
    .holding-table td:nth-child(1)::before{ content:"종목"; }
    .holding-table td:nth-child(2)::before{ content:"수량"; }
    .holding-table td:nth-child(3)::before{ content:"평균가"; }
    .holding-table td:nth-child(4)::before{ content:"현재가"; }
    .holding-table td:nth-child(5)::before{ content:"평가손익"; }
    .holding-table td:nth-child(6)::before{ content:"상태"; }
    .holding-table td:nth-child(7)::before{ content:""; }
  }
"""


# 투자성향 토글 + 갱신 버튼 클라이언트 스크립트(평문 JS — 중괄호 그대로).
_TOGGLE_JS = """
(function(){
  var data = window.REPORT_DATA || {};
  var tbody = document.getElementById('analysis-body');
  var cards = document.getElementById('cards');
  var label = document.getElementById('style-label');
  var pills = Array.prototype.slice.call(document.querySelectorAll('.style-pill'));
  function apply(st){
    var d = data[st]; if(!d) return;
    if(tbody) tbody.innerHTML = d.rows;
    if(cards) cards.innerHTML = d.cards;
    if(label) label.textContent = d.label;
    pills.forEach(function(p){ p.classList.toggle('active', p.getAttribute('data-style')===st); });
    try{ localStorage.setItem('sp_style', st); }catch(e){}
  }
  pills.forEach(function(p){ p.addEventListener('click', function(){ apply(p.getAttribute('data-style')); }); });
  var saved=null; try{ saved=localStorage.getItem('sp_style'); }catch(e){}
  if(saved && data[saved]) apply(saved);
  var rb = document.getElementById('refresh-btn');
  if(rb){ rb.addEventListener('click', function(){
    rb.disabled=true; rb.textContent='불러오는 중…';
    if('serviceWorker' in navigator && navigator.serviceWorker.getRegistrations){
      navigator.serviceWorker.getRegistrations().then(function(rs){ rs.forEach(function(r){ try{r.update();}catch(e){} }); });
    }
    setTimeout(function(){ location.reload(); }, 350);
  }); }
})();
"""


# 내 보유 종목: 동기화 코드(Cloudflare D1) + 가격 API(Cloudflare Worker) + 로컬 백업.
_HOLDINGS_JS = """
(function(){
  var universe = window.HOLDING_UNIVERSE || {};
  var apiBase = String(window.HOLDING_API_BASE || '/api').replace(/\\/$/, '');
  var key = 'sp_holdings_v2';
  var syncKey = 'sp_holdings_sync_code';
  var form = document.getElementById('holding-form');
  var tickerInput = document.getElementById('holding-ticker');
  var qtyInput = document.getElementById('holding-qty');
  var costInput = document.getElementById('holding-cost');
  var summary = document.getElementById('holding-summary');
  var body = document.getElementById('holding-body');
  var empty = document.getElementById('holding-empty');
  var syncForm = document.getElementById('sync-form');
  var syncInput = document.getElementById('sync-code-input');
  var syncLabel = document.getElementById('sync-code-label');
  var syncState = document.getElementById('sync-state');
  var createSyncBtn = document.getElementById('create-sync-btn');
  var refreshBtn = document.getElementById('refresh-holdings-btn');
  var priceStamp = document.getElementById('price-stamp');
  var holdings = clean(loadLocal());
  var syncCode = loadSyncCode();
  var quotes = {};
  var saveTimer = null;
  var quoteTimer = null;

  function esc(v){
    return String(v == null ? '' : v).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function num(v){
    var n = Number(v);
    return isFinite(n) ? n : NaN;
  }
  function money(v){
    if(!isFinite(v)) return '—';
    return new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:2}).format(v);
  }
  function pct(v){
    if(!isFinite(v)) return '—';
    return (v > 0 ? '+' : '') + v.toFixed(1) + '%';
  }
  function signedMoney(v){
    if(!isFinite(v)) return '—';
    return (v > 0 ? '+' : '') + money(v);
  }
  function tone(v){
    return v > 0.005 ? 'gain' : (v < -0.005 ? 'loss' : 'flat');
  }
  function status(v){
    if(!isFinite(v)) return '대기';
    return v > 0.005 ? '이득' : (v < -0.005 ? '손해' : '보합');
  }
  function validTicker(t){
    return /^[A-Z0-9.\\-]{1,12}$/.test(String(t || '').trim().toUpperCase());
  }
  function loadLocal(){
    try{
      var rows = JSON.parse(localStorage.getItem(key) || '[]');
      return Array.isArray(rows) ? rows : [];
    }catch(e){ return []; }
  }
  function loadSyncCode(){
    try{ return String(localStorage.getItem(syncKey) || '').trim().toUpperCase(); }catch(e){ return ''; }
  }
  function clean(rows){
    return rows.map(function(r){
      return {ticker:String(r.ticker || '').trim().toUpperCase(), qty:num(r.qty), avgCost:num(r.avgCost)};
    }).filter(function(r){
      return validTicker(r.ticker) && r.qty > 0 && r.avgCost > 0;
    });
  }
  function saveLocal(rows){
    holdings = clean(rows);
    try{ localStorage.setItem(key, JSON.stringify(holdings)); }catch(e){}
  }
  function saveSyncCode(code){
    syncCode = String(code || '').trim().toUpperCase();
    try{
      if(syncCode) localStorage.setItem(syncKey, syncCode);
      else localStorage.removeItem(syncKey);
    }catch(e){}
    renderSync();
  }
  function setState(text){
    if(syncState) syncState.textContent = text || '';
  }
  function renderSync(){
    if(syncLabel) syncLabel.textContent = syncCode || '이 기기만';
    if(syncInput && syncCode) syncInput.value = syncCode;
  }
  function api(path, options){
    return fetch(apiBase + path, Object.assign({
      headers: {'content-type':'application/json'},
      cache: 'no-store'
    }, options || {})).then(function(resp){
      if(!resp.ok) throw new Error('api ' + resp.status);
      return resp.json();
    });
  }
  function calc(r){
    var info = Object.assign({}, universe[r.ticker] || {}, quotes[r.ticker] || {});
    var price = num(info.price);
    var invested = r.qty * r.avgCost;
    var hasPrice = isFinite(price) && price > 0;
    var current = hasPrice ? r.qty * price : NaN;
    var pnl = hasPrice ? current - invested : NaN;
    var rate = hasPrice && invested > 0 ? pnl / invested * 100 : NaN;
    return {info:info, price:price, invested:invested, current:current, pnl:pnl, rate:rate};
  }
  function render(){
    holdings = clean(holdings);
    var totals = holdings.reduce(function(acc, r){
      var c = calc(r);
      acc.invested += c.invested;
      if(isFinite(c.current)){
        acc.current += c.current;
        acc.pnl += c.pnl;
        acc.pricedInvested += c.invested;
        acc.priced += 1;
      }
      return acc;
    }, {invested:0, current:0, pnl:0, pricedInvested:0, priced:0});
    var totalCurrent = totals.priced ? totals.current : NaN;
    var totalPnl = totals.priced ? totals.pnl : NaN;
    var totalRate = totals.pricedInvested > 0 ? totalPnl / totals.pricedInvested * 100 : NaN;
    var totalTone = tone(totalPnl);
    if(summary){
      summary.innerHTML =
        '<div class="sum-card"><span>매입금액</span><b>' + money(totals.invested) + '</b></div>' +
        '<div class="sum-card"><span>평가액</span><b>' + money(totalCurrent) + '</b></div>' +
        '<div class="sum-card ' + totalTone + '"><span>평가손익</span><b>' + signedMoney(totalPnl) + '</b></div>' +
        '<div class="sum-card ' + totalTone + '"><span>수익률</span><b>' + pct(totalRate) + '</b></div>';
    }
    if(empty) empty.style.display = holdings.length ? 'none' : 'block';
    if(!body) return;
    body.innerHTML = holdings.map(function(r){
      var c = calc(r);
      var info = c.info || {};
      var rowTone = tone(c.pnl);
      var name = [info.name, info.industry].filter(Boolean).join(' · ');
      return '<tr data-ticker="' + esc(r.ticker) + '">' +
        '<td><span class="tk">' + esc(r.ticker) + '</span><span class="name">' + esc(name) + '</span></td>' +
        '<td><input type="number" min="0" step="any" data-field="qty" value="' + esc(r.qty) + '" aria-label="수량"></td>' +
        '<td><input type="number" min="0" step="any" data-field="avgCost" value="' + esc(r.avgCost) + '" aria-label="평균 매입가"></td>' +
        '<td>' + money(c.price) + '</td>' +
        '<td><b class="' + rowTone + '">' + signedMoney(c.pnl) + '</b><br><span class="' + rowTone + '">' + pct(c.rate) + '</span></td>' +
        '<td><span class="status-pill ' + rowTone + '">' + status(c.pnl) + '</span></td>' +
        '<td><button class="delete-btn" type="button" data-delete="' + esc(r.ticker) + '" aria-label="삭제">×</button></td>' +
      '</tr>';
    }).join('');
    body.querySelectorAll('input[data-field]').forEach(function(input){
      input.addEventListener('change', function(){
        var tr = input.closest('tr');
        var ticker = tr ? tr.getAttribute('data-ticker') : '';
        var field = input.getAttribute('data-field');
        var next = clean(holdings).map(function(r){
          if(r.ticker === ticker) r[field] = num(input.value);
          return r;
        });
        saveLocal(next);
        render();
        scheduleRemoteSave();
        fetchQuotes();
      });
    });
    body.querySelectorAll('[data-delete]').forEach(function(btn){
      btn.addEventListener('click', function(){
        var ticker = btn.getAttribute('data-delete');
        saveLocal(clean(holdings).filter(function(r){ return r.ticker !== ticker; }));
        render();
        scheduleRemoteSave();
      });
    });
  }
  function scheduleRemoteSave(){
    if(!syncCode) return;
    if(saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(pushRemote, 450);
  }
  function pushRemote(){
    if(!syncCode) return Promise.resolve();
    setState('동기화 중');
    return api('/holdings/' + encodeURIComponent(syncCode), {
      method:'PUT',
      body: JSON.stringify({holdings: holdings})
    }).then(function(){
      setState('동기화됨');
    }).catch(function(){
      setState('동기화 대기');
    });
  }
  function pullRemote(code){
    return api('/holdings/' + encodeURIComponent(code), {method:'GET'}).then(function(data){
      saveSyncCode(code);
      saveLocal(data.holdings || []);
      setState('동기화됨');
      render();
      fetchQuotes();
    });
  }
  function createSync(){
    setState('코드 생성 중');
    return api('/sync-code', {
      method:'POST',
      body: JSON.stringify({holdings: holdings})
    }).then(function(data){
      saveSyncCode(data.code || '');
      saveLocal(data.holdings || holdings);
      setState('동기화됨');
      render();
      fetchQuotes();
    }).catch(function(){
      setState('동기화 서버 연결 실패');
    });
  }
  function fetchQuotes(){
    var symbols = clean(holdings).map(function(r){ return r.ticker; });
    if(!symbols.length) return Promise.resolve();
    return api('/quotes?symbols=' + encodeURIComponent(symbols.join(',')), {method:'GET'}).then(function(data){
      quotes = Object.assign({}, quotes, data.quotes || {});
      if(priceStamp && data.asOf) priceStamp.textContent = '가격 갱신 ' + data.asOf;
      render();
    }).catch(function(){
      if(priceStamp) priceStamp.textContent = '가격 갱신 대기';
    });
  }
  if(form){
    form.addEventListener('submit', function(e){
      e.preventDefault();
      var ticker = String(tickerInput && tickerInput.value || '').trim().toUpperCase();
      var qty = num(qtyInput && qtyInput.value);
      var avgCost = num(costInput && costInput.value);
      if(!validTicker(ticker)){
        if(tickerInput){ tickerInput.setCustomValidity('티커를 확인하세요.'); tickerInput.reportValidity(); }
        return;
      }
      if(tickerInput) tickerInput.setCustomValidity('');
      if(qty <= 0 || avgCost <= 0) return;
      var rows = clean(holdings);
      var found = false;
      rows = rows.map(function(r){
        if(r.ticker === ticker){ found = true; return {ticker:ticker, qty:qty, avgCost:avgCost}; }
        return r;
      });
      if(!found) rows.push({ticker:ticker, qty:qty, avgCost:avgCost});
      saveLocal(rows);
      if(qtyInput) qtyInput.value = '';
      if(costInput) costInput.value = '';
      render();
      scheduleRemoteSave();
      fetchQuotes();
    });
    if(tickerInput) tickerInput.addEventListener('input', function(){ tickerInput.setCustomValidity(''); });
  }
  if(syncForm){
    syncForm.addEventListener('submit', function(e){
      e.preventDefault();
      var code = String(syncInput && syncInput.value || '').trim().toUpperCase();
      if(!/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code)){
        if(syncInput){ syncInput.setCustomValidity('동기화 코드를 확인하세요.'); syncInput.reportValidity(); }
        return;
      }
      if(syncInput) syncInput.setCustomValidity('');
      setState('불러오는 중');
      pullRemote(code).catch(function(){ setState('코드를 찾지 못했습니다'); });
    });
    if(syncInput) syncInput.addEventListener('input', function(){ syncInput.setCustomValidity(''); });
  }
  if(createSyncBtn) createSyncBtn.addEventListener('click', createSync);
  if(refreshBtn) refreshBtn.addEventListener('click', function(){
    if(syncCode) pullRemote(syncCode).catch(function(){ setState('동기화 대기'); });
    fetchQuotes();
  });
  renderSync();
  render();
  if(syncCode) pullRemote(syncCode).catch(function(){ setState('동기화 대기'); });
  fetchQuotes();
  quoteTimer = setInterval(fetchQuotes, 5 * 60 * 1000);
})();
"""


def _bar(score: float) -> str:
    """0~100 점수를 코랄 농담 막대로(강=hi 진한 코랄 · 중=mid 연한 클레이 · 약=lo 뮤트)."""
    if score != score:  # NaN
        return "<span class='na'>데이터 없음</span>"
    pct = max(0, min(100, score))
    tier = "hi" if pct >= 60 else ("mid" if pct >= 40 else "lo")
    return (f"<div class='bar'><div class='fill {tier}' style='width:{pct:.0f}%'></div>"
            f"<span class='barlabel'>{pct:.0f}</span></div>")


def _analysis_rows(recs: list[Recommendation]) -> str:
    rows = []
    for i, r in enumerate(recs, 1):
        why = r.why[0] if r.why else "종합점수가 상대적으로 우수"
        risk = r.risks[0] if r.risks else "특이 리스크 메모 없음"
        ind = _industry(r.ticker, r.sector)
        ind_html = f"<br><span class='ind'>{ind}</span>" if ind else ""
        rows.append(
            f"<tr><td class='num'>{i}</td>"
            f"<td><span class='tk'>{r.ticker}</span><br><span>{r.name}</span>{ind_html}</td>"
            f"<td><span class='sc'>{r.composite:.0f}점</span></td>"
            f"<td>{r.confidence}</td>"
            f"<td>{why}</td><td>{risk}</td></tr>"
        )
    return "".join(rows)


def _rec_card(r: Recommendation) -> str:
    sub_bars = "".join(
        f"<tr><td class='axis'>{FACTOR_LABELS_KO[a]}</td><td>{_bar(r.sub_scores.get(a, float('nan')))}</td></tr>"
        for a in _AXES
    )
    why = "".join(f"<li>{w}</li>" for w in r.why) or "<li>—</li>"
    risks = "".join(f"<li>{w}</li>" for w in r.risks) or "<li>특이 리스크 메모 없음</li>"
    price = f"${r.price:,.2f}" if r.price == r.price else "—"
    ind = _industry(r.ticker, r.sector)
    name_line = f"{r.name} · {ind}" if ind else r.name
    return f"""
    <div class="card">
      <div class="card-head">
        <span class="rank-ticker">{r.ticker}</span>
        <span class="rank-name">{name_line}</span>
        <span class="composite">{r.composite:.0f}점</span>
      </div>
      <div class="card-meta">현재가 {price} · 신뢰도 <b>{r.confidence}</b></div>
      <table class="subs">{sub_bars}</table>
      <div class="cols">
        <div><h4>왜 추천?</h4><ul>{why}</ul></div>
        <div><h4>리스크</h4><ul>{risks}</ul></div>
      </div>
    </div>"""


def _holding_universe_from_recs(style_recs: dict[str, list[Recommendation]]) -> list[dict]:
    seen: dict[str, dict] = {}
    for recs in style_recs.values():
        for r in recs:
            ticker = (r.ticker or "").upper()
            if not ticker or ticker in seen:
                continue
            price = float(r.price) if r.price == r.price else None
            seen[ticker] = {
                "ticker": ticker,
                "name": r.name,
                "sector": r.sector,
                "industry": _industry(ticker, r.sector),
                "price": price,
            }
    return sorted(seen.values(), key=lambda item: item["ticker"])


def _normalize_holding_universe(
    holding_universe: list[dict] | None,
    style_recs: dict[str, list[Recommendation]],
) -> list[dict]:
    source = holding_universe or _holding_universe_from_recs(style_recs)
    normalized: dict[str, dict] = {}
    for item in source:
        ticker = str(item.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        price = item.get("price")
        try:
            price = float(price)
            if price != price:
                price = None
        except (TypeError, ValueError):
            price = None
        sector = str(item.get("sector", "") or "")
        normalized[ticker] = {
            "ticker": ticker,
            "name": str(item.get("name", "") or ""),
            "sector": sector,
            "industry": str(item.get("industry", "") or _industry(ticker, sector)),
            "price": price,
        }
    return sorted(normalized.values(), key=lambda item: item["ticker"])


def _holding_options(holding_universe: list[dict]) -> str:
    options = []
    for item in holding_universe:
        ticker = html.escape(item["ticker"])
        label = html.escape(" · ".join(x for x in (item.get("name"), item.get("industry")) if x))
        options.append(f'<option value="{ticker}" label="{label}"></option>')
    return "".join(options)


def build_recommend_report(
    recs: list[Recommendation] | None = None,
    portfolio_result=None,
    universe_size: int = 0,
    analyzed: int = 0,
    style: str = "balanced",
    out_path: str | Path | None = None,
    style_recs: dict[str, list[Recommendation]] | None = None,
    default_style: str | None = None,
    holding_universe: list[dict] | None = None,
) -> Path:
    """추천 리스트를 단일 HTML(Anthropic풍 + 투자성향 토글)로 저장하고 경로를 반환한다.

    style_recs 가 주어지면 여러 투자성향(Balance/Risk Taker/Conservative)의 순위를 모두
    심어 클라이언트(JS)에서 전환할 수 있게 한다. 없으면 recs 단일 성향으로 렌더한다(레거시).
    """
    if style_recs is None:
        style_recs = {style: list(recs or [])}
        default_style = style
    if default_style is None or default_style not in style_recs:
        default_style = next(iter(style_recs))

    today = dt.date.today().strftime("%Y%m%d")
    gen_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    if out_path is None:
        out_path = DEFAULT_RECOMMEND_REPORT
    out_path = Path(out_path)

    # 성향별 표 행 + 카드 HTML 을 미리 렌더해 JS 로 심는다(클라이언트 전환).
    payload = {
        st: {
            "label": _STYLE_LABELS_UX.get(st, st),
            "rows": _analysis_rows(srecs),
            "cards": "".join(_rec_card(r) for r in srecs),
        }
        for st, srecs in style_recs.items()
    }
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    toggle_js = f"window.REPORT_DATA = {data_js};\n{_TOGGLE_JS}"
    holdings_universe = _normalize_holding_universe(holding_universe, style_recs)
    holdings_universe_js = json.dumps(
        {item["ticker"]: item for item in holdings_universe},
        ensure_ascii=False,
    ).replace("</", "<\\/")
    holding_js = f"window.HOLDING_UNIVERSE = {holdings_universe_js};\nwindow.HOLDING_API_BASE = window.HOLDING_API_BASE || '/api';\n{_HOLDINGS_JS}"
    holding_options = _holding_options(holdings_universe)

    analysis_rows = payload[default_style]["rows"]
    cards = payload[default_style]["cards"]
    pills = "".join(
        f'<button class="style-pill{(" active" if st == default_style else "")}" type="button" data-style="{st}">{_STYLE_LABELS_UX.get(st, st)}</button>'
        for st in _UX_ORDER if st in payload
    )

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#f3f1ea">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="수익&플랜">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="./manifest.webmanifest">
<link rel="icon" href="./app_icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="./app_icon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,360;6..72,440;6..72,520&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<title>주식 종합분석 추천 리포트 — {today}</title>
<style>{_STYLE}</style></head>
<body><div class="wrap">

  <header class="hero">
    <p class="eyebrow">S&amp;P 500 · 종합분석 스크리너</p>
    <h1>미국 주식 종합분석<br><em>추천 리포트</em></h1>
    <p class="lead">S&amp;P 500을 가치·품질·성장·추세·심리 다섯 축으로 점수화해,<br>무엇을 어떤 규칙으로 사고팔지 근거와 함께 정리한 참고 자료입니다.</p>
    <div class="controls">
      <span class="ctl-label">투자성향</span>
      <div class="style-toggle" role="group" aria-label="투자성향">{pills}</div>
      <button class="refresh-btn" id="refresh-btn" type="button">↻ 갱신</button>
      <span class="upd">마지막 갱신 {gen_time}</span>
    </div>
  </header>

  <section class="section">
    <p class="eyebrow">ranked analysis</p>
    <h2 class="title">추천 종목 분석</h2>
    <div class="surface">
      <div class="table-wrap"><table class="analysis">
        <colgroup><col style="width:6%"><col style="width:24%"><col style="width:9%"><col style="width:12%"><col style="width:24%"><col style="width:25%"></colgroup>
        <thead><tr><th class="num">#</th><th>종목</th><th>점수</th><th>신뢰도</th><th>핵심 근거</th><th>주요 리스크</th></tr></thead>
        <tbody id="analysis-body">{analysis_rows}</tbody></table></div>
    </div>
  </section>

  <section class="section">
    <p class="eyebrow">per-ticker detail</p>
    <h2 class="title">종목별 상세</h2>
    <p class="sub">5축 점수 · 강점과 리스크</p>

    <div class="rules">
      <div class="rules-head"><h4 class="rules-title">공통 매매 규칙</h4>
        <span class="rules-note">모든 추천 종목에 동일하게 적용 — ‘고점 예측’이 아니라 손실을 제한하기 위한 사전 약속</span></div>
      <div class="rules-cols">
        <div><h5>진입 · 매수</h5><ul>
          <li>한 번에 사지 말고 3회 이상 나눠 분할매수(평균단가 분산)</li>
          <li>현재가가 200일선 위/근처면 분할매수 고려, 아래면 추세 회복(200일선 회복) 확인 후 진입</li>
          <li>단기 급등 직후(과열)라면 눌림목까지 기다리기</li></ul></div>
        <div><h5>청산 · 매도</h5><ul>
          <li>트레일링 손절: 매수 후 고점 대비 −20% 하락하면 기계적으로 매도</li>
          <li>추세 이탈: 종가가 200일 평균선을 의미 있게 하향 이탈하면 비중 축소</li>
          <li>펀더멘털 악화: 다음 분석에서 종합점수가 컷오프(예: 50점) 아래로 내려가면 교체</li></ul></div>
      </div>
    </div>

    <div class="cards" id="cards">{cards}</div>
  </section>

  <section class="section holdings">
    <p class="eyebrow">my holdings</p>
    <h2 class="title">내 보유 종목</h2>
    <div class="holding-shell">
      <div class="sync-panel">
        <div class="sync-code"><span>동기화 코드</span><b id="sync-code-label">이 기기만</b><span class="sync-state" id="sync-state"></span></div>
        <form class="sync-form" id="sync-form">
          <div class="field"><label for="sync-code-input">코드 연결</label><input id="sync-code-input" type="text" inputmode="latin" autocomplete="off" placeholder="ABCD-1234"></div>
          <button class="mini-btn secondary" type="submit">연결</button>
        </form>
        <button class="mini-btn" id="create-sync-btn" type="button">코드 만들기</button>
        <button class="mini-btn secondary" id="refresh-holdings-btn" type="button">↻ 갱신</button>
      </div>
      <div class="holding-summary" id="holding-summary"></div>
      <form class="holding-form" id="holding-form">
        <div class="field"><label for="holding-ticker">종목</label><input id="holding-ticker" list="holding-tickers" type="text" inputmode="latin" autocomplete="off" placeholder="AAPL"></div>
        <div class="field"><label for="holding-qty">수량</label><input id="holding-qty" type="number" min="0" step="any" placeholder="0"></div>
        <div class="field"><label for="holding-cost">평균 매입가($)</label><input id="holding-cost" type="number" min="0" step="any" placeholder="0.00"></div>
        <button class="holding-add" type="submit">추가</button>
      </form>
      <datalist id="holding-tickers">{holding_options}</datalist>
      <div class="table-wrap"><table class="holding-table">
        <thead><tr><th>종목</th><th>수량</th><th>평균가</th><th>현재가</th><th>평가손익</th><th>상태</th><th></th></tr></thead>
        <tbody id="holding-body"></tbody>
      </table></div>
      <div class="empty-holdings" id="holding-empty">보유 종목 없음</div>
      <div class="price-stamp" id="price-stamp">가격 갱신 대기</div>
    </div>
  </section>
</div>
<script>
  if ("serviceWorker" in navigator && location.protocol !== "file:") {{
    window.addEventListener("load", () => {{
      navigator.serviceWorker.register("./sw.js").catch(() => {{}});
    }});
  }}
</script>
<script>{toggle_js}</script>
<script>{holding_js}</script>
</body></html>"""

    out_path.write_text(html, encoding="utf-8")
    return out_path
