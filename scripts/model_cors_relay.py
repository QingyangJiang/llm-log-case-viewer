#!/usr/bin/env python3
"""Restricted local CORS relay for the NIO Anthropic Messages endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


DEFAULT_UPSTREAM = "https://model.nioint.com/token-x/v1/messages"
DEFAULT_ORIGIN = "http://10.129.72.139:8080"
DEFAULT_PORT = 19001
MAX_BODY_BYTES = 32 * 1024 * 1024
ALLOWED_REQUEST_HEADERS = "Content-Type, x-api-key, anthropic-version"


@dataclass(frozen=True)
class RelayConfig:
    upstream: str
    allowed_origin: str
    allow_no_origin: bool


def cors_headers(origin: str | None, config: RelayConfig, private_network: bool = False) -> dict[str, str]:
    if origin != config.allowed_origin:
        return {}
    headers = {
        "Access-Control-Allow-Origin": config.allowed_origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": ALLOWED_REQUEST_HEADERS,
        "Access-Control-Max-Age": "3600",
        "Vary": "Origin, Access-Control-Request-Headers, Access-Control-Request-Private-Network",
    }
    if private_network:
        headers["Access-Control-Allow-Private-Network"] = "true"
    return headers


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "CaseLensRelay/1.0"
    config: RelayConfig

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin == self.config.allowed_origin or (origin is None and self.config.allow_no_origin)

    def _send_headers(self, status: int, content_type: str, content_length: int = 0) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        private_network = self.headers.get("Access-Control-Request-Private-Network", "").lower() == "true"
        for key, value in cors_headers(self.headers.get("Origin"), self.config, private_network).items():
            self.send_header(key, value)
        self.end_headers()

    def _send_json(self, status: int, message: str) -> None:
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self._send_headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/health":
            self._send_json(404, "not found")
            return
        body = b'{"status":"ok"}'
        self._send_headers(200, "application/json", len(body))
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/v1/messages":
            self._send_json(404, "not found")
            return
        if not self._origin_allowed():
            self._send_json(403, "origin is not allowed")
            return
        self._send_headers(204, "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/v1/messages":
            self._send_json(404, "only /v1/messages is supported")
            return
        if not self._origin_allowed():
            self._send_json(403, "origin is not allowed")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, "invalid content length")
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(413, "request body is empty or too large")
            return
        api_key = self.headers.get("x-api-key", "").strip()
        if not api_key:
            self._send_json(401, "missing x-api-key")
            return
        body = self.rfile.read(content_length)
        request = urllib.request.Request(
            self.config.upstream,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": api_key,
                "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = response.read()
                self._send_headers(response.status, response.headers.get("Content-Type", "application/json"), len(payload))
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self._send_headers(exc.code, exc.headers.get("Content-Type", "application/json"), len(payload))
            self.wfile.write(payload)
        except (urllib.error.URLError, TimeoutError) as exc:
            self._send_json(502, f"upstream request failed: {exc.reason if isinstance(exc, urllib.error.URLError) else exc}")

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a restricted local CORS relay for Case Lens.")
    parser.add_argument("--listen-host", default=os.getenv("CASE_LENS_RELAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CASE_LENS_RELAY_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--allowed-origin", default=os.getenv("CASE_LENS_ALLOWED_ORIGIN", DEFAULT_ORIGIN))
    parser.add_argument("--upstream", default=os.getenv("CASE_LENS_MODEL_UPSTREAM", DEFAULT_UPSTREAM))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    upstream = urlsplit(args.upstream)
    if upstream.scheme not in {"http", "https"} or not upstream.netloc:
        raise SystemExit("--upstream must be an absolute HTTP(S) URL")
    config = RelayConfig(
        upstream=args.upstream,
        allowed_origin=args.allowed_origin.rstrip("/"),
        allow_no_origin=args.listen_host in {"127.0.0.1", "localhost", "::1"},
    )
    RelayHandler.config = config
    server = ThreadingHTTPServer((args.listen_host, args.port), RelayHandler)
    print(f"Case Lens model relay: http://{args.listen_host}:{args.port}/v1", flush=True)
    print(f"Allowed Origin: {config.allowed_origin}", flush=True)
    print(f"Upstream: {config.upstream}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping relay.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
