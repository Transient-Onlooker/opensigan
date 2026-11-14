import os
import re
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from backend.app import Handler

FRONTEND_DIR = Path("frontend/dist")


class PreviewHandler(Handler, SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def list_directory(self, path):
        self.send_error(404)

    def _serve_frontend(self, send):
        path = urlsplit(self.path).path
        if path in {"/", "/opensigan", "/opensigan/"}:
            self.path = "/index.html"
        elif path in {"/api-docs.html", "/openapi.yaml", "/analytics.html", "/opensigan/api-docs.html", "/opensigan/openapi.yaml", "/opensigan/analytics.html"}:
            self.path = path.removeprefix("/opensigan")
        elif re.fullmatch(r"/(?:opensigan/)?assets/[\w-][\w.-]*", path):
            self.path = path.removeprefix("/opensigan")
        else:
            return self.send_error(404)
        return send(self)

    def do_GET(self):
        self._timing_started = time.perf_counter()
        self._timing_path = urlsplit(self.path).path
        if self._timing_path.startswith("/api/"):
            return super().do_GET()
        return self._serve_frontend(SimpleHTTPRequestHandler.do_GET)

    def send_response(self, code, message=None):
        super().send_response(code, message)
        if hasattr(self, "_timing_started"):
            elapsed = (time.perf_counter() - self._timing_started) * 1000
            self.send_header("Server-Timing", f"app;dur={elapsed:.2f}")
            self.log_message("timing path=%s status=%s app_ms=%.2f", self._timing_path, code, elapsed)

    def do_HEAD(self):
        if urlsplit(self.path).path.startswith("/api/"):
            return super().do_HEAD()
        return self._serve_frontend(SimpleHTTPRequestHandler.do_HEAD)


if __name__ == "__main__":
    if not (FRONTEND_DIR / "index.html").is_file():
        raise SystemExit("Build the LAN frontend before starting the preview.")
    ThreadingHTTPServer((os.environ["LAN_HOST"], 8080), PreviewHandler).serve_forever()
