import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from backend.app import Handler


class PreviewHandler(Handler, SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=Path("frontend/dist"), **kwargs)

    def list_directory(self, path):
        self.send_error(404)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            return super().do_GET()
        if path in {"/", "/opensigan", "/opensigan/"}:
            self.path = "/index.html"
        elif path.startswith("/opensigan/assets/") and "/" not in path.removeprefix("/opensigan/assets/"):
            self.path = path.removeprefix("/opensigan")
        else:
            return self.send_error(404)
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_HEAD(self):
        self.send_error(405)


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ["LAN_HOST"], 8080), PreviewHandler).serve_forever()
