from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from query_to_page_agent.pipeline import PipelineError, analyze, generate_briefs, read_source, run_qa, validate_briefs
from query_to_page_agent.provider import FixtureClient
from scripts import workflow_state as workflow


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic"


class StaticModel:
    def __init__(self, value: dict) -> None:
        self.value = value

    def complete_json(self, **_: object) -> dict:
        return json.loads(json.dumps(self.value))


def qa_fixture(page_ids: list[str]) -> dict:
    pages = []
    for page_id in page_ids:
        pages.append(
            {
                "page_id": page_id,
                "checks": [
                    {
                        "category": category,
                        "name": name,
                        "status": "Warning",
                        "evidence": "Synthetic review evidence",
                        "owner": "agent",
                        "remediation": "Verify in a rendered preview",
                        "required": True,
                    }
                    for category, name in sorted(workflow.REQUIRED_QA_CHECKS)
                ],
            }
        )
    return {"pages": pages}


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp.name) / "run"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def approve_gate_1(self) -> None:
        workflow.decide_gate(
            argparse.Namespace(
                run_dir=str(self.run_dir),
                gate=1,
                decision="approve",
                reviewer="Portfolio owner",
                notes="Synthetic approval",
                warnings_accepted=None,
            )
        )

    def test_analysis_and_brief_generation(self) -> None:
        state = analyze(
            EXAMPLE / "config.json",
            self.run_dir,
            FixtureClient(EXAMPLE / "prioritization.json"),
        )
        self.assertEqual(state["stage"], "gate_1_review")
        self.assertTrue((self.run_dir / "gate-1.md").exists())
        self.approve_gate_1()
        state = generate_briefs(
            self.run_dir,
            FixtureClient(EXAMPLE / "briefs.json"),
        )
        self.assertEqual(state["stage"], "page_generation")
        manifest = workflow.load_json(self.run_dir / "page-manifest.draft.json")
        self.assertTrue(manifest["draft"])
        self.assertEqual(len(manifest["pages"]), 3)
        self.assertTrue((self.run_dir / "briefs" / "prd-to-ui.md").exists())

    def test_source_loader_redacts_common_secrets(self) -> None:
        source = Path(self.temp.name) / "input.md"
        source.write_text(
            "api_key=should-not-leave\nAuthorization: Bearer private-token\n",
            encoding="utf-8",
        )
        loaded = read_source(source)
        self.assertNotIn("should-not-leave", loaded)
        self.assertNotIn("private-token", loaded)
        self.assertEqual(loaded.count("[REDACTED]"), 2)

    def test_briefs_require_human_gate(self) -> None:
        analyze(
            EXAMPLE / "config.json",
            self.run_dir,
            FixtureClient(EXAMPLE / "prioritization.json"),
        )
        with self.assertRaisesRegex(PipelineError, "Gate 1"):
            generate_briefs(self.run_dir, FixtureClient(EXAMPLE / "briefs.json"))

    def test_qa_refuses_draft_manifest(self) -> None:
        analyze(
            EXAMPLE / "config.json",
            self.run_dir,
            FixtureClient(EXAMPLE / "prioritization.json"),
        )
        self.approve_gate_1()
        generate_briefs(self.run_dir, FixtureClient(EXAMPLE / "briefs.json"))
        with self.assertRaisesRegex(PipelineError, "draft manifest"):
            run_qa(
                self.run_dir,
                self.run_dir / "page-manifest.draft.json",
                StaticModel(qa_fixture(["prd-to-ui", "prd-to-prototype", "requirements-analysis"])),
            )

    def test_qa_opens_gate_2_and_keeps_missing_commands_blocking(self) -> None:
        analyze(
            EXAMPLE / "config.json",
            self.run_dir,
            FixtureClient(EXAMPLE / "prioritization.json"),
        )
        self.approve_gate_1()
        generate_briefs(self.run_dir, FixtureClient(EXAMPLE / "briefs.json"))
        manifest = workflow.load_json(self.run_dir / "page-manifest.draft.json")
        manifest.pop("draft")
        manifest.pop("instructions")
        for page in manifest["pages"]:
            page["preview_url"] = f"http://localhost/{page['page_id']}"
        manifest_path = self.run_dir / "page-manifest.json"
        workflow.write_json(manifest_path, manifest)
        state = run_qa(
            self.run_dir,
            manifest_path,
            StaticModel(qa_fixture(["prd-to-ui", "prd-to-prototype", "requirements-analysis"])),
        )
        self.assertEqual(state["stage"], "gate_2_review")
        self.assertEqual(state["gates"]["gate_2"]["status"], "Pending")
        self.assertIn("prd-to-ui:engineering:build:Not run", state["qa_blockers"])
        self.assertTrue((self.run_dir / "gate-2.md").exists())

    def test_brief_rejects_path_escape_and_malformed_nested_data(self) -> None:
        original = workflow.load_json(EXAMPLE / "briefs.json")
        approved = {item["cluster_id"] for item in original["briefs"]}
        mutations = (
            ("page_id", "../outside-run"),
            ("route", "/use-cases/%2e%2e/outside"),
            ("product_truth", None),
            ("search_metadata", []),
            ("sections", ["not an object"]),
            ("faq", [{"question": "Question", "answer": None}]),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                payload = json.loads(json.dumps(original))
                payload["briefs"][0][field] = value
                with self.assertRaises(PipelineError):
                    validate_briefs(payload, approved)

    def test_briefs_preserve_approved_action_and_existing_route(self) -> None:
        payload = workflow.load_json(EXAMPLE / "briefs.json")
        analysis = workflow.load_json(EXAMPLE / "prioritization.json")
        mapping = {item["cluster_id"]: item for item in analysis["clusters"] if item["selected"]}
        cid = payload["briefs"][0]["cluster_id"]
        mapping[cid]["recommendation"] = "optimize-existing"
        mapping[cid]["existing_page"] = "/existing-owner"
        with self.assertRaisesRegex(PipelineError, "approved recommendation"):
            validate_briefs(payload, set(mapping), mapping)
        payload["briefs"][0]["action"] = "optimize-existing"
        with self.assertRaisesRegex(PipelineError, "existing page route"):
            validate_briefs(payload, set(mapping), mapping)

    def test_source_edits_invalidate_gate_1(self) -> None:
        analyze(EXAMPLE / "config.json", self.run_dir, FixtureClient(EXAMPLE / "prioritization.json"))
        self.approve_gate_1()
        analysis = workflow.load_json(self.run_dir / "prioritization.json")
        analysis["clusters"][0]["rationale"] = "Changed after review"
        workflow.write_json(self.run_dir / "prioritization.json", analysis)
        with self.assertRaisesRegex(PipelineError, "Gate 1"):
            generate_briefs(self.run_dir, FixtureClient(EXAMPLE / "briefs.json"))
        state = workflow.load_state(self.run_dir)
        self.assertEqual(state["gates"]["gate_1"]["status"], "Locked")
        self.assertEqual(state["approved_cluster_ids"], [])


if __name__ == "__main__":
    unittest.main()
