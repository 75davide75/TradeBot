#!/usr/bin/env python3
"""
Server locale della dashboard, sulla rete di casa.

Serve la stessa identica pagina pubblicata su GitHub Pages (docs/index.html),
rigenerando data.json a ogni richiesta. Una sola pagina da mantenere: se il
locale e il pubblico divergessero, prima o poi guarderesti quello sbagliato.

Uso:  python3 dashboard.py
Poi:  http://<ip-del-pi>:8080
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from core import BASE, load_config
from publish import DOCS, costruisci

CFG = load_config()

TIPI = {".html": "text/html; charset=utf-8", ".json": "application/json",
        ".css": "text/css", ".js": "text/javascript"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"

        if path == "/data.json":
            body = json.dumps(costruisci()).encode()   # sempre fresco
            tipo = TIPI[".json"]
        else:
            # niente path traversal: si esce solo da dentro docs/
            f = os.path.normpath(os.path.join(DOCS, path.lstrip("/")))
            if not f.startswith(DOCS) or not os.path.isfile(f):
                self.send_error(404)
                return
            body = open(f, "rb").read()
            tipo = TIPI.get(os.path.splitext(f)[1], "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    porta = CFG.get("dashboard_port", 8080)
    print(f"Dashboard locale su http://0.0.0.0:{porta}")
    HTTPServer(("0.0.0.0", porta), Handler).serve_forever()
