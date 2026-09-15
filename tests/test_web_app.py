from __future__ import annotations

import json
import unittest

from app import app


def request(path: str, method: str = "GET") -> tuple[str, dict[str, str], bytes]:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(app({"PATH_INFO": path, "REQUEST_METHOD": method}, start_response))
    return str(captured["status"]), captured["headers"], body  # type: ignore[return-value]


class WebAppTest(unittest.TestCase):
    def test_homepage_is_a_portfolio_page(self) -> None:
        status, headers, body = request("/")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Query-to-Page Agent", body)
        self.assertIn(b"Run synthetic demo", body)

    def test_health_endpoint(self) -> None:
        status, _, body = request("/api/health")
        self.assertEqual(status, "200 OK")
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_demo_endpoint_contains_three_selected_pages(self) -> None:
        status, _, body = request("/api/demo")
        self.assertEqual(status, "200 OK")
        clusters = json.loads(body)["clusters"]
        self.assertEqual(sum(item["selected"] for item in clusters), 3)

    def test_unknown_route_and_method_are_rejected(self) -> None:
        self.assertEqual(request("/missing")[0], "404 Not Found")
        self.assertEqual(request("/", method="POST")[0], "405 Method Not Allowed")


if __name__ == "__main__":
    unittest.main()
