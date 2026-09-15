'use strict';

const $ = selector => document.querySelector(selector);
const fields = [
  ['icp', 'ICP · 服务谁', '目标用户角色、团队规模、最重要的痛点'],
  ['query_bank', 'Query Bank · 高意图查询', '每行一个 Query；或上传含 Query 列的 CSV'],
  ['product_capabilities', '已验证的产品事实', '支持什么、不支持什么、差异点、证据和已确认的 CTA 地址'],
  ['sitemap', '已有页面 Sitemap', '现有 URL、标题和负责的意图。没有请写“暂无”'],
  ['use_case_taxonomy', 'Use Case 分类', '已有分类及每类解决的用户任务'],
  ['page_skill', '页面 Skill', '粘贴 ojo-solution-pages 或当前页面 Skill 的说明'],
  ['design_system', 'Homepage / Design System', '现有组件、品牌视觉、布局、字体、移动端约束'],
  ['seo_rules', 'SEO Rules', '目标语言、域名、Title / Description、内链、Schema 与禁用规则']
];
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let project = null, busy = false, dirty = false, inputsDirty = false;
const drafts = new Map();

function status(message, kind = '') { $('#status').textContent = message; $('#status').className = 'status ' + kind; }
function values() { return {...Object.fromEntries(fields.map(([key]) => [key, $('#input-' + key).value])), target_language: $('#target-language').value}; }
function setInputs(inputs) { fields.forEach(([key]) => { $('#input-' + key).value = inputs[key] || ''; }); $('#target-language').value = inputs.target_language || 'en-US'; }
function inputsChanged() { inputsDirty = Boolean(project); dirty = true; if (project) status('输入已修改。请重新分析，旧的审核决定不会应用于新资料。'); render(); }
function download(name, data, type = 'application/json') { const url = URL.createObjectURL(data instanceof Blob ? data : new Blob([data], {type})); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 10000); }

$('#inputs').innerHTML = fields.map(([key, label, help]) => `<div><div class="input-head"><label for="input-${key}">${escape(label)}</label><label class="upload">上传文件<input type="file" data-upload="${key}" accept=".txt,.md,.csv,.json,.xml,.yaml,.yml" hidden></label></div><textarea id="input-${key}" maxlength="${key === 'query_bank' ? 40000 : 18000}" placeholder="${escape(help)}"></textarea></div>`).join('');
fields.forEach(([key]) => $('#input-' + key).addEventListener('input', inputsChanged));
$('#target-language').addEventListener('input', inputsChanged);
document.querySelectorAll('[data-upload]').forEach(input => input.addEventListener('change', async () => { const file = input.files[0]; if (!file) return; if (file.size > 180000) return status('文件过大，请先保留本批相关资料。', 'error'); $('#input-' + input.dataset.upload).value = await file.text(); inputsChanged(); input.value = ''; }));

async function api(path, body = {}, withKey = false, binary = false) {
  const headers = {'Content-Type': 'application/json'};
  if (withKey) {
    body = {...body, api_key: $('#api-key').value.trim()};
    const token = $('#access-token').value.trim();
    if (token) headers.Authorization = 'Bearer ' + token;
    if (!body.api_key && !token) throw new Error('请先填写 DeepSeek API Key，或服务器访问口令。');
  }
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 200000);
  try {
    const res = await fetch(path, {method: 'POST', headers, body: JSON.stringify(body), signal: controller.signal});
    if (binary && res.ok) return res.blob();
    const text = await res.text(); let payload;
    try { payload = JSON.parse(text); } catch { throw new Error('服务器未返回有效结果，可能是部署超时。资料已保留，请重试当前步骤。'); }
    if (!res.ok) throw new Error(payload.error || '本步骤失败，请稍后重试。');
    return payload;
  } catch (error) { if (error.name === 'AbortError') throw new Error('本步骤超过等待时间。资料已保留，请稍后重试当前页面。'); throw error; }
  finally { clearTimeout(timeout); }
}

function accept(data) { project = data.project; dirty = true; inputsDirty = false; render(); }
async function run(message, action) {
  if (busy) return;
  busy = true; status(message, 'busy'); document.querySelectorAll('button,input,textarea,select').forEach(control => { control.disabled = true; });
  try { await action(); } catch (error) { status(error.message, 'error'); }
  finally { busy = false; document.querySelectorAll('button,input,textarea,select').forEach(control => { control.disabled = false; }); updateButtons(); }
}
function updateButtons() { if (busy) document.querySelectorAll('button,input,textarea,select').forEach(control => { control.disabled = true; }); $('#export').disabled = busy || inputsDirty || drafts.size > 0 || project?.gate2?.status !== 'Approved'; $('#approve2').disabled = busy || drafts.size > 0; $('#save-project').disabled = busy; }

