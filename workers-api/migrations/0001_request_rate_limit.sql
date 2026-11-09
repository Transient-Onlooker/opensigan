ALTER TABLE d1_cache ADD COLUMN last_refresh_at INTEGER;

CREATE INDEX d1_cache_origin_last_refresh_idx ON d1_cache(origin, last_refresh_at)
    WHERE last_refresh_at IS NOT NULL;
