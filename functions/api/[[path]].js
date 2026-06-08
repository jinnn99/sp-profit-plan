const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

function withCors(headers = {}) {
  return {
    ...headers,
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,PUT,OPTIONS",
    "access-control-allow-headers": "content-type",
  };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: withCors(JSON_HEADERS),
  });
}

function normalizeCode(code) {
  return String(code || "").trim().toUpperCase();
}

function normalizeTicker(ticker) {
  return String(ticker || "").trim().toUpperCase().replace("_", "-");
}

function cleanHoldings(rows) {
  if (!Array.isArray(rows)) return [];
  return rows
    .map((row) => ({
      ticker: normalizeTicker(row.ticker),
      qty: Number(row.qty),
      avgCost: Number(row.avgCost),
    }))
    .filter((row) => (
      /^[A-Z0-9.-]{1,12}$/.test(row.ticker)
      && Number.isFinite(row.qty)
      && Number.isFinite(row.avgCost)
      && row.qty > 0
      && row.avgCost > 0
    ))
    .slice(0, 100);
}

async function readJson(request) {
  try {
    return await request.json();
  } catch (_) {
    return {};
  }
}

function makeCode() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  const chars = Array.from(bytes, (byte) => alphabet[byte % alphabet.length]);
  return `${chars.slice(0, 4).join("")}-${chars.slice(4).join("")}`;
}

async function createSyncCode(env, holdings) {
  for (let i = 0; i < 8; i += 1) {
    const code = makeCode();
    const now = Date.now();
    try {
      await env.DB.prepare(
        "INSERT INTO holdings (code, payload, updated_at) VALUES (?1, ?2, ?3)"
      ).bind(code, JSON.stringify({ holdings }), now).run();
      return { code, holdings, updatedAt: now };
    } catch (_) {
      // Retry on the tiny chance of a code collision.
    }
  }
  throw new Error("failed_to_create_code");
}

async function getHoldings(env, code) {
  const row = await env.DB.prepare(
    "SELECT payload, updated_at FROM holdings WHERE code = ?1"
  ).bind(code).first();
  if (!row) return null;
  let payload = {};
  try {
    payload = JSON.parse(row.payload || "{}");
  } catch (_) {
    payload = {};
  }
  return {
    code,
    holdings: cleanHoldings(payload.holdings || []),
    updatedAt: row.updated_at,
  };
}

async function putHoldings(env, code, holdings) {
  const now = Date.now();
  await env.DB.prepare(
    "INSERT INTO holdings (code, payload, updated_at) VALUES (?1, ?2, ?3) "
    + "ON CONFLICT(code) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at"
  ).bind(code, JSON.stringify({ holdings }), now).run();
  return { code, holdings, updatedAt: now };
}

async function readCachedQuote(env, symbol, now, ttlMs) {
  const row = await env.DB.prepare(
    "SELECT payload, fetched_at FROM quote_cache WHERE symbol = ?1"
  ).bind(symbol).first();
  if (!row) return null;
  let payload = null;
  try {
    payload = JSON.parse(row.payload || "null");
  } catch (_) {
    payload = null;
  }
  if (!payload) return null;
  return {
    payload,
    fresh: Number(row.fetched_at || 0) + ttlMs > now,
  };
}

async function writeCachedQuote(env, symbol, payload, now) {
  await env.DB.prepare(
    "INSERT INTO quote_cache (symbol, payload, fetched_at) VALUES (?1, ?2, ?3) "
    + "ON CONFLICT(symbol) DO UPDATE SET payload = excluded.payload, fetched_at = excluded.fetched_at"
  ).bind(symbol, JSON.stringify(payload), now).run();
}

async function fetchYahooQuotes(symbols) {
  if (!symbols.length) return {};
  const url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols="
    + encodeURIComponent(symbols.join(","));
  const response = await fetch(url, {
    headers: {
      "user-agent": "Mozilla/5.0",
      "accept": "application/json",
    },
  });
  if (!response.ok) throw new Error(`quote_fetch_${response.status}`);
  const data = await response.json();
  const results = data?.quoteResponse?.result || [];
  const out = {};
  for (const item of results) {
    const symbol = normalizeTicker(item.symbol);
    const price = Number(
      item.regularMarketPrice ?? item.postMarketPrice ?? item.preMarketPrice
    );
    if (!symbol || !Number.isFinite(price)) continue;
    out[symbol] = {
      ticker: symbol,
      name: item.shortName || item.longName || "",
      price,
      currency: item.currency || "USD",
      source: "yahoo",
    };
  }
  return out;
}

async function getQuotes(env, url) {
  const raw = url.searchParams.get("symbols") || "";
  const symbols = Array.from(new Set(
    raw.split(",").map(normalizeTicker).filter((s) => /^[A-Z0-9.-]{1,12}$/.test(s))
  )).slice(0, 40);
  const now = Date.now();
  const ttlSeconds = Number(env.QUOTE_TTL_SECONDS || 300);
  const ttlMs = Math.max(60, Math.min(ttlSeconds, 900)) * 1000;
  const quotes = {};
  const missing = [];

  for (const symbol of symbols) {
    const cached = await readCachedQuote(env, symbol, now, ttlMs);
    if (cached?.payload) quotes[symbol] = cached.payload;
    if (!cached?.fresh) missing.push(symbol);
  }

  if (missing.length) {
    try {
      const fresh = await fetchYahooQuotes(missing);
      await Promise.all(Object.entries(fresh).map(([symbol, payload]) => (
        writeCachedQuote(env, symbol, payload, now)
      )));
      Object.assign(quotes, fresh);
    } catch (_) {
      // Keep any stale cache. The app also has build-time prices embedded.
    }
  }

  return {
    quotes,
    asOf: new Date(now).toISOString().replace("T", " ").slice(0, 16),
    ttlSeconds: ttlMs / 1000,
  };
}

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: withCors() });
  }
  if (!env.DB) {
    return json({ error: "D1 binding DB is not configured" }, 503);
  }

  const url = new URL(request.url);
  const parts = url.pathname.replace(/^\/api\/?/, "").split("/").filter(Boolean);

  try {
    if (request.method === "GET" && parts[0] === "health") {
      return json({ ok: true });
    }
    if (request.method === "POST" && parts[0] === "sync-code") {
      const body = await readJson(request);
      return json(await createSyncCode(env, cleanHoldings(body.holdings || [])));
    }
    if (parts[0] === "holdings" && parts[1]) {
      const code = normalizeCode(parts[1]);
      if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code)) {
        return json({ error: "invalid_code" }, 400);
      }
      if (request.method === "GET") {
        const data = await getHoldings(env, code);
        return data ? json(data) : json({ error: "not_found" }, 404);
      }
      if (request.method === "PUT") {
        const body = await readJson(request);
        return json(await putHoldings(env, code, cleanHoldings(body.holdings || [])));
      }
    }
    if (request.method === "GET" && parts[0] === "quotes") {
      return json(await getQuotes(env, url));
    }
  } catch (error) {
    return json({ error: error.message || "api_error" }, 500);
  }

  return json({ error: "not_found" }, 404);
}

