"""휴대폰 브라우저에서 고정 리포트를 보기 위한 작은 로컬 서버."""
from __future__ import annotations

import argparse
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_FILE = "S&P_수익&플랜.html"


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class ReportHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path in ("", "/"):
            self.path = "/" + REPORT_FILE
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="S&P 수익 플랜 모바일 서버")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ReportHandler)
    ip = _local_ip()
    print(f"PC: http://127.0.0.1:{args.port}/")
    print(f"PHONE: http://{ip}:{args.port}/")
    print("종료하려면 Ctrl+C")
    server.serve_forever()


if __name__ == "__main__":
    main()
