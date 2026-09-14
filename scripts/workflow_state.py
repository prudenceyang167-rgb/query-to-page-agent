#!/usr/bin/env python3
"""Enforce the two human gates for a query-to-page batch run."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_INPUTS = {
    "icp",
    "query_bank",
    "product_capabilities",
    "sitemap",
    "use_case_taxonomy",
    "page_skill",
    "design_system",
    "seo_rules",
}
REQUIRED_CLUSTER_FIELDS = {
    "cluster_id",
    "cluster_label",
    "primary_query",
    "member_queries",
    "icp",
    "search_intent",
    "funnel_stage",
    "icp_relevance",
    "commercial_intent",
    "product_evidence",
    "existing_page",
    "coverage",
    "cannibalization_risk",
    "recommendation",
    "priority",
    "rationale",
    "evidence",
    "selected",
}
REQUIRED_PAGE_FIELDS = {
    "page_id",
    "cluster_id",
    "target_query",
    "page_type",
    "action",
    "route",
    "existing_page",
    "brief_path",
    "implementation_paths",
    "preview_url",
}
ALLOWED_RECOMMENDATIONS = {
    "optimize-existing",
    "create-use-case",
    "create-comparison",
    "create-landing",
    "create-blog",
}
ALLOWED_QA_STATUSES = {"Pass", "Warning", "Fail", "Not run"}
REQUIRED_QA_CHECKS = {
    ("seo", "title"),
    ("seo", "meta-description"),
    ("seo", "headings"),
    ("seo", "canonical"),
    ("seo", "internal-links"),
    ("seo", "schema"),
    ("seo", "query-coverage"),
    ("seo", "duplicate-content"),
    ("product-conversion", "cta"),
    ("product-conversion", "signup-path"),
    ("product-conversion", "core-value-proposition"),
    ("product-conversion", "use-case-clarity"),
    ("engineering", "mobile"),
    ("engineering", "component-reuse"),
    ("engineering", "build"),
    ("engineering", "type-check"),
    ("engineering", "ci"),
    ("engineering", "performance"),
}


class WorkflowError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowError(f"File does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def require_fields(item: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields.difference(item))
    if missing:
        raise WorkflowError(f"{label} is missing fields: {', '.join(missing)}")


def artifact_ref(path: Path, run_dir: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(run_dir.resolve()))
    except ValueError:
        return str(resolved)


def state_path(run_dir: Path) -> Path:
    return run_dir / "state.json"


def load_state(run_dir: Path) -> dict[str, Any]:
    return load_json(state_path(run_dir))


def save_state(run_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    write_json(state_path(run_dir), state)


def validate_config(config: dict[str, Any], config_path: Path) -> dict[str, str]:
    require_fields(config, {"run_name", "batch_size", "target_repository", "inputs"}, "config")
    batch_size = config["batch_size"]
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 3 <= batch_size <= 5:
        raise WorkflowError("config.batch_size must be an integer from 3 to 5")
    if not isinstance(config["inputs"], dict):
        raise WorkflowError("config.inputs must be an object")
    missing = sorted(REQUIRED_INPUTS.difference(config["inputs"]))
    if missing:
        raise WorkflowError(f"config.inputs is missing: {', '.join(missing)}")

    base = config_path.resolve().parent
    resolved: dict[str, str] = {}
    for name in sorted(REQUIRED_INPUTS):
        raw = config["inputs"][name]
        if not isinstance(raw, str) or not raw.strip():
            raise WorkflowError(f"config.inputs.{name} must be a non-empty path")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate
        if not candidate.exists():
            raise WorkflowError(f"Input path does not exist ({name}): {candidate.resolve()}")
        resolved[name] = str(candidate.resolve())

    repository = Path(str(config["target_repository"])).expanduser()
    if not repository.is_absolute():
        repository = base / repository
    if not repository.is_dir():
        raise WorkflowError(f"Target repository does not exist: {repository.resolve()}")
    resolved["target_repository"] = str(repository.resolve())
    return resolved


def init_run(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config)
    config = load_json(config_path)
    resolved = validate_config(config, config_path)
    run_dir = Path(args.run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise WorkflowError(f"Refusing to overwrite non-empty run directory: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "briefs").mkdir(exist_ok=True)
    (run_dir / "qa").mkdir(exist_ok=True)
    stored_config = dict(config)
    stored_config["resolved"] = resolved
    write_json(run_dir / "config.json", stored_config)
    created = now_iso()
    state = {
        "schema_version": 1,
        "run_name": config["run_name"],
        "batch_size": config["batch_size"],
        "stage": "query_prioritization",
        "created_at": created,
        "updated_at": created,
        "artifacts": {},
        "approved_cluster_ids": [],
        "page_ids": [],
        "qa_blockers": [],
        "gates": {
            "gate_1": {"status": "Locked", "history": []},
            "gate_2": {"status": "Locked", "history": []},
        },
    }
    write_json(state_path(run_dir), state)
    return state


def validate_analysis(analysis: dict[str, Any], batch_size: int) -> list[str]:
    clusters = analysis.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        raise WorkflowError("prioritization must contain a non-empty clusters array")
    selected: list[str] = []
    all_ids: set[str] = set()
    for index, cluster in enumerate(clusters):
        if not isinstance(cluster, dict):
            raise WorkflowError(f"clusters[{index}] must be an object")
        require_fields(cluster, REQUIRED_CLUSTER_FIELDS, f"clusters[{index}]")
        cluster_id = cluster["cluster_id"]
        if not isinstance(cluster_id, str) or not cluster_id:
            raise WorkflowError(f"clusters[{index}].cluster_id must be a non-empty string")
        if cluster_id in all_ids:
            raise WorkflowError(f"Duplicate cluster_id: {cluster_id}")
        all_ids.add(cluster_id)
        if cluster["recommendation"] not in ALLOWED_RECOMMENDATIONS:
            raise WorkflowError(f"Invalid recommendation for {cluster_id}: {cluster['recommendation']}")
        if cluster["priority"] not in {"P0", "P1", "P2"}:
            raise WorkflowError(f"Invalid priority for {cluster_id}: {cluster['priority']}")
        if cluster["funnel_stage"] not in {"awareness", "consideration", "decision"}:
            raise WorkflowError(f"Invalid funnel stage for {cluster_id}: {cluster['funnel_stage']}")
        if cluster["coverage"] not in {"none", "partial", "strong"}:
            raise WorkflowError(f"Invalid coverage for {cluster_id}: {cluster['coverage']}")
        if cluster["cannibalization_risk"] not in {"low", "medium", "high"}:
            raise WorkflowError(
                f"Invalid cannibalization risk for {cluster_id}: {cluster['cannibalization_risk']}"
            )
        if not isinstance(cluster["member_queries"], list) or not cluster["member_queries"]:
            raise WorkflowError(f"{cluster_id}.member_queries must be a non-empty array")
        if not isinstance(cluster["evidence"], list):
            raise WorkflowError(f"{cluster_id}.evidence must be an array")
        for field in ("icp_relevance", "commercial_intent", "product_evidence"):
            rating = cluster[field]
            if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
                raise WorkflowError(f"{cluster_id}.{field} must be an integer from 1 to 5")
        if cluster["selected"] is True:
            if cluster["priority"] != "P0":
                raise WorkflowError(f"Selected cluster must be P0: {cluster_id}")
            selected.append(cluster_id)
        elif cluster["selected"] is not False:
            raise WorkflowError(f"{cluster_id}.selected must be true or false")
    if len(selected) != batch_size:
        raise WorkflowError(
            f"Expected exactly {batch_size} selected clusters, found {len(selected)}"
        )
    return selected


def record_analysis(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    if state["stage"] not in {"query_prioritization", "gate_1_review"}:
        raise WorkflowError(f"Cannot record analysis during stage: {state['stage']}")
    analysis_path = Path(args.analysis)
    analysis = load_json(analysis_path)
    selected = validate_analysis(analysis, state["batch_size"])
    state["artifacts"]["prioritization"] = artifact_ref(analysis_path, run_dir)
    state["proposed_cluster_ids"] = selected
    state["approved_cluster_ids"] = []
    state["stage"] = "gate_1_review"
    state["gates"]["gate_1"]["status"] = "Pending"
    state["gates"]["gate_2"] = {"status": "Locked", "history": []}
    save_state(run_dir, state)
    return state


def validate_page_manifest(manifest: dict[str, Any], approved: set[str]) -> list[str]:
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        raise WorkflowError("page manifest must contain a non-empty pages array")
    page_ids: list[str] = []
    cluster_ids: set[str] = set()
    routes: set[str] = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise WorkflowError(f"pages[{index}] must be an object")
        require_fields(page, REQUIRED_PAGE_FIELDS, f"pages[{index}]")
        page_id = page["page_id"]
        cluster_id = page["cluster_id"]
        route = page["route"]
        if not all(isinstance(value, str) and value for value in (page_id, cluster_id, route)):
            raise WorkflowError(f"pages[{index}] requires non-empty page_id, cluster_id, and route")
        if page_id in page_ids:
            raise WorkflowError(f"Duplicate page_id: {page_id}")
        if cluster_id in cluster_ids:
            raise WorkflowError(f"Duplicate cluster_id in page manifest: {cluster_id}")
        if route in routes:
            raise WorkflowError(f"Duplicate route in page manifest: {route}")
        page_ids.append(page_id)
        cluster_ids.add(cluster_id)
        routes.add(route)
    if cluster_ids != approved:
        raise WorkflowError(
            "Page manifest cluster IDs must exactly match Gate 1 approval: "
            f"approved={sorted(approved)}, manifest={sorted(cluster_ids)}"
        )
    return page_ids


def record_pages(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    if state["gates"]["gate_1"]["status"] != "Approved":
        raise WorkflowError("Gate 1 must be approved before recording pages")
    manifest_path = Path(args.manifest)
    page_ids = validate_page_manifest(
        load_json(manifest_path), set(state["approved_cluster_ids"])
    )
    state["artifacts"]["page_manifest"] = artifact_ref(manifest_path, run_dir)
    state["page_ids"] = page_ids
    state["stage"] = "implementation"
    save_state(run_dir, state)
    return state


def validate_qa(report: dict[str, Any], expected_pages: set[str]) -> list[str]:
    pages = report.get("pages")
    if not isinstance(pages, list) or not pages:
        raise WorkflowError("QA report must contain a non-empty pages array")
    reported: set[str] = set()
    blockers: list[str] = []
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict) or not isinstance(page.get("page_id"), str):
            raise WorkflowError(f"QA pages[{page_index}] requires page_id")
        page_id = page["page_id"]
        if page_id in reported:
            raise WorkflowError(f"Duplicate QA page_id: {page_id}")
        reported.add(page_id)
        checks = page.get("checks")
        if not isinstance(checks, list) or not checks:
            raise WorkflowError(f"QA page {page_id} requires checks")
        seen_checks: set[tuple[str, str]] = set()
        for check_index, check in enumerate(checks):
            if not isinstance(check, dict):
                raise WorkflowError(f"{page_id}.checks[{check_index}] must be an object")
            require_fields(check, {"category", "name", "status", "evidence"}, f"{page_id}.checks[{check_index}]")
            status = check["status"]
            if status not in ALLOWED_QA_STATUSES:
                raise WorkflowError(f"Invalid QA status for {page_id}/{check['name']}: {status}")
            key = (check["category"], check["name"])
            if key in seen_checks:
                raise WorkflowError(f"Duplicate QA check for {page_id}: {key[0]}/{key[1]}")
            seen_checks.add(key)
            if status == "Fail" or (status == "Not run" and check.get("required", True)):
                blockers.append(f"{page_id}:{check['category']}:{check['name']}:{status}")
        for category, name in sorted(REQUIRED_QA_CHECKS.difference(seen_checks)):
            blockers.append(f"{page_id}:{category}:{name}:Not run")
    if reported != expected_pages:
        raise WorkflowError(
            "QA page IDs must exactly match the page manifest: "
            f"expected={sorted(expected_pages)}, report={sorted(reported)}"
        )
    return blockers


def record_qa(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    if state["gates"]["gate_1"]["status"] != "Approved" or not state["page_ids"]:
        raise WorkflowError("Approved Gate 1 and a page manifest are required before QA")
    if state["stage"] not in {"implementation", "qa", "gate_2_review"}:
        raise WorkflowError(f"Cannot record QA during stage: {state['stage']}")
    report_path = Path(args.report)
    blockers = validate_qa(load_json(report_path), set(state["page_ids"]))
    state["artifacts"]["qa_report"] = artifact_ref(report_path, run_dir)
    state["qa_blockers"] = blockers
    state["stage"] = "gate_2_review"
    state["gates"]["gate_2"]["status"] = "Pending"
    save_state(run_dir, state)
    return state


def decide_gate(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    reviewer = args.reviewer.strip()
    if not reviewer or reviewer.casefold() == "agent":
        raise WorkflowError("A named human reviewer is required")
    gate_key = f"gate_{args.gate}"
    gate = state["gates"][gate_key]
    if gate["status"] != "Pending":
        raise WorkflowError(f"Gate {args.gate} is not pending; current status is {gate['status']}")
    approved = args.decision == "approve"
    if args.gate == 2 and approved and state["qa_blockers"]:
        raise WorkflowError("Gate 2 cannot be approved while QA blockers remain")
    entry = {
        "decision": "Approved" if approved else "Rejected",
        "reviewer": reviewer,
        "timestamp": now_iso(),
        "notes": args.notes or "",
    }
    if args.gate == 1:
        entry["scope"] = list(state.get("proposed_cluster_ids", []))
        gate["history"].append(entry)
        gate["status"] = entry["decision"]
        if approved:
            state["approved_cluster_ids"] = list(state["proposed_cluster_ids"])
            state["stage"] = "briefing"
        else:
            state["approved_cluster_ids"] = []
            state["stage"] = "query_prioritization"
    else:
        entry["scope"] = list(state["page_ids"])
        entry["warnings_accepted"] = args.warnings_accepted or []
        gate["history"].append(entry)
        gate["status"] = entry["decision"]
        state["stage"] = "pr_ready" if approved else "qa"
    save_state(run_dir, state)
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a new MVP run")
    init_parser.add_argument("--config", required=True)
    init_parser.add_argument("--run-dir", required=True)
    init_parser.set_defaults(handler=init_run)

    analysis_parser = subparsers.add_parser("record-analysis", help="Validate prioritization and open Gate 1")
    analysis_parser.add_argument("--run-dir", required=True)
    analysis_parser.add_argument("--analysis", required=True)
    analysis_parser.set_defaults(handler=record_analysis)

    page_parser = subparsers.add_parser("record-pages", help="Validate the approved page manifest")
    page_parser.add_argument("--run-dir", required=True)
    page_parser.add_argument("--manifest", required=True)
    page_parser.set_defaults(handler=record_pages)

    qa_parser = subparsers.add_parser("record-qa", help="Validate QA evidence and open Gate 2")
    qa_parser.add_argument("--run-dir", required=True)
    qa_parser.add_argument("--report", required=True)
    qa_parser.set_defaults(handler=record_qa)

    gate_parser = subparsers.add_parser("gate", help="Record a human gate decision")
    gate_parser.add_argument("--run-dir", required=True)
    gate_parser.add_argument("--gate", type=int, choices=(1, 2), required=True)
    gate_parser.add_argument("--decision", choices=("approve", "reject"), required=True)
    gate_parser.add_argument("--reviewer", required=True)
    gate_parser.add_argument("--notes")
    gate_parser.add_argument("--warnings-accepted", nargs="*")
    gate_parser.set_defaults(handler=decide_gate)

    status_parser = subparsers.add_parser("status", help="Print current workflow state")
    status_parser.add_argument("--run-dir", required=True)
    status_parser.set_defaults(handler=lambda args: load_state(Path(args.run_dir)))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except WorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
