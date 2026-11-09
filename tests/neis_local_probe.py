"""Manual real-NEIS check through an isolated local HTTP server."""

import argparse
import json
import os
import threading
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

from backend.app import Handler
from backend.cache import Cache


class QuietHandler(Handler):
    def log_message(self, format, *args):
        pass


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass


def main():
    parser = argparse.ArgumentParser(description="Manual NEIS local HTTP integration check")
    parser.add_argument("school", help="school name yielding exactly one result")
    parser.add_argument("day", nargs="?", type=date.fromisoformat, default=date.today(), help="date (YYYY-MM-DD; default: today)")
    args = parser.parse_args()

    env_path = Path(__file__).resolve().parents[1] / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
        keys = [line.split("=", 1)[1].strip() for line in lines if line.startswith("NEIS_API_KEY=")]
        if len(keys) != 1 or not keys[0]:
            raise ValueError
    except (OSError, UnicodeError, ValueError):
        raise SystemExit("Could not load a single nonempty NEIS_API_KEY from .env") from None

    server = QuietServer(("127.0.0.1", 0), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    opener = build_opener(ProxyHandler({}))

    def request(path, params, field):
        url = f"http://127.0.0.1:{server.server_port}{path}?{urlencode(params)}"
        try:
            with opener.open(url, timeout=60) as response:
                status = response.status
                payload = json.load(response)
        except HTTPError as error:
            print(f"{field}: HTTP {error.code}")
            return None
        if not isinstance(payload[field], list):
            raise ValueError
        print(f"{field}: HTTP {status}, count {len(payload[field])}")
        if payload.get("stale") is not False:
            return None
        return payload[field]

    try:
        with patch.dict(os.environ, {"NEIS_API_KEY": keys[0]}), \
                patch("backend.app.cache", Cache()), \
                patch("backend.app.logger.exception"):
            thread.start()
            schools = request("/api/v1/neis/schools", {"q": args.school}, "schools")
            if schools is None or len(schools) != 1:
                raise SystemExit("School lookup failed or did not return exactly one result")
            meals = request("/api/v1/meals", {"school": schools[0]["id"],
                            "from": args.day.isoformat(), "to": args.day.isoformat()}, "meals")
            if meals is None:
                raise SystemExit("Meal lookup failed")
    except Exception:
        raise SystemExit("Local integration check failed") from None
    finally:
        if thread.is_alive():
            server.shutdown()
            thread.join()
        server.server_close()


if __name__ == "__main__":
    main()
