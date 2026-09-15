"""Stateless browser workflow. Gate approvals are bound to the reviewed content."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlsplit

from scripts.workflow_state import REQUIRED_INPUTS, validate_analysis
from .pipeline import ANALYSIS_SYSTEM, BRIEF_SYSTEM, SECRET_PATTERNS, PipelineError, render_brief, validate_briefs


class WebError(ValueError):
    pass


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any, label: str, limit: int = 18000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WebError(f"请填写 {label}；如果没有资料，请明确写‘暂无’，不要留空。")
    if len(value) > limit:
        raise WebError(f"{label} 超过 {limit} 字符，请缩减后重试。")
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(lambda m: f"{m.group(1)}[REDACTED]" if m.lastindex else "[REDACTED]", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", value)
    return value.strip()


def inputs_from(value: Any) -> dict:
    if not isinstance(value, dict):
        raise WebError("缺少项目输入。")
    inputs = {name: clean_text(value.get(name), name, 40000 if name == "query_bank" else 18000) for name in sorted(REQUIRED_INPUTS)}
    if sum(map(len, inputs.values())) > 90000:
        raise WebError("八类输入合计最多 90,000 字符，请先保留与本批页面有关的资料。")
    language = str(value.get("target_language", "en-US")).strip()
    if not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,2}", language):
        raise WebError("页面语言请输入语言代码，例如 en-US、ja-JP、zh-CN。")
    inputs["target_language"] = language
    return inputs


def queries_from(text: str) -> list[str]:
    first = text.splitlines()[0].lower()
    if "," in first or "\t" in first:
        reader = csv.DictReader(io.StringIO(text), delimiter="\t" if "\t" in first else ",")
        columns = {str(key).strip().lower(): key for key in (reader.fieldnames or [])}
        key = next((columns[name] for name in ("query", "keyword", "top queries", "查询", "关键词") if name in columns), None)
        if key is None:
            raise WebError("Query Bank CSV 需要 query 或 keyword 列；也可以每行粘贴一个词。")
        rows = [str(row.get(key) or "").strip() for row in reader]
    else:
        rows = [line.strip().lstrip("-• ") for line in text.splitlines()]
    result = list({row.casefold(): row for row in reversed(rows) if row}.values())[::-1]
    if not result or len(result) > 300:
        raise WebError("每批需要 1–300 个 Query。更大的词库请按市场或主题拆分。")
    if any(len(row) > 300 for row in result):
        raise WebError("单个 Query 最多 300 字符，请检查 CSV 列或换行。")
    return result


def context(inputs: dict) -> str:
    return "\n".join(f"SOURCE {name}:\n{value}" for name, value in inputs.items())


def checked_analysis(value: Any) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("clusters"), list) or len(value["clusters"]) > 80:
        raise WebError("模型的 Cluster 输出无效或超过 80 组，请缩小 Query 范围后重试。")
    # The model proposes priorities; selection is exclusively the human's decision.
    result = json.loads(json.dumps(value))
    for cluster in result["clusters"]:
        if not isinstance(cluster, dict):
            raise WebError("Cluster 必须是对象。")
        cluster["selected"] = False
    validate_analysis(result, 0)
    for cluster in result["clusters"]:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", cluster["cluster_id"]):
            raise WebError("Cluster ID 需要使用英文、数字、横线或下划线。")
        for field in ("cluster_label", "primary_query", "icp", "search_intent", "existing_page", "rationale"):
            if not isinstance(cluster[field], str) or len(cluster[field]) > 4000:
                raise WebError(f"Cluster 字段格式不正确：{field}")
    return result


def analyze(inputs: Any, model: Any) -> dict:
    inputs = inputs_from(inputs)
    queries = queries_from(inputs["query_bank"])
    response = model.complete_json(system=ANALYSIS_SYSTEM + " Use safe ASCII cluster_id. Explanations in Chinese; preserve query language. Set selected=false for all clusters. No requirement for any P0. At most 80 clusters.", user=f"Cover every supplied query exactly once. Do not add queries. Query list JSON: {json.dumps(queries, ensure_ascii=False)}\n{context(inputs)}", max_tokens=14000)
    analysis = checked_analysis(response)
    expected = {q.casefold() for q in queries}
    mapped = [str(q).strip().casefold() for c in analysis["clusters"] for q in c["member_queries"]]
    if set(mapped) != expected or len(mapped) != len(set(mapped)):
        raise WebError("模型没有完整且唯一地覆盖所有 Query，请重试分析或缩小本批词库。当前输入已保留。")
    for cluster in analysis["clusters"]:
        if cluster["primary_query"].casefold() not in {str(q).casefold() for q in cluster["member_queries"]}:
            raise WebError("主 Query 不属于其 Cluster，请重新分析。")
    return {"version": 1, "created_at": now(), "inputs": inputs, "analysis": analysis, "gate1": None, "pages": {}, "gate2": None}


def project_from(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("version") != 1:
        raise WebError("项目快照版本不正确，请导入此工具导出的 JSON。")
    project = {"version": 1, "created_at": str(value.get("created_at", now())), "inputs": inputs_from(value.get("inputs")), "analysis": checked_analysis(value.get("analysis")), "gate1": value.get("gate1"), "pages": value.get("pages", {}), "gate2": value.get("gate2")}
    if not isinstance(project["pages"], dict) or len(project["pages"]) > 5:
        raise WebError("每个项目最多 5 个页面。")
    return project


def gate1_digest(project: dict, ids: list) -> str:
    return fingerprint({"inputs": project["inputs"], "analysis": project["analysis"], "selected_ids": ids})


def require_gate1(project: dict) -> list:
    gate = project.get("gate1")
    if not isinstance(gate, dict) or gate.get("status") != "Approved" or not str(gate.get("reviewer", "")).strip():
        raise WebError("请先由具名审核人批准 Human Gate 1。")
    ids = gate.get("selected_ids", [])
    allowed = {c["cluster_id"] for c in project["analysis"]["clusters"]}
    if not isinstance(ids, list) or not 1 <= len(ids) <= 5 or len(set(ids)) != len(ids) or not set(ids).issubset(allowed):
        raise WebError("Gate 1 必须选定 1–5 个有效 Cluster。")
    if gate.get("digest") != gate1_digest(project, ids):
        raise WebError("输入或分析已经改变，请重新审核 Gate 1。")
    return ids


def approve_gate1(value: Any, ids: Any, reviewer: Any, decision: str = "approve") -> dict:
    project = project_from(value)
    reviewer = clean_text(reviewer, "审核人", 100)
    if decision not in {"approve", "reject"}:
        raise WebError("审核决定无效。")
    if decision == "reject":
        project.update(gate1={"status": "Rejected", "reviewer": reviewer, "at": now()}, pages={}, gate2=None)
        return project
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        raise WebError("请选择需要生产的 Cluster。")
    project["gate1"] = {"status": "Approved", "reviewer": reviewer, "at": now(), "selected_ids": ids, "digest": gate1_digest(project, ids)}
    require_gate1(project)
    project.update(pages={}, gate2=None)
    return project


def safe_url(value: Any, allow_anchor: bool = True) -> str:
    if not isinstance(value, str) or not value or len(value) > 2000 or re.search(r"[\s\x00-\x1f\\]", value):
        return ""
    if value.startswith("#"):
        return value if allow_anchor else ""
    if value.startswith("/") and not value.startswith("//"):
        return value
    parts = urlsplit(value)
    if parts.scheme in {"https", "http"} and parts.netloc and not parts.username and not parts.password:
        return value
    return ""


def checked_brief(value: Any, cid: str) -> dict:
    brief = validate_briefs({"briefs": [value]}, {cid})[0]
    for name in ("page_id", "page_name", "target_query", "search_intent", "icp", "user_pain", "route"):
        if not isinstance(brief[name], str) or not brief[name].strip():
            raise WebError(f"Brief 缺少 {name}。")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", brief["page_id"]):
        raise WebError("page_id 只能使用英文、数字、横线和下划线。")
    if not brief["route"].startswith("/") or not safe_url(brief["route"], False):
        raise WebError("页面 route 必须是站内路径，例如 /use-cases/example。")
    for name in ("supporting_queries", "assumptions", "proof_gaps", "prohibited_claims", "acceptance_criteria"):
        if not isinstance(brief[name], list) or any(not isinstance(v, str) for v in brief[name]):
            raise WebError(f"{name} 必须是文本数组。")
    for name in ("product_truth", "search_metadata", "conversion", "internal_links"):
        if not isinstance(brief[name], dict):
            raise WebError(f"{name} 格式不正确。")
    seo = brief["search_metadata"]
    for name in ("h1", "title", "description", "canonical", "robots"):
        if not isinstance(seo.get(name), str):
            raise WebError(f"search_metadata.{name} 必须是文本。")
    for name in ("primary_cta", "secondary_cta"):
        cta = brief["conversion"].get(name)
        if not isinstance(cta, dict) or not all(isinstance(cta.get(k), str) for k in ("label", "destination")):
            raise WebError(f"conversion.{name} 需要 label 和 destination。")
    if not isinstance(brief["sections"], list) or not brief["sections"] or len(brief["sections"]) > 15:
        raise WebError("页面需要 1–15 个 Section。")
    for item in brief["sections"]:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in ("name", "h2", "core_copy")):
            raise WebError("每个 Section 需要 name、h2 和 core_copy 文本。")
    if not isinstance(brief["faq"], list) or len(brief["faq"]) > 15:
        raise WebError("FAQ 格式不正确。")
    for item in brief["faq"]:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in ("question", "answer")):
            raise WebError("FAQ 需要 question 和 answer。")
    for name in ("inbound", "outbound"):
        if not isinstance(brief["internal_links"].get(name), list):
            raise WebError("internal_links 需要 inbound / outbound 数组。")
    for name in ("verified_capabilities", "differentiation", "evidence_sources"):
        if not isinstance(brief["product_truth"].get(name), list):
            raise WebError(f"product_truth.{name} 需要数组。")
    if len(json.dumps(brief, ensure_ascii=False)) > 60000:
        raise WebError("单页 Brief 超过 60,000 字符，请缩减。")
    return brief


def preview_html(brief: dict, language: str = "en-US") -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    seo, conv = brief["search_metadata"], brief["conversion"]
    section_html = "".join(f'<section id="{esc(re.sub(r"[^a-z0-9-]", "-", s["name"].lower()).strip("-") or "section-" + str(i))}">{"<h2>" + esc(s["h2"]) + "</h2>" if s["h2"] else ""}<p>{esc(s["core_copy"])}</p></section>' for i, s in enumerate(brief["sections"]))
    faqs = "".join(f'<details><summary>{esc(item["question"])}</summary><p>{esc(item["answer"])}</p></details>' for item in brief["faq"])
    buttons = "".join(f'<a class="cta" href="{esc(safe_url(cta["destination"]) or "#")}">{esc(cta["label"])}</a>' for cta in conv.values() if isinstance(cta, dict) and cta.get("label"))
    links = "".join(f'<li><a href="{esc(safe_url(link))}">{esc(link)}</a></li>' for link in brief["internal_links"]["outbound"] if safe_url(link))
    schema = {"@context": "https://schema.org", "@type": "WebPage", "name": seo["title"], "description": seo["description"], "url": safe_url(seo["canonical"], False)}
    schema_text = json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'''<!doctype html><html lang="{esc(language)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{esc(seo["title"])}</title><meta name="description" content="{esc(seo["description"])}"><link rel="canonical" href="{esc(safe_url(seo["canonical"], False))}"><script type="application/ld+json">{schema_text}</script><style>*{{box-sizing:border-box}}body{{margin:0;background:#faf9f6;color:#18342e;font:17px/1.7 system-ui,sans-serif;overflow-wrap:anywhere}}main{{max-width:1060px;margin:auto;padding:36px 6vw}}aside{{padding:10px 6vw;background:#e4efe9;font-size:12px}}h1{{font-size:clamp(34px,6vw,70px);line-height:1.1;letter-spacing:-.04em;max-width:880px;margin:38px 0 28px}}h2{{line-height:1.2;font-size:clamp(24px,4vw,34px)}}section{{padding:26px 0;border-bottom:1px solid #d2ddd6}}p{{max-width:780px;white-space:pre-line}}.cta{{display:inline-block;margin:8px 12px 8px 0;padding:12px 22px;border-radius:9px;background:#244f40;color:#fff;text-decoration:none}}details{{padding:16px;border:1px solid #d2ddd6;margin:12px 0;border-radius:10px}}summary{{cursor:pointer;font-weight:650}}a{{color:#244f40}}footer{{margin-top:36px;font-size:13px;color:#53675e}}</style></head><body><aside>内容预览 · 通用响应式模板 · 待接入站点组件和设计系统 · 不用于直接上线</aside><main><h1>{esc(seo["h1"])}</h1><p>{esc(brief["user_pain"])}</p><div>{buttons}</div>{section_html}<section><h2>FAQ</h2>{faqs}</section><section><h2>Related resources</h2><ul>{links}</ul></section><footer>Draft preview · prudenceyang167-rgb</footer></main></body></html>'''


def qa_for(brief: dict, inputs: dict, others: list) -> list:
    checks = []
    def check(category: str, name: str, status: str, evidence: str) -> None:
        checks.append({"category": category, "name": name, "status": status, "evidence": evidence})
    seo = brief["search_metadata"]
    check("SEO", "Title", "Pass" if 10 <= len(seo["title"]) <= 65 else "Warning" if seo["title"].strip() else "Fail", f"{len(seo['title'])} 字符；长度是启发式检查，请按目标语言审核。")
    check("SEO", "Description", "Pass" if 40 <= len(seo["description"]) <= 170 else "Warning" if seo["description"].strip() else "Fail", f"{len(seo['description'])} 字符；这是草稿元数据。")
    check("SEO", "H1 / H2", "Pass" if seo["h1"].strip() and any(s["h2"].strip() for s in brief["sections"]) else "Fail", "预览模板渲染一个 H1；正文需要至少一个 H2。")
    canonical = safe_url(seo["canonical"], False)
    canonical_matches = bool(canonical) and urlsplit(canonical).path.rstrip("/") == brief["route"].rstrip("/")
    check("SEO", "Canonical", "Fail" if not canonical_matches else "Pass" if canonical.startswith("https://") else "Warning", "canonical 未指向本页 route，请修正。" if not canonical_matches else "完整 canonical 地址已提供；尚未验证站点响应。" if canonical.startswith("https://") else "需要确认生产域名与 canonical；预览始终 noindex。")
    links = brief["internal_links"]["outbound"]
    invalid_links = [link for link in links if not safe_url(link)]
    check("SEO", "Internal links", "Fail" if invalid_links else "Warning", "包含无效链接。" if invalid_links else "链接结构已检查；站内目标是否存在需要生产站点验证。")
    check("SEO", "Schema", "Pass", "预览生成有效 WebPage JSON-LD；FAQ 富结果资格不作保证。")
    copy = " ".join([seo["h1"], seo["title"], seo["description"]] + [s["core_copy"] for s in brief["sections"]])
    check("SEO", "Query coverage", "Pass" if brief["target_query"].casefold() in copy.casefold() else "Warning", "精确目标词覆盖检查；同义表达由人工检查。")
    duplicates = [b["page_name"] for b in others if b["route"] == brief["route"] or b["search_metadata"]["title"].casefold() == seo["title"].casefold() or SequenceMatcher(None, copy.casefold(), " ".join(s["core_copy"] for s in b["sections"]).casefold()).ratio() > .88]
    check("SEO", "Batch duplicates", "Fail" if duplicates else "Pass", "与当前批次重复：" + ", ".join(duplicates) if duplicates else "未发现本批页面相同 route / title 或高度相似正文；不代表全站无重复。")
    cta = brief["conversion"]["primary_cta"]
    check("Conversion", "CTA", "Pass" if cta["label"].strip() and safe_url(cta["destination"]) else "Fail", "主 CTA 文本及 URL 格式检查；尚未验证注册流程。")
    check("Conversion", "Signup path", "Warning", "需要在生产环境实际点击并走通注册流程。")
    check("Content", "Product claims", "Warning" if brief["product_truth"]["verified_capabilities"] else "Fail", "产品证据由模型引用，最终真实性须由产品负责人审核。")
    check("Content", "Use case clarity", "Warning", "请核对用户痛点、能力收益与当前页面方向。")
    for name in ("Design system integration", "Component reuse", "Mobile visual QA", "Build", "Type check", "CI", "Performance", "PR / Production release"):
        check("Production", name, "Not run", "浏览器工具未连接目标代码仓库；请使用交付包和 Page Skill 在目标仓库实施及验证。")
    return checks


def update_page(value: Any, cid: str, raw_brief: Any) -> dict:
    project = project_from(value)
    if cid not in require_gate1(project):
        raise WebError("此 Cluster 未经 Gate 1 批准。")
    brief = checked_brief(raw_brief, cid)
    cluster = next(c for c in project["analysis"]["clusters"] if c["cluster_id"] == cid)
    if brief["action"] != cluster["recommendation"] or brief["target_query"].casefold() != cluster["primary_query"].casefold():
        raise WebError("Brief 的目标 Query 和行动建议必须与 Gate 1 一致。改变方向请重新审核 Gate 1。")
    if cluster["recommendation"] == "optimize-existing" and brief["route"] != urlsplit(cluster["existing_page"]).path:
        raise WebError("优化已有页面时必须保留原有页面路径。")
    project["pages"][cid] = {"brief": brief}
    briefs = {key: checked_brief(page.get("brief"), key) for key, page in project["pages"].items()}
    for key, item in briefs.items():
        project["pages"][key] = {"brief": item, "html": preview_html(item, project["inputs"]["target_language"]), "qa": qa_for(item, project["inputs"], [b for k, b in briefs.items() if k != key]), "revision_hash": fingerprint(item)}
    project["gate2"] = None
    return project


def generate_page(value: Any, cid: str, model: Any) -> dict:
    project = project_from(value)
    if cid not in require_gate1(project):
        raise WebError("此 Cluster 未经 Gate 1 批准。")
    cluster = next(c for c in project["analysis"]["clusters"] if c["cluster_id"] == cid)
    result = model.complete_json(system=BRIEF_SYSTEM + " Return exactly ONE brief. Preserve the target query language for page copy. IDs must be safe ASCII. Include 3-7 sections, 2-5 FAQ items. Use only confirmed capabilities; never claim production integration is done. For internal_links use arrays of URL strings, not objects.", user=f"Approved cluster: {json.dumps(cluster, ensure_ascii=False)}\nPrior pages (avoid duplicating their intent): {json.dumps([p['brief']['target_query'] for p in project['pages'].values()], ensure_ascii=False)}\n{context(project['inputs'])}", max_tokens=7000)
    briefs = validate_briefs(result, {cid})
    return update_page(project, cid, briefs[0])


def checked_pages(project: dict) -> dict:
    ids = require_gate1(project)
    if set(project["pages"]) != set(ids):
        raise WebError("请先为所有已批准的 Cluster 生成页面。")
    pages = {cid: checked_brief(project["pages"][cid].get("brief"), cid) for cid in ids}
    mapping = {c["cluster_id"]: c for c in project["analysis"]["clusters"] if c["cluster_id"] in ids}
    validate_briefs({"briefs": list(pages.values())}, set(ids), mapping)
    for cid, brief in pages.items():
        qa = qa_for(brief, project["inputs"], [b for k, b in pages.items() if k != cid])
        if any(q["status"] == "Fail" for q in qa):
            raise WebError(f"{brief['page_name']} 仍有 Fail，请修改 Brief 并重新检查。")
    return pages


def gate2_digest(project: dict, pages: dict) -> str:
    return fingerprint({"gate1": project["gate1"], "briefs": pages})


def approve_gate2(value: Any, reviewer: Any, checks: Any, notes: Any, decision: str = "approve") -> dict:
    project = project_from(value)
    reviewer = clean_text(reviewer, "审核人", 100)
    if decision not in {"approve", "reject"}:
        raise WebError("审核决定无效。")
    if decision == "reject":
        project["gate2"] = {"status": "Rejected", "reviewer": reviewer, "notes": str(notes)[:4000], "at": now()}
        return project
    pages = checked_pages(project)
    required = {"direction", "claims", "copy", "preview", "cta", "handoff_only"}
    if not isinstance(checks, dict) or any(checks.get(k) is not True for k in required):
        raise WebError("请逐项审核页面方向、产品事实、文案、视觉预览、CTA，并确认工程上线仍待实施。")
    project["gate2"] = {"status": "Approved", "scope": "content-handoff-only", "reviewer": reviewer, "checks": {k: True for k in required}, "notes": str(notes)[:4000], "at": now(), "digest": gate2_digest(project, pages)}
    return project


def export_files(value: Any) -> dict:
    project = project_from(value)
    pages = checked_pages(project)
    gate = project.get("gate2")
    if not isinstance(gate, dict) or gate.get("status") != "Approved" or gate.get("digest") != gate2_digest(project, pages):
        raise WebError("请先完成 Human Gate 2。修改内容后需要重新审核。")
    project["pages"] = {cid: {"brief": brief, "html": preview_html(brief, project["inputs"]["target_language"]), "qa": qa_for(brief, project["inputs"], [b for k, b in pages.items() if k != cid]), "revision_hash": fingerprint(brief)} for cid, brief in pages.items()}
    files = {"project.json": json.dumps(project, ensure_ascii=False, indent=2), "page-map.json": json.dumps(project["analysis"], ensure_ascii=False, indent=2)}
    for cid, brief in pages.items():
        base = f"pages/{cid}"
        files[f"{base}/brief.md"] = render_brief(brief)
        files[f"{base}/brief.json"] = json.dumps(brief, ensure_ascii=False, indent=2)
        files[f"{base}/preview.html"] = preview_html(brief, project["inputs"]["target_language"])
        files[f"{base}/metadata.json"] = json.dumps(brief["search_metadata"], ensure_ascii=False, indent=2)
        files[f"{base}/qa.json"] = json.dumps(qa_for(brief, project["inputs"], [b for k, b in pages.items() if k != cid]), ensure_ascii=False, indent=2)
    files["page-skill-handoff.md"] = "# Page Skill implementation handoff\n\nContent approval only. Production implementation, mobile visual QA, build, type check, CI, performance, PR and release are NOT RUN.\n\n1. Read the target repository instructions and supplied Page Skill.\n2. Confirm existing page ownership and routes before editing.\n3. Implement approved briefs with existing components and Homepage design system. Generic preview HTML is reference copy/layout, not production source.\n4. Verify canonical, internal links and actual signup path.\n5. Run repository-native checks and mobile/desktop visual QA.\n6. Obtain separate release approval before PR/merge/publication.\n\n## Supplied Page Skill\n\n" + project["inputs"]["page_skill"] + "\n\n## Design system\n\n" + project["inputs"]["design_system"] + "\n\n## SEO rules\n\n" + project["inputs"]["seo_rules"]
    return files
