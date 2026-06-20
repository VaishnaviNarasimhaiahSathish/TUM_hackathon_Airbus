"""Small standard-library HTTP API exposing the global eVTOL dashboard feed."""

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from backend.dashboard_feed import FleetDashboardFeed


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Serve read-only simulation state for the Vite/React frontend."""

    feed = FleetDashboardFeed()

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - standard library request-handler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"status": "ok", "service": "evtol-dashboard-feed"})
            return
        if parsed.path != "/api/simulation":
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        requested_tick = parse_qs(parsed.query).get("tick", [None])[0]
        try:
            tick = int(requested_tick) if requested_tick is not None else None
        except ValueError:
            self._send_json({"error": "tick must be an integer"}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json(self.feed.snapshot(tick))

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep the local development server quiet between frontend polls."""


def main() -> None:
    """Run the local dashboard API on the documented development port."""
    server = ThreadingHTTPServer(("127.0.0.1", 8000), DashboardRequestHandler)
    print("eVTOL dashboard API listening at http://127.0.0.1:8000/api/simulation")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping eVTOL dashboard API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
