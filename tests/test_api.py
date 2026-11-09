import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from backend.app import Handler
from backend.neis import Meal, School


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path):
        with urlopen(self.base + path) as response:
            return json.load(response)

    def test_school_search_and_meals(self):
        with patch("backend.app.search_schools", return_value=[{"id": "2:school", "name": "school", "region": "region"}]):
            self.assertEqual(self.get("/api/v1/schools?q=school")["schools"][0]["id"], "2:school")
        with patch.dict("os.environ", {"NEIS_API_KEY": "test-key"}), patch("backend.app.NEISClient.from_environment") as factory:
            factory.return_value.search_schools.return_value = [School("B10", "1234567", "school", "high", "address")]
            factory.return_value.get_meals.return_value = [Meal("2026-11-10", "lunch", "rice(1)<br/>soup(2)")]
            self.assertEqual(self.get("/api/v1/neis/schools?q=school")["schools"][0]["id"], "B10:1234567")
            meals = self.get("/api/v1/meals?school=B10%3A1234567&from=2026-11-09&to=2026-11-15")
            self.assertEqual(meals["meals"][0]["dishes"], ["rice(1)", "soup(2)"])

    def test_invalid_inputs_and_upstream_failure(self):
        for path in ["/api/v1/schools?q=", "/api/v1/meals?school=invalid&from=2026-11-09&to=2026-11-15"]:
            with self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertEqual(error.exception.code, 400)
        with patch("backend.app.search_schools", side_effect=RuntimeError("secret details")):
            with self.assertRaises(HTTPError) as error:
                self.get("/api/v1/schools?q=school")
            self.assertEqual(error.exception.code, 503)
            self.assertNotIn("secret details", error.exception.read().decode())


if __name__ == "__main__":
    unittest.main()
