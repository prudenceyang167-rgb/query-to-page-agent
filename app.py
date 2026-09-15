"""Zero-dependency WSGI entrypoint for the Vercel portfolio deployment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

from query_to_page_agent import __version__


ROOT = Path(__file__).resolve().parent


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="A human-gated agent that turns high-intent search queries into PR-ready page batches.">
  <title>Query-to-Page Agent — High-intent SEO workflow</title>
  <style>
    :root {
      color-scheme: dark;
      --ink: #0d1110;
      --panel: #151b1a;
      --line: #2a3431;
      --paper: #f2efe8;
      --muted: #aeb9b4;
      --mint: #88d7b5;
      --gold: #d7b95f;
      --danger: #ef8c7f;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      background: var(--ink);
      color: var(--paper);
      font: 15px/1.6 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        radial-gradient(circle at 75% 10%, rgba(87, 130, 111, .18), transparent 34rem),
        linear-gradient(rgba(255,255,255,.018) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px);
      background-size: auto, 64px 64px, 64px 64px;
      mask-image: linear-gradient(to bottom, #000, transparent 75%);
    }
    a { color: inherit; }
    nav, main, footer { width: min(1160px, calc(100% - 40px)); margin: 0 auto; }
    nav { height: 76px; display: flex; align-items: center; justify-content: space-between; position: relative; }
    .brand { display: flex; gap: 11px; align-items: center; font-weight: 700; letter-spacing: -.02em; text-decoration: none; }
    .mark { width: 28px; height: 28px; border: 1px solid var(--mint); border-radius: 9px; display: grid; place-items: center; color: var(--mint); }
    .nav-links { display: flex; gap: 22px; color: var(--muted); }
    .nav-links a { text-decoration: none; }
    .hero { min-height: 650px; display: grid; grid-template-columns: 1.15fr .85fr; gap: 70px; align-items: center; padding: 84px 0 110px; position: relative; }
    .eyebrow { color: var(--mint); font: 600 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .12em; text-transform: uppercase; }
    h1 { margin: 18px 0 22px; font-size: clamp(52px, 7.2vw, 92px); line-height: .98; letter-spacing: -.065em; max-width: 820px; }
    .hero p { color: var(--muted); max-width: 650px; font-size: 18px; }
    .actions { margin-top: 34px; display: flex; gap: 12px; flex-wrap: wrap; }
    .button { border: 1px solid var(--line); border-radius: 999px; padding: 11px 18px; text-decoration: none; font-weight: 650; background: var(--panel); cursor: pointer; color: var(--paper); }
    .button.primary { background: var(--paper); color: var(--ink); border-color: var(--paper); }
    .terminal { background: rgba(21,27,26,.94); border: 1px solid var(--line); border-radius: 22px; overflow: hidden; box-shadow: 0 35px 80px rgba(0,0,0,.35); transform: rotate(1.5deg); }
    .terminal-head { height: 44px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 7px; padding: 0 16px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #44504c; }
    pre { margin: 0; padding: 22px; overflow: auto; color: #cad5d0; font: 12px/1.75 ui-monospace, SFMono-Regular, Menlo, monospace; }
    .ok { color: var(--mint); } .warn { color: var(--gold); }
    section { padding: 100px 0; border-top: 1px solid var(--line); position: relative; }
    .section-head { display: flex; justify-content: space-between; align-items: end; gap: 28px; margin-bottom: 42px; }
    h2 { font-size: clamp(34px, 5vw, 58px); line-height: 1.05; letter-spacing: -.045em; margin: 0; max-width: 720px; }
    .section-head p { color: var(--muted); max-width: 360px; margin: 0; }
    .flow { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
    .step, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 22px; }
    .step small { color: var(--mint); font-family: ui-monospace, monospace; }
    .step h3, .card h3 { margin: 32px 0 8px; font-size: 17px; }
    .step p, .card p { color: var(--muted); margin: 0; font-size: 13px; }
    .step.gate { border-color: rgba(215,185,95,.5); }
    .step.gate small { color: var(--gold); }
    .demo-shell { background: var(--paper); color: #1a201e; border-radius: 24px; padding: 26px; }
    .demo-top { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; }
    .demo-top p { color: #5d6864; margin: 4px 0 0; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 14px 12px; border-bottom: 1px solid #d7d3cb; text-align: left; vertical-align: top; }
    th { color: #6e7773; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
    .pill { display: inline-block; padding: 3px 8px; border-radius: 999px; background: #d8eee4; color: #1f6648; font: 700 11px/1.5 ui-monospace, monospace; }
    .empty { color: #6e7773; padding: 28px 12px; }
    .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .card h3 { margin-top: 4px; }
    .metric { color: var(--mint); font: 700 34px/1 ui-monospace, monospace; margin-bottom: 18px; }
    footer { padding: 48px 0 70px; color: var(--muted); display: flex; justify-content: space-between; gap: 20px; border-top: 1px solid var(--line); }
    @media (max-width: 850px) {
      .nav-links { display: none; }
      .hero { grid-template-columns: 1fr; gap: 48px; padding-top: 60px; }
      .terminal { transform: none; }
      .flow, .cards { grid-template-columns: 1fr; }
      .section-head { align-items: start; flex-direction: column; }
      .demo-shell { overflow-x: auto; }
      table { min-width: 720px; }
    }
    @media (prefers-reduced-motion: no-preference) {
      .terminal { animation: settle .7s ease-out both; }
      @keyframes settle { from { opacity: 0; transform: translateY(22px) rotate(1.5deg); } }
    }
  </style>
</head>
<body>
  <nav>
    <a class="brand" href="/"><span class="mark">Q</span> Query-to-Page Agent</a>
    <div class="nav-links"><a href="#workflow">Workflow</a><a href="#demo">Demo</a><a href="https://github.com/prudenceyang167-rgb/query-to-page-agent">GitHub ↗</a></div>
  </nav>
  <main>
    <div class="hero">
      <div>
        <div class="eyebrow">High-intent SEO production system</div>
        <h1>From query bank to PR-ready pages.</h1>
        <p>A DeepSeek-powered agent for clustering demand, mapping page intent, writing evidence-led briefs, and running QA—without handing critical business decisions to the model.</p>
        <div class="actions"><a class="button primary" href="#demo">Run synthetic demo</a><a class="button" href="https://github.com/prudenceyang167-rgb/query-to-page-agent">View source</a></div>
      </div>
      <div class="terminal" aria-label="Workflow status example">
        <div class="terminal-head"><i class="dot"></i><i class="dot"></i><i class="dot"></i></div>
        <pre><span class="ok">$ q2p analyze</span>

clusters             4
selected P0          3
existing coverage    checked
cannibalization      checked

<span class="warn">● HUMAN GATE 1 — PENDING</span>

$ q2p briefs
blocked: named reviewer required

<span class="ok">✓ model cannot approve its own gate</span></pre>
      </div>
    </div>

    <section id="workflow">
      <div class="section-head"><h2>Autonomy where it saves time. Judgment where it matters.</h2><p>Every model output is validated before it can advance workflow state.</p></div>
      <div class="flow">
        <article class="step"><small>01 / DEEPSEEK</small><h3>Prioritize</h3><p>Cluster, intent, ICP fit, commercial value, coverage and collision risk.</p></article>
        <article class="step gate"><small>GATE 1 / HUMAN</small><h3>Select</h3><p>A named reviewer approves the exact 3–5 page scope.</p></article>
        <article class="step"><small>02 / AGENT</small><h3>Produce</h3><p>Briefs, metadata, copy, schema, page-skill handoff and previews.</p></article>
        <article class="step"><small>03 / EVIDENCE</small><h3>Verify</h3><p>SEO, conversion, mobile, reuse, build, type check, CI and performance.</p></article>
        <article class="step gate"><small>GATE 2 / HUMAN</small><h3>Release</h3><p>Direction, claims, copy, visual output and CTA receive final review.</p></article>
      </div>
    </section>

    <section id="demo">
      <div class="section-head"><h2>A real three-page batch, using synthetic evidence.</h2><p>No API key, company data or model spend is used in this public demo.</p></div>
      <div class="demo-shell">
        <div class="demo-top"><div><strong>Gate 1 candidate packet</strong><p>Load the repository's deterministic example.</p></div><button class="button primary" id="load-demo">Load batch</button></div>
        <div id="demo-output" class="empty">The batch is waiting to be loaded.</div>
      </div>
    </section>

    <section>
      <div class="section-head"><h2>Built to measure whether automation actually helps.</h2><p>The MVP stays at 3–5 pages until the operating evidence supports scaling.</p></div>
      <div class="cards">
        <article class="card"><div class="metric">3–5</div><h3>Controlled batch</h3><p>Small enough to catch systemic template or evidence failures.</p></article>
        <article class="card"><div class="metric">18</div><h3>Required QA checks</h3><p>Missing evidence stays Not run and blocks final approval.</p></article>
        <article class="card"><div class="metric">2</div><h3>Human gates</h3><p>Page selection and release remain accountable decisions.</p></article>
      </div>
    </section>
  </main>
  <footer><span>Open-source portfolio project by prudenceyang167-rgb.</span><span>DeepSeek · Python · Vercel</span></footer>
  <script>
    const button = document.querySelector('#load-demo');
    const output = document.querySelector('#demo-output');
    button.addEventListener('click', async () => {
      button.disabled = true;
      button.textContent = 'Loading…';
      try {
        const response = await fetch('/api/demo');
        if (!response.ok) throw new Error('Demo unavailable');
        const data = await response.json();
        const rows = data.clusters.filter(item => item.selected).map(item => `
          <tr><td><strong>${escapeHtml(item.cluster_label)}</strong><br>${escapeHtml(item.primary_query)}</td><td>${escapeHtml(item.search_intent)}</td><td>${escapeHtml(item.recommendation)}</td><td><span class="pill">${escapeHtml(item.priority)}</span></td></tr>`).join('');
        output.className = '';
        output.innerHTML = `<table><thead><tr><th>Query cluster</th><th>Intent</th><th>Recommendation</th><th>Priority</th></tr></thead><tbody>${rows}</tbody></table>`;
        button.textContent = 'Batch loaded';
      } catch (error) {
        output.textContent = error.message;
        button.disabled = false;
        button.textContent = 'Retry';
      }
    });
    function escapeHtml(value) {
      return String(value).replace(/[&<>'"]/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character]));
    }
  </script>
</body>
</html>"""


def _json_response(start_response: Callable, payload: dict, status: str = "200 OK") -> Iterable[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "public, max-age=60"),
        ],
    )
    return [body]


def app(environ: dict, start_response: Callable) -> Iterable[bytes]:
    """Serve the portfolio UI and read-only synthetic demo endpoints."""
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/") or "/"

    if method != "GET":
        return _json_response(start_response, {"error": "method_not_allowed"}, "405 Method Not Allowed")
    if path == "/api/health":
        return _json_response(
            start_response,
            {"status": "ok", "service": "query-to-page-agent", "version": __version__},
        )
    if path == "/api/demo":
        fixture = ROOT / "examples" / "synthetic" / "prioritization.json"
        return _json_response(start_response, json.loads(fixture.read_text(encoding="utf-8")))
    if path == "/":
        body = INDEX_HTML.encode("utf-8")
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "public, max-age=300"),
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "strict-origin-when-cross-origin"),
            ],
        )
        return [body]
    return _json_response(start_response, {"error": "not_found"}, "404 Not Found")
