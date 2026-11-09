"""Explicit, limited manual probe of NEIS's unauthenticated sample endpoint."""

from datetime import date
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen
from unittest.mock import patch

from backend.app import Handler
from backend.cache import Cache
from backend.neis import NEISClient


def sample_transport(url, timeout):
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "KEY"]
    with urlopen(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)), timeout=timeout) as response:
        return response.read()


if __name__ == "__main__":
    client = NEISClient("sample-probe", transport=sample_transport)
    schools = client.search_schools("경기고등학교")
    print("school candidates:", len(schools))
    if len(schools) != 1:
        raise SystemExit("The sample school lookup was not unique")
    meals = client.get_meals(schools[0], date(2026, 11, 9), date(2026, 11, 9))
    print("meals:", len(meals))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.dict("os.environ", {"NEIS_API_KEY": "sample-probe"}), \
                patch("backend.app.NEISClient.from_environment", return_value=client), \
                patch("backend.app.cache", Cache()):
            query = urlencode({"school": f"{schools[0].office_code}:{schools[0].school_code}",
                               "from": "2026-11-09", "to": "2026-11-09"})
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/v1/meals?{query}") as response:
                result = json.load(response)
            if len(result["meals"]) != len(meals) or result["stale"]:
                raise SystemExit("The API response did not match the sample")
            print("HTTP meals:", len(result["meals"]))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
