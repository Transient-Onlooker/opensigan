import io
import json
import os
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from backend.app import Handler, ThreadingWSGIServer, make_app, serve
from backend.cache import Cache


class WsGITests(unittest.TestCase):
    def setUp(self):
        self.cache = Cache()
        self.app = make_app(cache_instance=self.cache)

    def _call_app(self, method, path, query_string="", headers=None, body=b""):
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query_string,
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "80",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": io.StringIO(),
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }
        if headers:
            for k, v in headers.items():
                environ["HTTP_" + k.upper().replace("-", "_")] = v

        captured = {}

        def start_response(status, response_headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = dict(response_headers)

        response_iter = self.app(environ, start_response)
        response_body = b"".join(response_iter)
        return captured.get("status"), captured.get("headers"), response_body

    def test_status_endpoint_via_wsgi(self):
        status, headers, body = self._call_app("GET", "/api/v1/status")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data, {"status": "ok", "scope": "process liveness"})

    def test_cors_options_preflight(self):
        with patch.dict(os.environ, {"ALLOWED_ORIGIN": "https://transient-onlooker.github.io"}):
            status, headers, body = self._call_app("OPTIONS", "/api/v1/schools", "q=test")
            self.assertEqual(status, "204 No Content")
            self.assertEqual(headers["Access-Control-Allow-Origin"], "https://transient-onlooker.github.io")
            self.assertIn("OPTIONS", headers["Access-Control-Allow-Methods"])
            self.assertEqual(body, b"")

    def test_head_method_returns_headers_with_empty_body(self):
        status, headers, body = self._call_app("HEAD", "/api/v1/status")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(body, b"")

    def test_method_not_allowed(self):
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            status, headers, body = self._call_app(method, "/api/v1/status")
            self.assertEqual(status, "405 Method Not Allowed")
            data = json.loads(body.decode("utf-8"))
            self.assertIn("error", data)

    def test_not_found(self):
        status, headers, body = self._call_app("GET", "/api/v1/unknown")
        self.assertEqual(status, "404 Not Found")
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["error"], "요청한 경로가 없습니다")

    def test_invalid_query_parameter(self):
        status, headers, body = self._call_app("GET", "/api/v1/schools", "q=")
        self.assertEqual(status, "400 Bad Request")
        data = json.loads(body.decode("utf-8"))
        self.assertIn("error", data)

    def test_live_threading_wsgi_server(self):
        import wsgiref.simple_server

        server = wsgiref.simple_server.make_server(
            "127.0.0.1", 0, self.app, server_class=ThreadingWSGIServer
        )
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/api/v1/status")
            res = conn.getresponse()
            self.assertEqual(res.status, 200)
            payload = json.loads(res.read().decode("utf-8"))
            self.assertEqual(payload["status"], "ok")
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