$('#test-connection').addEventListener('click', () => run('正在测试 DeepSeek 连接…', async () => { await api('/api/test', {}, true); status('DeepSeek 连接成功。现在可以分析 Query。'); }));
$('#load-example').addEventListener('click', () => run('正在载入合成示例…', async () => { const res = await fetch('/api/example'); if (!res.ok) throw new Error('示例暂时无法读取。'); const data = await res.json(); setInputs(data.inputs); inputsChanged(); status('已填入合成示例。点击分析将真实调用 DeepSeek，并消耗少量 API 额度。'); }));
$('#analyze').addEventListener('click', () => run('DeepSeek 正在聚类、判断意图及页面机会，通常需要 30–90 秒…', async () => { const result = await api('/api/analyze', {inputs: values()}, true); drafts.clear(); accept(result); status(`分析完成：${project.analysis.clusters.length} 个 Cluster。请审核并选取 1–5 个。`); $('#gate1-panel').scrollIntoView(); }));
$('#approve1').addEventListener('click', () => run('正在记录 Gate 1 审核…', async () => { const selected_ids = [...document.querySelectorAll('[data-cluster]:checked')].map(input => input.dataset.cluster); accept(await api('/api/gate1', {project, selected_ids, reviewer: $('#reviewer1').value})); status('Gate 1 已批准。可以逐页生成 Brief、预览和 QA。'); $('#pages-panel').scrollIntoView(); }));
$('#reject1').addEventListener('click', () => run('正在退回选题…', async () => { accept(await api('/api/gate1', {project, selected_ids: [], reviewer: $('#reviewer1').value, decision: 'reject'})); status('选题已退回；可以重新选择或修改输入后重新分析。'); }));

async function generate(cid) { if (drafts.size) throw new Error('页面有尚未应用的修改，请先点「保存修改并重新检查」。'); accept(await api('/api/brief', {project, cluster_id: cid}, true)); }
$('#generate-all').addEventListener('click', () => run('准备生成页面…', async () => {
  const ids = project.gate1.selected_ids.filter(cid => !project.pages[cid]);
  if (!ids.length) return status('所有页面均已生成。可以修改内容或单独重新生成。');
  for (let i = 0; i < ids.length; i++) { const cluster = project.analysis.clusters.find(c => c.cluster_id === ids[i]); status(`正在生成 ${i + 1}/${ids.length}：${cluster.cluster_label}。完成的页面会保留。`, 'busy'); await generate(ids[i]); }
  status('页面已全部生成。请查看预览、修正文案，再完成 Gate 2。建议现在保存项目。');
}));

