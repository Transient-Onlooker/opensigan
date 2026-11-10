import asyncio
import json
import logging
import re
import secrets
import time
from datetime import date
from urllib.parse import parse_qs, urlsplit

from workers import Response, WorkerEntrypoint
import requests

from backend.neis import NEISClient, NEISNetworkError, School
from backend.timetable import fetch_timetable, search_schools, validate_timetable_week
from d1_cache import D1Cache

# urllib3 debug output includes the request path and NEIS key.
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

CACHE_CONTENTION_RETRIES = 3
CACHE_CONTENTION_DELAY_SECONDS = 0.05
NEIS_CONTENTION_RETRIES = 12
NEIS_CONTENTION_DELAY_SECONDS = 0.1
CACHE_MAINTENANCE_INTERVAL_SECONDS = 6 * 60 * 60
CACHE_MAINTENANCE_FAILURE_RETRY_SECONDS = 5 * 60
_monotonic = time.monotonic
_next_cache_maintenance_at = 0.0


def _claim_cache_maintenance() -> bool:
    """Throttle pruning within this isolate; this is not a distributed lock."""
    global _next_cache_maintenance_at
    now = _monotonic()
    if now < _next_cache_maintenance_at:
        return False
    _next_cache_maintenance_at = now + CACHE_MAINTENANCE_INTERVAL_SECONDS
    return True


def _defer_cache_maintenance_retry() -> None:
    global _next_cache_maintenance_at
    _next_cache_maintenance_at = _monotonic() + CACHE_MAINTENANCE_FAILURE_RETRY_SECONDS


