CREATE TABLE IF NOT EXISTS d1_cache (
    cache_key TEXT PRIMARY KEY NOT NULL,
    origin TEXT NOT NULL,
    payload TEXT,
    expires_at INTEGER NOT NULL DEFAULT 0,
    refresh_owner TEXT,
    lease_until INTEGER,
    last_refresh_at INTEGER,
    failures INTEGER NOT NULL DEFAULT 0 CHECK (failures >= 0),
    retry_after INTEGER,
    CHECK ((refresh_owner IS NULL) = (lease_until IS NULL))
);

CREATE INDEX IF NOT EXISTS d1_cache_expiry_idx ON d1_cache(expires_at);
CREATE INDEX IF NOT EXISTS d1_cache_origin_active_lease_idx ON d1_cache(origin, lease_until)
    WHERE refresh_owner IS NOT NULL;
CREATE INDEX IF NOT EXISTS d1_cache_origin_last_refresh_idx ON d1_cache(origin, last_refresh_at)
    WHERE last_refresh_at IS NOT NULL;