function render() {
  const active = project && !inputsDirty;
  $('#gate1-panel').hidden = !active;
  $('#pages-panel').hidden = !active || project.gate1?.status !== 'Approved';
  $('#gate2-panel').hidden = !active || project.gate1?.status !== 'Approved';
  if (!active) { updateButtons(); return; }
  const selected = project.gate1?.selected_ids || [];
  $('#cluster-table').innerHTML = `<table><thead><tr><th>选择</th><th>Cluster / Query</th><th>用户 / 意图</th><th>已有覆盖 / 冲突</th><th>建议 / 优先级</th></tr></thead><tbody>${project.analysis.clusters.map(c => `<tr><td><input type="checkbox" data-cluster="${escape(c.cluster_id)}" aria-label="选择 ${escape(c.cluster_label)}" ${selected.includes(c.cluster_id) ? 'checked' : ''}></td><td><strong>${escape(c.cluster_label)}</strong><p>${escape(c.primary_query)}</p><details><summary>${c.member_queries.length} 个查询</summary>${c.member_queries.map(q => `<p>${escape(q)}</p>`).join('')}</details></td><td>${escape(c.icp)}<p>${escape(c.search_intent)}</p><small>${escape(c.funnel_stage)} · ICP ${c.icp_relevance}/5 · 商业 ${c.commercial_intent}/5</small></td><td>${escape(c.existing_page || '未发现匹配页面')}<p>覆盖 ${escape(c.coverage)} · 风险 ${escape(c.cannibalization_risk)}</p></td><td><span class="tag">${escape(c.priority)}</span> ${escape(c.recommendation)}<p>${escape(c.rationale)}</p></td></tr>`).join('')}</tbody></table>`;
  $('#page-list').innerHTML = selected.map(cid => {
    const cluster = project.analysis.clusters.find(c => c.cluster_id === cid), page = project.pages[cid];
    if (!page) return `<article class="page-card" data-page="${escape(cid)}"><div class="page-head"><h3>${escape(cluster.cluster_label)}</h3><button data-generate="${escape(cid)}">生成此页</button></div><p class="pending">待生成 · ${escape(cluster.primary_query)}</p></article>`;
    const b = page.brief, seo = b.search_metadata, cta = b.conversion.primary_cta;
    const fails = page.qa.filter(q => q.status === 'Fail').length;
    const editorFields = [ ['page_name','页面名称', b.page_name], ['route','目标路由', b.route], ['h1','H1', seo.h1], ['title','Title', seo.title], ['description','Description', seo.description], ['canonical','Canonical', seo.canonical], ['cta_label','主 CTA 文案',cta.label], ['cta_destination','主 CTA 路径',cta.destination] ];
    return `<article class="page-card" data-page="${escape(cid)}"><div class="page-head"><div><h3>${escape(b.page_name)}</h3><small>${escape(b.route)} · ${escape(b.target_query)}</small></div><span class="tag ${fails ? 'Fail' : 'Warning'}">${fails ? fails + ' 项 Fail' : '内容待人工审核'}</span></div><div class="page-actions"><button data-device="${escape(cid)}">切换手机预览</button><button data-generate="${escape(cid)}">重新生成</button><button data-download="${escape(cid)}">下载 HTML 草稿</button><button data-brief="${escape(cid)}">下载 Brief JSON</button></div><div class="preview-shell" id="preview-${escape(cid)}"><iframe sandbox="" title="${escape(b.page_name)} 页面内容预览" loading="lazy"></iframe></div><details><summary>编辑文案 / Metadata / CTA</summary><div class="input-grid">${editorFields.map(([key,label,value]) => `<label>${label}<input data-edit="${key}" value="${escape(value)}"></label>`).join('')}</div>${b.sections.map((section, index) => `<label>Section ${index + 1} · ${escape(section.name)}<input data-section-h2="${index}" value="${escape(section.h2)}" placeholder="H2"><textarea data-section-copy="${index}">${escape(section.core_copy)}</textarea></label>`).join('')}${b.faq.map((faq,index) => `<label>FAQ ${index + 1}<input data-faq-question="${index}" value="${escape(faq.question)}"><textarea data-faq-answer="${index}">${escape(faq.answer)}</textarea></label>`).join('')}<div class="actions"><button data-save="${escape(cid)}" class="primary">保存修改并重新检查</button></div><details><summary>完整 Brief（高级编辑）</summary><textarea class="editor" data-json="${escape(cid)}">${escape(JSON.stringify(b, null, 2))}</textarea><button data-save-json="${escape(cid)}">应用 JSON 并检查</button></details></details><details><summary>QA 详情 · 内容与工程分开记录</summary><div class="table-wrap"><table class="qa-table"><thead><tr><th>检查项</th><th>状态</th><th>证据 / 后续工作</th></tr></thead><tbody>${page.qa.map(q => `<tr><td>${escape(q.category)} / ${escape(q.name)}</td><td><span class="tag ${escape(q.status.replace(' ','-'))}">${escape(q.status)}</span></td><td>${escape(q.evidence)}</td></tr>`).join('')}</tbody></table></div></details><details><summary>产品事实、假设与证据缺口</summary><p>${escape(JSON.stringify({product_truth:b.product_truth,assumptions:b.assumptions,proof_gaps:b.proof_gaps}, null, 2))}</p></details></article>`;
  }).join('');
  document.querySelectorAll('[data-page]').forEach(card => { const page = project.pages[card.dataset.page]; if (page) card.querySelector('iframe').srcdoc = page.html; });
  document.querySelectorAll('[data-page]').forEach(card => { const saved = drafts.get(card.dataset.page); if (saved) card.querySelectorAll('input,textarea').forEach((input,index) => { if (saved[index] !== undefined) input.value = saved[index]; }); });
  const gate = project.gate2;
  $('#gate2-status').textContent = gate ? `${gate.status} · ${gate.reviewer} · ${gate.at}${gate.status === 'Approved' ? ' · 内容交付已批准；生产工程仍待完成。' : ''}` : '尚未批准。';
  document.querySelectorAll('[data-review]').forEach(input => { input.checked = gate?.status === 'Approved' && gate.checks?.[input.dataset.review] === true; });
  updateButtons();
}

