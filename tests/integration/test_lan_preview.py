import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from deploy.lan_preview import PreviewHandler


class LanPreviewTests(unittest.TestCase):
    def test_preview_routes_frontend_and_api_on_same_origin(self):
        temp_root = Path(os.environ["LOCALAPPDATA"]) / "Temp" if os.name == "nt" else None
        with tempfile.TemporaryDirectory(prefix="opensigan-preview-", dir=temp_root) as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "index.html").write_text("<title>OpenSigan</title>", encoding="utf-8")
            (root / "api-docs.html").write_text("API docs", encoding="utf-8")
            (root / "analytics.html").write_text("Analytics", encoding="utf-8")
            (root / "openapi.yaml").write_text("openapi: 3.1.0", encoding="utf-8")
            (root / "assets" / "index-test.js").write_text("export {};", encoding="utf-8")
            with patch("deploy.lan_preview.FRONTEND_DIR", root), \
                    ThreadingHTTPServer(("127.0.0.1", 0), PreviewHandler) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    def request(method, path):
                        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                        try:
                            connection.request(method, path)
                            response = connection.getresponse()
                            return response.status, response.read()
                        finally:
                            connection.close()

                    self.assertEqual(request("GET", "/opensigan/"), (200, b"<title>OpenSigan</title>"))
                    self.assertEqual(request("HEAD", "/opensigan/assets/index-test.js"), (200, b""))
                    self.assertEqual(request("GET", "/opensigan/api-docs.html"), (200, b"API docs"))
                    self.assertEqual(request("GET", "/opensigan/openapi.yaml"), (200, b"openapi: 3.1.0"))
                    self.assertEqual(request("GET", "/assets/index-test.js"), (200, b"export {};"))
                    self.assertEqual(request("GET", "/api-docs.html"), (200, b"API docs"))
                    self.assertEqual(request("GET", "/analytics.html"), (200, b"Analytics"))
                    self.assertEqual(request("GET", "/opensigan/analytics.html"), (200, b"Analytics"))
                    self.assertEqual(request("GET", "/assets/../index.html")[0], 404)
                    status, body = request("GET", "/api/v1/status")
                    self.assertEqual(status, 200)
                    self.assertEqual(json.loads(body)["status"], "ok")
                    self.assertEqual(request("GET", "/opensigan/assets/")[0], 404)
                finally:
                    server.shutdown()
                    thread.join()
