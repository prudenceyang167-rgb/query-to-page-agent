from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "workflow_state.py"
SPEC = importlib.util.spec_from_file_location("workflow_state", SCRIPT)
assert SPEC and SPEC.loader
WORKFLOW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKFLOW)


class WorkflowStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        inputs = self.base / "inputs"
        inputs.mkdir()
        for name in (
            "icp.md",
            "query-bank.csv",
            "product-capabilities.md",
            "sitemap.csv",
            "use-cases.md",
            "page-skill.md",
            "design-system.md",
            "seo-rules.md",
        ):
            (inputs / name).write_text("synthetic\n", encoding="utf-8")
        config = {
            "run_name": "test-run",
            "batch_size": 3,
            "target_repository": ".",
            "inputs": {
                "icp": "inputs/icp.md",
                "query_bank": "inputs/query-bank.csv",
                "product_capabilities": "inputs/product-capabilities.md",
                "sitemap": "inputs/sitemap.csv",
                "use_case_taxonomy": "inputs/use-cases.md",
                "page_skill": "inputs/page-skill.md",
                "design_system": "inputs/design-system.md",
                "seo_rules": "inputs/seo-rules.md",
            },
        }
        self.config = self.base / "config.json"
        self.config.write_text(json.dumps(config), encoding="utf-8")
        self.run_dir = self.base / "run"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def call(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if ok and result.returncode != 0:
            self.fail(result.stderr)
        return result

    def write_analysis(self, selected: int = 3) -> Path:
        clusters = []
        for index in range(4):
            clusters.append(
                {
                    "cluster_id": f"c{index + 1}",
                    "cluster_label": f"Cluster {index + 1}",
                    "primary_query": f"query {index + 1}",
                    "member_queries": [f"query {index + 1}"],
                    "icp": "Product team",
                    "search_intent": "commercial",
                    "funnel_stage": "decision",
                    "icp_relevance": 5,
                    "commercial_intent": 5,
                    "product_evidence": 4,
                    "existing_page": "",
                    "coverage": "none",
                    "cannibalization_risk": "low",
                    "recommendation": "create-use-case",
                    "priority": "P0" if index < selected else "P1",
                    "rationale": "Synthetic test",
                    "evidence": ["fixture"],
                    "selected": index < selected,
                }
            )
        path = self.base / "prioritization.json"
        path.write_text(json.dumps({"clusters": clusters}), encoding="utf-8")
        return path

    def initialize(self) -> None:
        self.call("init", "--config", str(self.config), "--run-dir", str(self.run_dir))

    def _reach_pr_ready(self) -> None:
        self.initialize()
        analysis = self.write_analysis()
        self.call("record-analysis", "--run-dir", str(self.run_dir), "--analysis", str(analysis))
        self.call(
            "gate",
            "--run-dir",
            str(self.run_dir),
            "--gate",
            "1",
            "--decision",
            "approve",
            "--reviewer",
            "Portfolio owner",
        )
        pages = {
            "pages": [
                {
                    "page_id": f"p{index}",
                    "cluster_id": f"c{index}",
                    "target_query": f"query {index}",
                    "page_type": "use-case",
                    "action": "create-use-case",
                    "route": f"/use-cases/p{index}",
                    "existing_page": "",
                    "brief_path": f"briefs/p{index}.md",
                    "implementation_paths": [f"routes/p{index}.tsx"],
                    "preview_url": f"http://localhost/p{index}",
                }
                for index in range(1, 4)
            ]
        }
        manifest = self.base / "page-manifest.json"
        manifest.write_text(json.dumps(pages), encoding="utf-8")
        self.call("record-pages", "--run-dir", str(self.run_dir), "--manifest", str(manifest))
        report = {
            "pages": [
                {
                    "page_id": f"p{index}",
                    "checks": [
                        {
                            "category": category,
                            "name": name,
                            "status": "Pass",
                            "evidence": "fixture",
                        }
                        for category, name in sorted(WORKFLOW.REQUIRED_QA_CHECKS)
                    ],
                }
                for index in range(1, 4)
            ]
        }
        qa = self.base / "qa.json"
        qa.write_text(json.dumps(report), encoding="utf-8")
        self.call("record-qa", "--run-dir", str(self.run_dir), "--report", str(qa))
        result = self.call(
            "gate",
            "--run-dir",
            str(self.run_dir),
            "--gate",
            "2",
            "--decision",
            "approve",
            "--reviewer",
            "Portfolio owner",
        )
        self.assertEqual(json.loads(result.stdout)["stage"], "pr_ready")

    def test_happy_path_reaches_pr_ready(self) -> None:
        self._reach_pr_ready()

    def test_gate_1_cannot_open_without_analysis(self) -> None:
        self.initialize()
        result = self.call(
            "gate",
            "--run-dir",
            str(self.run_dir),
            "--gate",
            "1",
            "--decision",
            "approve",
            "--reviewer",
            "Portfolio owner",
            ok=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("not pending", result.stderr)

    def test_selected_count_must_match_batch(self) -> None:
        self.initialize()
        analysis = self.write_analysis(selected=2)
        result = self.call(
            "record-analysis",
            "--run-dir",
            str(self.run_dir),
            "--analysis",
            str(analysis),
            ok=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Expected exactly 3", result.stderr)

    def test_missing_or_failed_required_qa_blocks_gate_2(self) -> None:
        report = {
            "pages": [
                {
                    "page_id": "p1",
                    "checks": [
                        {
                            "category": "engineering",
                            "name": "build",
                            "status": "Fail",
                            "evidence": "fixture failure",
                        }
                    ],
                }
            ]
        }
        blockers = WORKFLOW.validate_qa(report, {"p1"})
        self.assertIn("p1:engineering:build:Fail", blockers)
        self.assertIn("p1:seo:title:Not run", blockers)

    def test_mandatory_checks_cannot_be_marked_optional(self) -> None:
        checks = [
            {"category": category, "name": name, "status": "Not run", "evidence": "", "required": False}
            for category, name in WORKFLOW.REQUIRED_QA_CHECKS
        ]
        blockers = WORKFLOW.validate_qa({"pages": [{"page_id": "p1", "checks": checks}]}, {"p1"})
        self.assertEqual(len(blockers), len(WORKFLOW.REQUIRED_QA_CHECKS))
        checks[0]["status"] = "Pass"
        blockers = WORKFLOW.validate_qa({"pages": [{"page_id": "p1", "checks": checks}]}, {"p1"})
        self.assertTrue(any(item.endswith(":Missing evidence") for item in blockers))

    def test_query_coverage_rejects_missing_and_duplicate_members(self) -> None:
        analysis = json.loads(self.write_analysis().read_text())
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "every input query"):
            WORKFLOW.validate_analysis(analysis, 3, {"query 1", "query 2", "query 3", "query 4", "missing"})
        analysis["clusters"][1]["member_queries"].append("QUERY 1")
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "more than once"):
            WORKFLOW.validate_analysis(analysis, 3)

    def test_pending_gate_rejects_changed_review_contents(self) -> None:
        self.initialize()
        analysis = self.write_analysis()
        self.call("record-analysis", "--run-dir", str(self.run_dir), "--analysis", str(analysis))
        value = json.loads(analysis.read_text())
        value["clusters"][0]["rationale"] = "Changed while awaiting review"
        analysis.write_text(json.dumps(value))
        result = self.call("gate", "--run-dir", str(self.run_dir), "--gate", "1", "--decision", "approve", "--reviewer", "Portfolio owner", ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("review contents changed", result.stderr)

    def test_manifest_replacement_invalidates_release_approval(self) -> None:
        self._reach_pr_ready()
        self.call("record-pages", "--run-dir", str(self.run_dir), "--manifest", str(self.base / "page-manifest.json"))
        state = json.loads(self.call("status", "--run-dir", str(self.run_dir)).stdout)
        self.assertEqual(state["gates"]["gate_2"]["status"], "Locked")
        self.assertEqual(state["stage"], "implementation")

    def test_post_approval_file_edit_invalidates_release(self) -> None:
        self._reach_pr_ready()
        manifest_path = self.base / "page-manifest.json"
        value = json.loads(manifest_path.read_text())
        value["pages"][0]["preview_url"] = "https://different-preview.example"
        manifest_path.write_text(json.dumps(value))
        state = json.loads(self.call("status", "--run-dir", str(self.run_dir)).stdout)
        self.assertEqual(state["gates"]["gate_2"]["status"], "Locked")
        self.assertEqual(state["stage"], "implementation")

    def test_qa_cannot_approve_a_changed_mapping(self) -> None:
        self._reach_pr_ready()
        manifest_path = self.base / "page-manifest.json"
        value = json.loads(manifest_path.read_text())
        value["pages"][0]["action"] = "create-blog"
        value["pages"][0]["page_type"] = "blog"
        manifest_path.write_text(json.dumps(value))
        result = self.call("record-qa", "--run-dir", str(self.run_dir), "--report", str(self.base / "qa.json"), ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("approved recommendation", result.stderr)


if __name__ == "__main__":
    unittest.main()