$('#page-list').addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button || busy) return;
  if (button.dataset.device) { const shell = $('#preview-' + button.dataset.device); shell.classList.toggle('mobile'); button.textContent = shell.classList.contains('mobile') ? '切换桌面预览' : '切换手机预览'; }
  if (button.dataset.download) { const cid = button.dataset.download; download(cid + '-DRAFT.html', project.pages[cid].html, 'text/html'); }
  if (button.dataset.brief) download(button.dataset.brief + '-brief.json', JSON.stringify(project.pages[button.dataset.brief].brief, null, 2));
  if (button.dataset.generate) run('正在重新生成此页，其余页面会保留…', async () => { await generate(button.dataset.generate); status('此页生成完成。修改后的内容需要重新进行 Gate 2 审核。'); });
  if (button.dataset.save || button.dataset.saveJson) run('正在应用修改并重新检查…', async () => {
    const cid = button.dataset.save || button.dataset.saveJson, card = button.closest('[data-page]');
    let brief;
    if (button.dataset.saveJson) { try { brief = JSON.parse(card.querySelector('[data-json]').value); } catch { throw new Error('Brief JSON 格式有误，请检查引号、逗号和括号。'); } }
    else {
      brief = JSON.parse(JSON.stringify(project.pages[cid].brief));
      card.querySelectorAll('[data-edit]').forEach(input => { const key = input.dataset.edit; if (key === 'page_name' || key === 'route') brief[key] = input.value; else if (key === 'cta_label') brief.conversion.primary_cta.label = input.value; else if (key === 'cta_destination') brief.conversion.primary_cta.destination = input.value; else brief.search_metadata[key] = input.value; });
      card.querySelectorAll('[data-section-h2]').forEach(input => { brief.sections[Number(input.dataset.sectionH2)].h2 = input.value; });
      card.querySelectorAll('[data-section-copy]').forEach(input => { brief.sections[Number(input.dataset.sectionCopy)].core_copy = input.value; });
      card.querySelectorAll('[data-faq-question]').forEach(input => { brief.faq[Number(input.dataset.faqQuestion)].question = input.value; });
      card.querySelectorAll('[data-faq-answer]').forEach(input => { brief.faq[Number(input.dataset.faqAnswer)].answer = input.value; });
    }
    const result = await api('/api/render', {project, cluster_id: cid, brief}); drafts.delete(cid); accept(result); status('修改已保存，预览与 QA 已更新。请重新审核 Gate 2。');
  });
});
$('#page-list').addEventListener('input', event => { const card = event.target.closest('[data-page]'); if (!card) return; drafts.set(card.dataset.page, [...card.querySelectorAll('input,textarea')].map(input => input.value)); dirty = true; status('页面有未应用的修改，请点该页「保存修改并重新检查」后再审核或导出。'); updateButtons(); });

$('#approve2').addEventListener('click', () => run('正在确认内容审核…', async () => { const checks = Object.fromEntries([...document.querySelectorAll('[data-review]')].map(input => [input.dataset.review, input.checked])); accept(await api('/api/gate2', {project, reviewer: $('#reviewer2').value, checks, notes: $('#review-notes').value})); status('内容交付已批准。下载 ZIP 交给页面 Skill 在目标仓库实施；上线仍需单独审核。'); }));
$('#reject2').addEventListener('click', () => run('正在记录退回意见…', async () => { accept(await api('/api/gate2', {project, reviewer: $('#reviewer2').value, checks: {}, notes: $('#review-notes').value, decision: 'reject'})); status('内容已退回修改，可以编辑或重新生成单页。'); }));
$('#export').addEventListener('click', () => run('正在生成交付包…', async () => { download('query-to-page-handoff.zip', await api('/api/export', {project}, false, true)); status('交付包已下载：Brief、Metadata、文案、HTML 预览、QA、Page Skill 交接说明与项目快照。'); }));
$('#save-project').addEventListener('click', () => { if (drafts.size) return status('请先在编辑过的页面点击「保存修改并重新检查」，再保存项目。', 'error'); const saved = project && !inputsDirty ? project : {version: 1, draft: true, inputs: values()}; download('query-to-page-project.json', JSON.stringify(saved, null, 2)); dirty = false; status('项目已下载，API Key 和访问口令不在文件中。以后可导入继续。'); });
$('#import-project').addEventListener('change', () => run('正在导入项目…', async () => { const input = $('#import-project'), file = input.files[0]; if (!file) return; if (file.size > 2000000) throw new Error('项目文件超过 2 MB。'); const saved = JSON.parse(await file.text()); if (saved.draft && saved.version === 1 && saved.inputs) { setInputs(saved.inputs); project = null; inputsDirty = false; render(); } else { accept(await api('/api/import', {project: saved})); setInputs(project.inputs); } dirty = false; input.value = ''; status('项目已恢复。请重新输入 DeepSeek Key 后继续。'); }));
window.addEventListener('beforeunload', event => { if (dirty || busy) { event.preventDefault(); event.returnValue = ''; } });
