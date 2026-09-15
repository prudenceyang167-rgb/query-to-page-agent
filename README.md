# Query-to-Page Agent

Personal project by **prudenceyang167-rgb**.

将高意图 Query Bank 转为可审核的页面决策、Brief、Metadata、核心文案、HTML 内容预览和实施交付包。使用 DeepSeek，支持每批 1–5 页及两个人工审核点。

## 部署后怎么用

1. 打开工作台，填写自己的 DeepSeek API Key，点击「测试连接」。
2. 选择页面语言（如 en-US、ja-JP），填写或上传八类资料：ICP、Query Bank、已验证产品能力、Sitemap、Use Case 分类、页面 Skill、Homepage / Design System、SEO Rules。
3. 点击「分析 Query 与页面机会」。在 Gate 1 检查意图、商业价值、已有覆盖、页面相互竞争风险，并由具名审核人选择 1–5 组。
4. 点击「生成剩余页面」。页面逐个生成，已完成的页会保留，失败的页可以单独重试。
5. 查看桌面/手机内容预览、QA 结果，直接编辑标题、文案、CTA、路由、Section、FAQ；保存后自动重新生成预览和检查。完整 Brief 也可用 JSON 编辑。
6. 完成 Gate 2 的方向、事实、文案、预览和 CTA 审核，下载 ZIP 实施交付包。
7. 将交付包交给目标网站的页面 Skill，在真实仓库复用组件、接入视觉规范，运行工程检查，再单独审核上线。

可从 [Keyword Research Agent](https://keywordresearchagent-five.vercel.app) 下载人工批准的 Query Bank CSV，直接上传至本工作台的 Query Bank。支持 Query / query / keyword 列或每行一个 Query；每批最多 300 条，最多 80 个 Cluster。

「填入合成示例」只填充资料，不会伪装为真实运行结果。随后点击分析会真实调用 DeepSeek 并消耗 API 额度。

## 当前可以完成什么

- 真实 DeepSeek 聚类、Intent / ICP / Commercial / Funnel / P0-P2 判断、已有页面覆盖、页面映射建议。
- 优化已有页、Use Case、Comparison、Landing、Blog 的方向建议；不强制将不足条件的 Query 标成 P0。
- 完整 Brief、产品事实与证据引用、H1、Title、Description、Canonical、文案、CTA、FAQ、内部链接。
- 通用响应式 HTML 内容预览、隔离的浏览器预览、HTML 草稿下载、逐页修改与重试。
- 确定性基础 QA：元数据、标题结构、URL 格式、目标词精确覆盖、本批 route/title/正文重复、CTA 格式。
- 两次具名人工审核。输入改变会使 Gate 1 失效；Brief 改动会使 Gate 2 失效；基础 QA 的 Fail 阻止内容批准。
- 一次下载所有页面的 Brief Markdown/JSON、Metadata、HTML 预览、QA、页面映射、项目快照和 Page Skill 交接说明。

## 工作边界

浏览器版本交付的是**经过人工审核的页面内容及实施包**。通用 HTML 预览不是目标网站的生产组件实现；它始终使用 noindex，且不能证明品牌视觉、真实注册流程或目标站点工程质量。

以下项目固定显示 **Not run**，不会因模型说“通过”而改变：Design System integration、Component reuse、Mobile visual QA、Build、Type check、CI、Performance、PR / Production release。Gate 2 只批准内容交付，不能批准生产上线。

已有页面归属、自然语言、产品卖点、证据真伪、页面是否代表独立需求仍由人审核。输入来源标签只是引用，不能替代产品事实验证。全站重复内容、真实 URL 响应和性能需要在目标站点检查。

两个 Gate 是具名操作记录及内容版本校验，并非公司身份认证或法律签署。

## API Key 与项目保存

- 默认使用个人 DeepSeek Key。Key 只保存在当前表单内，随需要调用模型的请求发送；不写入 localStorage、项目快照、导出文件或服务器磁盘。
- 页面资料在处理时发送给 DeepSeek。只提交有权用于此工作流的内容。
- 使用服务器 Key 时，必须同时配置 DEEPSEEK_API_KEY 和 APP_ACCESS_TOKEN，并在工作台填写匹配的服务器访问口令。仅配置 DeepSeek Key 不会开放匿名调用。
- 服务器不持久保存项目。刷新或关页前点击「保存项目」，下次「导入项目」继续。项目文件含业务资料，请保管好。
- 普通请求上限 2 MB；八类资料合计上限 90,000 字符。每次模型调用最多等待 90 秒，每页独立请求，失败保留已完成页面。
- 模型为 deepseek-flash，关闭 thinking，使用 JSON Output。连接测试和实际生成均会产生供应商 API 费用。

## 本地运行与 Vercel

仅使用 Python 标准库：

```bash
python3 app.py
```

打开 http://127.0.0.1:8000。也可通过 PORT 修改端口。

在 Vercel 导入此 GitHub 仓库，Root Directory 使用仓库根目录。保留自动识别的 Python 设置；不要填写前端 Build Command 或 Output Directory。

- app.py 提供 WSGI 入口。
- pyproject.toml 有标准 [project] 和 [tool.vercel] entrypoint。
- vercel.json 将函数 maxDuration 设置为 300 秒。
- /api/health 返回版本、workflow=live 和服务器 Key 是否受保护配置就绪的布尔值，不返回任何密钥。
- /api/test、/api/analyze、/api/gate1、/api/brief、/api/render、/api/gate2、/api/import、/api/export 提供实际工作流。

## 目标仓库实施：CLI 与 Skill

浏览器交付包中的 page-skill-handoff.md 包含所提供的页面 Skill、视觉规则和工程验收清单。在 Codex 中使用本仓库的 SKILL.md 可进一步将工作接入真实代码仓库。

CLI 保留针对目标仓库的完整工作流（MVP 每批 3–5 页）：

```bash
python3 -m pip install -e .
export DEEPSEEK_API_KEY="your-key"

q2p analyze --config /path/to/run-config.json --run-dir .runs/mvp
q2p gate --run-dir .runs/mvp --gate 1 --decision approve --reviewer "Prudence"
q2p briefs --run-dir .runs/mvp
```

页面 Skill 完成真实实现后，填写 page-manifest.draft.json 的代码路径、Preview 和证据，移除 draft 标志，再运行：

```bash
q2p qa --run-dir .runs/mvp --manifest .runs/mvp/page-manifest.json
q2p gate --run-dir .runs/mvp --gate 2 --decision approve --reviewer "Prudence"
```

CLI 工程 Gate 2 与网页“内容交付”Gate 2 范围不同：CLI 的必要工程项若 Fail 或 Not run，会阻止生产交接。配置示例在 assets/templates/run-config.json；八类输入需使用真实文件或目录路径。

## 验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
node --check web/app.js
```

测试覆盖完整 API 工作流与 ZIP、CSV 衔接、人工 Gate、过期审核、模型错误、输入限制、HTML 注入防护、服务器 Key 保护和 CLI 状态机。自动测试中的模型使用明确的合成 fixture；真实 DeepSeek 调用和真实生产发布仍需要分别验证。

## License

[MIT](LICENSE)
