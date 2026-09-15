#!/usr/bin/env python3
"""Enforce the two human gates for a query-to-page batch run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


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
    state = load_json(state_path(run_dir))
    changed = False
    gate_1 = state["gates"]["gate_1"]
    if gate_1["status"] == "Approved" and (
        not gate_1.get("approved_digest")
        or gate_1["approved_digest"] != review_digest(run_dir, state, 1)
    ):
        gate_1["status"] = "Locked"
        gate_1["invalidated_reason"] = "Analysis or source inputs changed; record analysis and review again."
        state["approved_cluster_ids"] = []
        state["stage"] = "query_prioritization"
        invalidate_gate_2(state)
        changed = True
    gate_2 = state["gates"]["gate_2"]
    if gate_2["status"] == "Approved" and (
        not gate_2.get("approved_digest")
        or gate_2["approved_digest"] != review_digest(run_dir, state, 2)
    ):
        invalidate_gate_2(state)
        state["stage"] = "implementation"
        changed = True
    if changed:
        save_state(run_dir, state)
    return state


def save_state(run_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    write_json(state_path(run_dir), state)


def normalized_query(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def require_safe_id(value: Any, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise WorkflowError(f"{label} must be a lowercase ASCII slug")


def route_key(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        raise WorkflowError("Page route must be a site-relative path beginning with /")
    decoded = unquote(value)
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in decoded) or any(char in decoded for char in "\\?#"):
        raise WorkflowError("Page route contains an unsafe character")
    if "//" in decoded or any(part in {".", ".."} for part in decoded.split("/")):
        raise WorkflowError("Page route must not contain traversal or empty segments")
    return decoded.rstrip("/") or "/"


def validate_mapping(page: dict[str, Any], cluster: dict[str, Any]) -> None:
    if page["action"] != cluster["recommendation"]:
        raise WorkflowError(f"{page['cluster_id']}: action differs from the approved recommendation")
    if normalized_query(page["target_query"]) != normalized_query(cluster["primary_query"]):
        raise WorkflowError(f"{page['cluster_id']}: target query differs from Gate 1 approval")
    if cluster["recommendation"] == "optimize-existing":
        existing = cluster["existing_page"]
        existing_route = urlsplit(existing).path if "://" in existing else existing
        if not existing_route or route_key(page["route"]) != route_key(existing_route):
            raise WorkflowError(f"{page['cluster_id']}: optimization must preserve the existing page route")
    else:
        expected_type = cluster["recommendation"].removeprefix("create-")
        if page["page_type"] != expected_type:
            raise WorkflowError(f"{page['cluster_id']}: page type differs from the approved recommendation")


def input_queries(config: dict[str, Any]) -> set[str] | None:
    path = Path(config["resolved"]["query_bank"])
    if path.suffix.lower() != ".csv":
        return None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = {re.sub(r"[\s-]+", "_", key.strip().casefold()): key for key in reader.fieldnames or []}
        key = next((headers[name] for name in ("query", "keyword", "search_term", "search_query", "top_queries") if name in headers), None)
        if key is None:
            return None
        return {normalized_query(row[key]) for row in reader if isinstance(row.get(key), str) and row[key].strip()}


def approved_mapping(run_dir: Path, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    analysis = load_json(run_dir / state["artifacts"]["prioritization"])
    approved = set(state["approved_cluster_ids"])
    return {item["cluster_id"]: item for item in analysis["clusters"] if item["cluster_id"] in approved}


def invalidate_gate_2(state: dict[str, Any]) -> None:
    gate = state["gates"]["gate_2"]
    gate["status"] = "Locked"
    gate.pop("approved_digest", None)
    gate.pop("review_digest", None)
    state["qa_blockers"] = []


def _digest_source(digest: Any, path: Path) -> None:
    digest.update(str(path).encode())
    if path.is_file():
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1_048_576), b""):
                digest.update(chunk)
    elif path.is_dir():
        # Match the bounded source sampling used by the pipeline, without reading secrets.
        count = 0
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(name for name in dirs if name not in {".git", "node_modules", ".next", ".build", ".runs", "dist", ".venv", "__pycache__"})
            for name in sorted(files):
                child = Path(root) / name
                if name.startswith(".env") or name in {"credentials", "credentials.json", "secrets.json", "id_ed25519", "id_rsa", ".npmrc", ".pypirc"} or child.suffix.lower() not in {".md", ".csv", ".json", ".txt", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".py", ".yaml", ".yml", ".mdx", ".scss"}:
                    continue
                _digest_source(digest, child)
                count += 1
                if count >= 80:
                    return
    else:
        digest.update(b"[missing]")


def review_digest(run_dir: Path, state: dict[str, Any], gate: int) -> str:
    digest = hashlib.sha256()
    config = load_json(run_dir / "config.json")
    _digest_source(digest, run_dir / "config.json")
    for name in sorted(REQUIRED_INPUTS):
        _digest_source(digest, Path(config["resolved"][name]))
    keys = ["prioritization"] if gate == 1 else ["prioritization", "brief_index", "page_manifest", "qa_report"]
    for key in keys:
        if state["artifacts"].get(key):
            _digest_source(digest, run_dir / state["artifacts"][key])
    if gate == 2 and state["artifacts"].get("page_manifest"):
        manifest = load_json(run_dir / state["artifacts"]["page_manifest"])
        target = Path(config["resolved"]["target_repository"])
        for page in manifest["pages"]:
            _digest_source(digest, run_dir / page["brief_path"])
            for raw in page.get("implementation_paths", []) + page.get("evidence_paths", []):
                _digest_source(digest, target / raw)
    return digest.hexdigest()


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


def validate_analysis(analysis: dict[str, Any], batch_size: int, expected_queries: set[str] | None = None) -> list[str]:
    clusters = analysis.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        raise WorkflowError("prioritization must contain a non-empty clusters array")
    selected: list[str] = []
    all_ids: set[str] = set()
    all_queries: set[str] = set()
    for index, cluster in enumerate(clusters):
        if not isinstance(cluster, dict):
            raise WorkflowError(f"clusters[{index}] must be an object")
        require_fields(cluster, REQUIRED_CLUSTER_FIELDS, f"clusters[{index}]")
        cluster_id = cluster["cluster_id"]
        require_safe_id(cluster_id, f"clusters[{index}].cluster_id")
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
        for field in ("cluster_label", "primary_query", "icp", "search_intent", "rationale"):
            if not isinstance(cluster[field], str) or not cluster[field].strip():
                raise WorkflowError(f"{cluster_id}.{field} must be non-empty text")
        if not isinstance(cluster["existing_page"], str):
            raise WorkflowError(f"{cluster_id}.existing_page must be text")
        if cluster["recommendation"] == "optimize-existing" and not cluster["existing_page"].strip():
            raise WorkflowError(f"{cluster_id}: optimize-existing requires an existing page")
        members: set[str] = set()
        for query in cluster["member_queries"]:
            if not isinstance(query, str) or not query.strip():
                raise WorkflowError(f"{cluster_id}.member_queries must contain non-empty strings")
            normalized = normalized_query(query)
            if normalized in members or normalized in all_queries:
                raise WorkflowError(f"Query occurs more than once: {query}")
            members.add(normalized)
        if normalized_query(cluster["primary_query"]) not in members:
            raise WorkflowError(f"{cluster_id}: primary query must belong to member_queries")
        all_queries.update(members)
        if not isinstance(cluster["evidence"], list) or not all(isinstance(item, str) and item.strip() for item in cluster["evidence"]):
            raise WorkflowError(f"{cluster_id}.evidence must be a string array")
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
    if expected_queries is not None and all_queries != expected_queries:
        raise WorkflowError("Analysis must cover every input query exactly once without adding queries")
    return selected


def record_analysis(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    if state["stage"] not in {"query_prioritization", "gate_1_review"}:
        raise WorkflowError(f"Cannot record analysis during stage: {state['stage']}")
    analysis_path = Path(args.analysis)
    analysis = load_json(analysis_path)
    selected = validate_analysis(analysis, state["batch_size"], input_queries(load_json(run_dir / "config.json")))
    state["artifacts"]["prioritization"] = artifact_ref(analysis_path, run_dir)
    state["proposed_cluster_ids"] = selected
    state["approved_cluster_ids"] = []
    state["stage"] = "gate_1_review"
    state["gates"]["gate_1"]["status"] = "Pending"
    state["gates"]["gate_1"]["review_digest"] = review_digest(run_dir, state, 1)
    state["gates"]["gate_1"].pop("approved_digest", None)
    invalidate_gate_2(state)
    save_state(run_dir, state)
    return state


def validate_page_manifest(manifest: dict[str, Any], approved: set[str], approved_mapping: dict[str, dict[str, Any]] | None = None) -> list[str]:
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
        require_safe_id(page_id, "page_id")
        require_safe_id(cluster_id, "cluster_id")
        normalized_route = route_key(route)
        for field in ("target_query", "page_type", "action", "brief_path"):
            if not isinstance(page[field], str) or not page[field].strip():
                raise WorkflowError(f"{page_id}.{field} must be non-empty text")
        brief_path = Path(page["brief_path"])
        if brief_path.is_absolute() or ".." in brief_path.parts or "\\" in page["brief_path"]:
            raise WorkflowError(f"{page_id}.brief_path must stay inside the run directory")
        if page["action"] not in ALLOWED_RECOMMENDATIONS:
            raise WorkflowError(f"{page_id}.action is invalid")
        if page["page_type"] not in {"use-case", "comparison", "landing", "blog"}:
            raise WorkflowError(f"{page_id}.page_type is invalid")
        for field in ("implementation_paths", "evidence_paths"):
            if not isinstance(page.get(field, []), list) or not all(isinstance(item, str) and item.strip() for item in page.get(field, [])):
                raise WorkflowError(f"{page_id}.{field} must be a string array")
        if approved_mapping is not None:
            if cluster_id not in approved_mapping:
                raise WorkflowError(f"Unapproved cluster: {cluster_id}")
            validate_mapping(page, approved_mapping[cluster_id])
        if page_id in page_ids:
            raise WorkflowError(f"Duplicate page_id: {page_id}")
        if cluster_id in cluster_ids:
            raise WorkflowError(f"Duplicate cluster_id in page manifest: {cluster_id}")
        if normalized_route in routes:
            raise WorkflowError(f"Duplicate route in page manifest: {route}")
        page_ids.append(page_id)
        cluster_ids.add(cluster_id)
        routes.add(normalized_route)
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
        load_json(manifest_path), set(state["approved_cluster_ids"]), approved_mapping(run_dir, state)
    )
    state["artifacts"]["page_manifest"] = artifact_ref(manifest_path, run_dir)
    state["page_ids"] = page_ids
    state["stage"] = "implementation"
    invalidate_gate_2(state)
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
            if not all(isinstance(value, str) and value for value in key):
                raise WorkflowError(f"{page_id}: QA category and name must be non-empty text")
            if not isinstance(check["evidence"], str):
                raise WorkflowError(f"{page_id}: QA evidence must be text")
            if key in seen_checks:
                raise WorkflowError(f"Duplicate QA check for {page_id}: {key[0]}/{key[1]}")
            seen_checks.add(key)
            if status == "Pass" and not check["evidence"].strip():
                blockers.append(f"{page_id}:{check['category']}:{check['name']}:Missing evidence")
            if status == "Fail" or (status == "Not run" and (key in REQUIRED_QA_CHECKS or check.get("required", True))):
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
    manifest = load_json(run_dir / state["artifacts"]["page_manifest"])
    current_ids = validate_page_manifest(manifest, set(state["approved_cluster_ids"]), approved_mapping(run_dir, state))
    if set(current_ids) != set(state["page_ids"]):
        raise WorkflowError("Page manifest changed; record the pages again before QA")
    report_path = Path(args.report)
    blockers = validate_qa(load_json(report_path), set(state["page_ids"]))
    state["artifacts"]["qa_report"] = artifact_ref(report_path, run_dir)
    state["qa_blockers"] = blockers
    state["stage"] = "gate_2_review"
    state["gates"]["gate_2"]["status"] = "Pending"
    state["gates"]["gate_2"]["review_digest"] = review_digest(run_dir, state, 2)
    state["gates"]["gate_2"].pop("approved_digest", None)
    save_state(run_dir, state)
    return state


def decide_gate(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    reviewer = args.reviewer.strip()
    if not reviewer or reviewer.casefold() in {"agent", "ai", "deepseek"}:
        raise WorkflowError("A named human reviewer is required")
    gate_key = f"gate_{args.gate}"
    gate = state["gates"][gate_key]
    if gate["status"] != "Pending":
        raise WorkflowError(f"Gate {args.gate} is not pending; current status is {gate['status']}")
    approved = args.decision == "approve"
    if approved and gate.get("review_digest") != review_digest(run_dir, state, args.gate):
        raise WorkflowError(f"Gate {args.gate} review contents changed; rerun the stage before approval")
    if args.gate == 2 and approved and state["qa_blockers"]:
        raise WorkflowError("Gate 2 cannot be approved while QA blockers remain")
    entry = {
        "decision": "Approved" if approved else "Rejected",
        "reviewer": reviewer,
        "timestamp": now_iso(),
        "notes": args.notes or "",
    }
    if approved:
        gate["approved_digest"] = gate["review_digest"]
        entry["approved_digest"] = gate["approved_digest"]
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
