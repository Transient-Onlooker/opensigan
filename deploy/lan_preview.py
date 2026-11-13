import os
import re
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
        elif re.fullmatch(r"/opensigan/assets/[\w-][\w.-]*", path):
            self.path = path.removeprefix("/opensigan")
        else:
            return self.send_error(404)
        return send(self)

    def do_GET(self):
        if urlsplit(self.path).path.startswith("/api/"):
            return super().do_GET()
        return self._serve_frontend(SimpleHTTPRequestHandler.do_GET)

    def do_HEAD(self):
        if urlsplit(self.path).path.startswith("/api/"):
            return super().do_HEAD()
        return self._serve_frontend(SimpleHTTPRequestHandler.do_HEAD)


if __name__ == "__main__":
    if not (FRONTEND_DIR / "index.html").is_file():
        raise SystemExit("Build the LAN frontend before starting the preview.")
    ThreadingHTTPServer((os.environ["LAN_HOST"], 8080), PreviewHandler).serve_forever()
