CREATE TABLE IF NOT EXISTS holdings (
  code TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quote_cache (
  symbol TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  fetched_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quote_cache_fetched_at
  ON quote_cache (fetched_at);

