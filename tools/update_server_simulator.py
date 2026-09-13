"""
update_server_simulator.py — Basit HTTP güncelleme sunucusu simülatörü.

Gerçek bir güncelleme sunucusu olmadan `launcher.Launcher`'ı uçtan uca
test edebilmek için. `tools/modbus_simulator.py` ile aynı ruhta: sadece
standart kütüphane, hiçbir üçüncü parti paket gerektirmiyor.

Bir `version.json` manifestini ve içeriği `files` sözlüğünden verilen bir
`.zip` dosyasını serve eder. `Launcher.fetch_remote_manifest()` ve
`Launcher.download_update()` bu sunucuya karşı gerçekten çalıştırılabilir.

Kullanım:
    sim = UpdateServerSimulator(host="127.0.0.1", port=0)
    sim.set_manifest({"version": "1.1.0", "url": sim.zip_url, "sha256": "..."})
    sim.set_zip_bytes(zip_bytes)
    sim.start()
    ...
    sim.stop()
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class UpdateServerSimulator:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self._manifest: dict | None = None
        self._zip_bytes: bytes = b""
        self._server = HTTPServer((host, port), self._make_handler())
        self.port = self._server.server_port
        self._thread: threading.Thread | None = None

    @property
    def manifest_url(self) -> str:
        return f"http://{self.host}:{self.port}/version.json"

    @property
    def zip_url(self) -> str:
        return f"http://{self.host}:{self.port}/update.zip"

    def set_manifest(self, manifest: dict) -> None:
        self._manifest = manifest

    def set_zip_bytes(self, data: bytes) -> None:
        self._zip_bytes = data

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _make_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (http.server API'si)
                if self.path == "/version.json" and outer._manifest is not None:
                    body = json.dumps(outer._manifest).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/update.zip":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Length", str(len(outer._zip_bytes)))
                    self.end_headers()
                    self.wfile.write(outer._zip_bytes)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args) -> None:  # noqa: A002
                pass  # test çıktısını kirletmesin

        return Handler
