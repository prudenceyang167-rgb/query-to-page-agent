"""Vercel-compatible, dependency-free WSGI application for the working agent."""
from __future__ import annotations

import hmac
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Callable, Iterable

from query_to_page_agent import __version__
from query_to_page_agent.provider import DeepSeekClient, ProviderError
from query_to_page_agent import web_workflow as flow

ROOT = Path(__file__).resolve().parent
MAX_BODY = 2_000_000


def response(start_response: Callable, body: bytes, kind: str, status: str = "200 OK", extra: list | None = None) -> Iterable[bytes]:
    headers = [("Content-Type", kind), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"), ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")]
    start_response(status, headers + (extra or []))
    return [body]


def json_response(start_response: Callable, value: dict, status: str = "200 OK") -> Iterable[bytes]:
    return response(start_response, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)


def get_client(data: dict, environ: dict) -> DeepSeekClient:
    raw = data.get("api_key", "")
    if not isinstance(raw, str) or len(raw) > 300:
        raise flow.WebError("DeepSeek API Key 格式不正确。")
    api_key = raw.strip()
    if not api_key:
        expected = os.environ.get("APP_ACCESS_TOKEN", "").strip()
        provided = environ.get("HTTP_AUTHORIZATION", "")
        if not expected or not hmac.compare_digest(provided, "Bearer " + expected):
            raise flow.WebError("请填写自己的 DeepSeek API Key；使用服务器密钥时需要有效的访问口令。")
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise flow.WebError("服务器尚未配置 DeepSeek API Key，请使用自己的 Key。")
    return DeepSeekClient(api_key=api_key, model="deepseek-flash", base_url="https://api.deepseek.com", timeout_seconds=90, retries=0)


def app(environ: dict, start_response: Callable) -> Iterable[bytes]:
    path = environ.get("PATH_INFO", "/") or "/"
    method = environ.get("REQUEST_METHOD", "GET").upper()
    if method == "GET":
        if path == "/api/health":
            return json_response(start_response, {"status": "ok", "service": "query-to-page-agent", "version": __version__, "workflow": "live", "model": "deepseek-flash", "server_key_available": bool(os.environ.get("DEEPSEEK_API_KEY") and os.environ.get("APP_ACCESS_TOKEN"))})
        if path == "/api/demo":
            return json_response(start_response, json.loads((ROOT / "examples/synthetic/prioritization.json").read_text()))
        if path == "/api/example":
            mapping = {"icp": "icp.md", "query_bank": "query-bank.csv", "product_capabilities": "product-capabilities.md", "sitemap": "sitemap.csv", "use_case_taxonomy": "use-cases.md", "page_skill": "page-skill.md", "design_system": "design-system.md", "seo_rules": "seo-rules.md"}
            return json_response(start_response, {"inputs": {key: (ROOT / "examples/synthetic/inputs" / name).read_text() for key, name in mapping.items()}, "synthetic": True})
        resources = {"/": ("web/index.html", "text/html; charset=utf-8"), "/static/app.js": ("web/app.js", "text/javascript; charset=utf-8"), "/static/style.css": ("web/style.css", "text/css; charset=utf-8")}
        if path in resources:
            filename, kind = resources[path]
            return response(start_response, (ROOT / filename).read_bytes(), kind)
        return json_response(start_response, {"error": "页面不存在。"}, "404 Not Found")
    if method != "POST" or not path.startswith("/api/"):
        return json_response(start_response, {"error": "请求方法不支持。"}, "405 Method Not Allowed")
    allowed = {"/api/test", "/api/analyze", "/api/gate1", "/api/brief", "/api/render", "/api/gate2", "/api/export", "/api/import"}
    if path not in allowed:
        return json_response(start_response, {"error": "接口不存在。"}, "404 Not Found")
    try:
        origin = environ.get("HTTP_ORIGIN", "")
        expected_origin = environ.get("wsgi.url_scheme", "https") + "://" + environ.get("HTTP_HOST", "")
        if origin and origin != expected_origin:
            return json_response(start_response, {"error": "请从当前站点发送请求。"}, "403 Forbidden")
        if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip() != "application/json":
            return json_response(start_response, {"error": "需要 application/json 请求。"}, "415 Unsupported Media Type")
        try:
            length = int(environ.get("CONTENT_LENGTH", "0"))
        except ValueError:
            raise flow.WebError("请求长度不正确。")
        if not 1 <= length <= MAX_BODY:
            return json_response(start_response, {"error": "项目最多 2 MB，请缩减输入或拆分批次。"}, "413 Payload Too Large")
        data = json.loads(environ["wsgi.input"].read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise flow.WebError("请求内容必须是 JSON 对象。")
        if path == "/api/test":
            result = get_client(data, environ).complete_json(system='Return only JSON {"ok": true}.', user='Test the connection. JSON only.', max_tokens=30)
            if result.get("ok") is not True:
                raise ProviderError("DeepSeek did not confirm the connection; please retry.")
            return json_response(start_response, {"ok": True, "model": "deepseek-flash"})
        if path == "/api/analyze":
            value = flow.analyze(data.get("inputs"), get_client(data, environ))
        elif path == "/api/gate1":
            value = flow.approve_gate1(data.get("project"), data.get("selected_ids"), data.get("reviewer"), data.get("decision", "approve"))
        elif path == "/api/brief":
            value = flow.generate_page(data.get("project"), data.get("cluster_id"), get_client(data, environ))
        elif path == "/api/render":
            value = flow.update_page(data.get("project"), data.get("cluster_id"), data.get("brief"))
        elif path == "/api/gate2":
            value = flow.approve_gate2(data.get("project"), data.get("reviewer"), data.get("checks"), data.get("notes", ""), data.get("decision", "approve"))
        elif path == "/api/import":
            value = flow.project_from(data.get("project"))
            old_gate = value.get("gate2")
            if value.get("pages"):
                for cid in list(value["pages"]):
                    value = flow.update_page(value, cid, value["pages"][cid]["brief"])
                value["gate2"] = old_gate
            elif (value.get("gate1") or {}).get("status") == "Approved":
                flow.require_gate1(value)
        else:
            files = flow.export_files(data.get("project"))
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, content in files.items():
                    archive.writestr(name, content)
            return response(start_response, output.getvalue(), "application/zip", extra=[("Content-Disposition", 'attachment; filename="query-to-page-handoff.zip"')])
        return json_response(start_response, {"project": value})
    except (flow.WebError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, (flow.WebError, flow.PipelineError)) else "输入或模型响应格式不正确，请检查资料并重试当前步骤。"
        return json_response(start_response, {"error": message}, "400 Bad Request")
    except ProviderError as exc:
        safe = str(exc)
        if "401" in safe:
            message = "DeepSeek Key 无效，请检查 Key 后重试。"
        elif "402" in safe:
            message = "DeepSeek 余额不足，请充值后重试。"
        elif "429" in safe:
            message = "DeepSeek 请求过于频繁，请稍后重试。"
        else:
            message = "DeepSeek 暂时没有返回完整结果（可能超时或输出截断）。资料已保留，请重试本步骤；持续失败时缩减输入。"
        return json_response(start_response, {"error": message}, "502 Bad Gateway")
    except Exception:
        return json_response(start_response, {"error": "本步骤未完成，项目资料已保留。请重试；如持续失败，请查看部署日志。"}, "500 Internal Server Error")


if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    port = int(os.environ.get("PORT", "8000"))
    print(f"Query-to-Page Agent: http://127.0.0.1:{port}")
    make_server("127.0.0.1", port, app).serve_forever()
