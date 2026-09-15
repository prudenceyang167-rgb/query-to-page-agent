from __future__ import annotations

import copy
import io
import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app import app
from query_to_page_agent import web_workflow as flow
from query_to_page_agent.provider import ProviderError

ROOT = Path(__file__).resolve().parents[1]


def request(path, method="GET", payload=None, headers=None):
    captured = {}
    def start_response(status, headers):
        captured.update(status=status, headers=dict(headers))
    raw = json.dumps(payload or {}).encode()
    environ = {"PATH_INFO": path, "REQUEST_METHOD": method, "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw), "HTTP_HOST": "localhost", "wsgi.url_scheme": "http"}
    environ.update(headers or {})
    body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], body


class FakeModel:
    def complete_json(self, *, system, user, max_tokens):
        if "Test the connection" in user:
            return {"ok": True}
        if "priorit" in system or "strategy stage" in system:
            return json.loads((ROOT / "examples/synthetic/prioritization.json").read_text())
        data = json.loads((ROOT / "examples/synthetic/briefs.json").read_text())
        cid = json.loads(user.split("Approved cluster: ")[1].split("\nPrior pages")[0])["cluster_id"]
        return {"briefs": [b for b in data["briefs"] if b["cluster_id"] == cid]}


class WebAppTest(unittest.TestCase):
    def setUp(self):
        _, _, body = request("/api/example")
        self.inputs = json.loads(body)["inputs"]
        self.model = patch("app.get_client", return_value=FakeModel())
        self.mock_client = self.model.start()
        self.addCleanup(self.model.stop)

    def post(self, path, payload):
        status, _, body = request(path, "POST", payload)
        self.assertEqual(status, "200 OK", body.decode(errors="replace"))
        return json.loads(body)

    def analyzed(self):
        return self.post("/api/analyze", {"inputs": self.inputs})["project"]

    def approved(self, project=None):
        return self.post("/api/gate1", {"project": project or self.analyzed(), "selected_ids": ["prd-to-ui"], "reviewer": "Prudence"})["project"]

    def test_working_home_and_static_assets(self):
        status, headers, body = request("/")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b'api-key', body)
        self.assertIn(b'prudenceyang167-rgb', body)
        self.assertIn(b'target-language', body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        for path in ("/static/app.js", "/static/style.css", "/api/health"):
            self.assertEqual(request(path)[0], "200 OK")

    def test_full_workflow_and_zip(self):
        self.assertTrue(self.post("/api/test", {})["ok"])
        project = self.analyzed()
        self.assertEqual(len(project["analysis"]["clusters"]), 4)
        project = self.approved(project)
        project = self.post("/api/brief", {"project": project, "cluster_id": "prd-to-ui"})["project"]
        page = project["pages"]["prd-to-ui"]
        self.assertIn('name="robots" content="noindex,nofollow"', page["html"])
        self.assertTrue(all(check["status"] == "Not run" for check in page["qa"] if check["category"] == "Production"))
        self.assertEqual(request("/api/export", "POST", {"project": project})[0], "400 Bad Request")
        checks = {key: True for key in ("direction", "claims", "copy", "preview", "cta", "handoff_only")}
        project = self.post("/api/gate2", {"project": project, "reviewer": "Prudence", "checks": checks})["project"]
        status, headers, body = request("/api/export", "POST", {"project": project})
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIn("pages/prd-to-ui/preview.html", archive.namelist())
            self.assertIn("page-skill-handoff.md", archive.namelist())
            self.assertIn(b"NOT RUN", archive.read("page-skill-handoff.md"))

    def test_missing_gate_and_input_change_block_generation(self):
        project = self.analyzed()
        self.assertEqual(request("/api/brief", "POST", {"project": project, "cluster_id": "prd-to-ui"})[0], "400 Bad Request")
        project = self.approved(project)
        project["inputs"]["product_capabilities"] += "\nchanged facts"
        self.assertEqual(request("/api/brief", "POST", {"project": project, "cluster_id": "prd-to-ui"})[0], "400 Bad Request")

    def test_gate2_requires_named_review_all_checks_and_fails_block(self):
        project = self.post("/api/brief", {"project": self.approved(), "cluster_id": "prd-to-ui"})["project"]
        self.assertEqual(request("/api/gate2", "POST", {"project": project, "reviewer": "Prudence", "checks": {}})[0], "400 Bad Request")
        checks = {key: True for key in ("direction", "claims", "copy", "preview", "cta", "handoff_only")}
        self.assertEqual(request("/api/gate2", "POST", {"project": project, "reviewer": "", "checks": checks})[0], "400 Bad Request")
        brief = copy.deepcopy(project["pages"]["prd-to-ui"]["brief"])
        brief["conversion"]["primary_cta"]["destination"] = "javascript:alert(1)"
        status, _, body = request("/api/render", "POST", {"project": project, "cluster_id": "prd-to-ui", "brief": brief})
        # Validators may reject unsafe destinations before the QA layer.
        if status == "200 OK":
            failed_project = json.loads(body)["project"]
            self.assertEqual(request("/api/gate2", "POST", {"project": failed_project, "reviewer": "Prudence", "checks": checks})[0], "400 Bad Request")
        else:
            self.assertEqual(status, "400 Bad Request")

    def test_edit_invalidates_approval_and_escapes_html(self):
        project = self.post("/api/brief", {"project": self.approved(), "cluster_id": "prd-to-ui"})["project"]
        checks = {key: True for key in ("direction", "claims", "copy", "preview", "cta", "handoff_only")}
        project = self.post("/api/gate2", {"project": project, "reviewer": "Prudence", "checks": checks})["project"]
        brief = copy.deepcopy(project["pages"]["prd-to-ui"]["brief"])
        brief["search_metadata"]["h1"] = '<img src=x onerror="alert(1)">'
        project = self.post("/api/render", {"project": project, "cluster_id": "prd-to-ui", "brief": brief})["project"]
        self.assertIsNone(project["gate2"])
        self.assertNotIn('<img src=x', project["pages"]["prd-to-ui"]["html"])
        self.assertIn('&lt;img', project["pages"]["prd-to-ui"]["html"])
        self.assertEqual(request("/api/export", "POST", {"project": project})[0], "400 Bad Request")

    def test_language_and_untrusted_import_html(self):
        self.inputs["target_language"] = "ja-JP"
        project = self.post("/api/brief", {"project": self.approved(), "cluster_id": "prd-to-ui"})["project"]
        self.assertIn('lang="ja-JP"', project["pages"]["prd-to-ui"]["html"])
        project["pages"]["prd-to-ui"]["html"] = '<script>steal()</script>'
        imported = self.post("/api/import", {"project": project})["project"]
        self.assertNotIn('steal()', imported["pages"]["prd-to-ui"]["html"])

    def test_server_key_requires_protection_and_byok_does_not_persist(self):
        self.model.stop()
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret-server-key", "APP_ACCESS_TOKEN": ""}, clear=True):
            status, _, body = request("/api/test", "POST", {})
            self.assertEqual(status, "400 Bad Request")
            self.assertNotIn(b'secret-server-key', body)
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret-server-key", "APP_ACCESS_TOKEN": "access"}, clear=True), patch("app.DeepSeekClient", return_value=FakeModel()) as client:
            self.assertTrue(self.post("/api/test", {"api_key": "user-key"})["ok"])
            self.assertEqual(client.call_args.kwargs["api_key"], "user-key")
            status, _, body = request("/api/test", "POST", {}, {"HTTP_AUTHORIZATION": "Bearer access"})
            self.assertEqual(status, "200 OK")
            self.assertEqual(client.call_args.kwargs["api_key"], "secret-server-key")
            self.assertNotIn(b'secret-server-key', body)

    def test_invalid_size_origin_and_provider_error_do_not_leak(self):
        self.assertEqual(request("/api/analyze", "POST", {}, {"CONTENT_LENGTH": "3000000"})[0], "413 Payload Too Large")
        self.assertEqual(request("/api/test", "POST", {}, {"HTTP_ORIGIN": "https://evil.example"})[0], "403 Forbidden")
        self.mock_client.return_value.complete_json = lambda **kwargs: (_ for _ in ()).throw(ProviderError("secret-private-input 401"))
        status, _, body = request("/api/test", "POST", {})
        self.assertEqual(status, "502 Bad Gateway")
        self.assertNotIn(b'secret-private-input', body)

    def test_upstream_csv_input_and_query_coverage(self):
        self.assertEqual(flow.queries_from("Market,Language,Query,Cluster\nUS,en,ai ui builder,ui\n"), ["ai ui builder"])
        with self.assertRaises(flow.WebError):
            flow.queries_from("one\n" * 301 + "\n".join(f"query {i}" for i in range(301)))
        self.mock_client.return_value.complete_json = lambda **kwargs: {"clusters": []}
        self.assertEqual(request("/api/analyze", "POST", {"inputs": self.inputs})[0], "400 Bad Request")


if __name__ == "__main__":
    unittest.main()