def neis_transport(url, timeout):
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise NEISNetworkError("NEIS request failed")
        return response.content
    except requests.exceptions.RequestException:
        raise NEISNetworkError("NEIS request failed") from None


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        origin = request.headers.get("Origin")
        allowed_origin = getattr(self.env, "CORS_ALLOWED_ORIGIN", None)
        cors_origin = origin if origin and origin == allowed_origin else None
        if request.method == "OPTIONS":
            if cors_origin is None:
                return self.respond(403, {"error": "origin not allowed"})
            return Response(None, status=204, headers={
                "access-control-allow-origin": cors_origin,
                "access-control-allow-methods": "GET, OPTIONS",
                "access-control-allow-headers": "Accept",
                "access-control-max-age": "86400",
                "vary": "Origin",
                "cache-control": "no-store",
            })
        if request.method != "GET":
            return self.respond(405, {"error": "method not allowed"}, cors_origin)
        parts = urlsplit(request.url)
        query = parse_qs(parts.query, keep_blank_values=True)
        try:
            if parts.path in ("/status", "/api/v1/status"):
                result = {"status": "ok", "scope": "process liveness"}
            elif parts.path in ("/schools", "/api/v1/schools"):
                name = self.query(query, "q", 50)
                result = await self.cached(["schools", name], lambda: {"schools": search_schools(name), "stale": False}, origin="comcigan")
            elif parts.path in ("/timetable", "/api/v1/timetable"):
                school = self.query(query, "school", 100)
                if not re.fullmatch(r"[0-9]+:[^:]{1,50}", school) or int(school.split(":", 1)[0]) == 0:
                    raise ValueError("invalid school identifier")
                week = self.query(query, "week", 10)
                week_offset = validate_timetable_week(week)
                def check_week():
                    if validate_timetable_week(week) != week_offset:
                        raise ValueError("school week changed during request")
                result = await self.cached(["timetable", school, week], lambda: fetch_timetable(school, week), check_week,
                                           origin="comcigan")
                check_week()
            elif parts.path == "/api/v1/neis/schools":
                name = self.query(query, "q", 50)
                api_key = self.env.NEIS_API_KEY
                if not api_key or not api_key.strip():
                    raise RuntimeError("NEIS key is not configured")
                def load_schools():
                    schools = NEISClient(api_key, transport=neis_transport).search_schools(name)
                    return {"schools": [{"id": f"{school.office_code}:{school.school_code}",
                    "name": school.name, "region": school.kind, "address": school.address}
                    for school in schools], "stale": False}
                result = await self.cached(["neis-schools", name], load_schools, origin="neis")
            elif parts.path == "/api/v1/meals":
                school_id = self.query(query, "school", 20)
                if not re.fullmatch(r"[A-Z][0-9]{2}:[0-9]{7}", school_id):
                    raise ValueError("invalid school identifier")
                start_text = self.query(query, "from", 10)
                end_text = self.query(query, "to", 10)
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", start_text):
                    raise ValueError("invalid from")
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", end_text):
                    raise ValueError("invalid to")
                start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
                if end < start or (end - start).days > 6:
                    raise ValueError("invalid date range")
                api_key = self.env.NEIS_API_KEY
                if not api_key or not api_key.strip():
                    raise RuntimeError("NEIS key is not configured")
                office, code = school_id.split(":")
                def load_meals():
                    meals = NEISClient(api_key, transport=neis_transport).get_meals(School(office, code, ""), start, end)
                    return {"meals": [{"date": meal.date, "type": meal.meal_type,
                    "dishes": re.split(r"<br\s*/?>", meal.menu, flags=re.I)}
                    for meal in meals], "stale": False}
                result = await self.cached(["meals", school_id, start_text, end_text], load_meals,
                                           origin="neis")
            else:
                return self.respond(404, {"error": "not found"}, cors_origin)
        except ValueError as exc:
            return self.respond(400, {"error": str(exc)}, cors_origin)
        except Exception:
            # Upstream exceptions can contain request data.
            return self.respond(503, {"error": "upstream unavailable"}, cors_origin)
        return self.respond(200, result, cors_origin)

    async def cached(self, components, load, check=None, *, origin):
        try:
            return await self._cached(components, load, check, origin)
        except ValueError as exc:
            raise RuntimeError("cache unavailable") from exc

    async def _cached(self, components, load, check, origin):
        database = getattr(self.env, "DB", None)
        if database is None:
            raise RuntimeError("cache unavailable")
        cache = D1Cache(database)
        key = "opensigan:" + json.dumps(components, ensure_ascii=False, separators=(",", ":"))
        now = int(time.time())
        if _claim_cache_maintenance():
            try:
                await cache.prune(now=now)
            except Exception:
                # Maintenance must not make cache reads or stale serving unavailable.
                _defer_cache_maintenance_retry()
                logging.warning("cache maintenance failed")
        entry = await cache.read(key)
        if entry and entry.fresh(now):
            return entry.value
        stale = (entry.value if entry and entry.has_value
                 and entry.expires_at + cache.stale_retention_seconds > now else None)
        token = None
        contention_retries = NEIS_CONTENTION_RETRIES if origin == "neis" else CACHE_CONTENTION_RETRIES
        contention_delay = NEIS_CONTENTION_DELAY_SECONDS if origin == "neis" else CACHE_CONTENTION_DELAY_SECONDS
        for attempt in range(contention_retries + 1):
            if attempt:
                await asyncio.sleep(contention_delay)
                try:
                    entry = await cache.read(key)
                except Exception:
                    if stale is not None:
                        return {**stale, "stale": True}
                    raise
                now = int(time.time())
                if entry and entry.fresh(now):
                    return entry.value
                stale = (entry.value if entry and entry.has_value
                         and entry.expires_at + cache.stale_retention_seconds > now else None)
                if stale is not None:
                    return {**stale, "stale": True}
            now = int(time.time())
            if entry and entry.retry_after is not None and entry.retry_after > now:
                if stale is not None:
                    return {**stale, "stale": True}
                raise RuntimeError("cache refresh unavailable")
            token = secrets.token_urlsafe(32)
            try:
                acquired = await cache.acquire_refresh(
                    key, token, origin=origin, now=now, lease_seconds=120,
                    rate_now_ms=int(time.time() * 1000))
            except Exception:
                if stale is not None:
                    return {**stale, "stale": True}
                raise
            if acquired:
                break
            if stale is not None:
                return {**stale, "stale": True}
        else:
            raise RuntimeError("cache refresh unavailable")
        try:
            value = load()
            if check:
                check()
            if not await cache.store_success(key, token, value, now=int(time.time()), ttl_seconds=1800):
                raise RuntimeError("cache lease lost")
            return value
        except Exception as exc:
            try:
                await cache.store_failure(key, token, now=int(time.time()))
            except Exception:
                if stale is None:
                    raise RuntimeError("cache failure recording unavailable") from None
            if stale is not None:
                return {**stale, "stale": True}
            raise RuntimeError("cache refresh failed") from exc

    @staticmethod
    def query(params, key, limit):
        values = params.get(key, [])
        if len(values) != 1 or not values[0].strip() or len(values[0]) > limit:
            raise ValueError(f"invalid {key}")
        return values[0].strip()

    @staticmethod
    def respond(status, result, allowed_origin=None):
        headers = {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "vary": "Origin",
        }
        if allowed_origin:
            headers["access-control-allow-origin"] = allowed_origin
        return Response(json.dumps(result, ensure_ascii=False, allow_nan=False), status=status,
                        headers=headers)
