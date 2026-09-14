# OJO Query-to-Page Agent

一个面向高意图 SEO 页面批量生产的 Codex Agent/Skill。它把 Query Bank 到 PR-ready 页面之间最耗人工的判断和交付环节串成一个可审计工作流，并用两个 Human Gate 保留关键业务决策。

> Personal portfolio project by prudenceyang167-rgb. The repository contains only workflow logic and synthetic examples—no private query bank, customer data, credentials, unpublished metrics, or copied product source.

## 它解决什么

```text
ICP + Query Bank + Product Evidence + Sitemap
                    ↓
        Cluster / Intent / Coverage / Risk
                    ↓
            Human Gate 1: 做哪些页
                    ↓
         Brief → Page Skill → 3–5 pages
                    ↓
        SEO / Conversion / Mobile / Build QA
                    ↓
           Human Gate 2: 是否交付
                    ↓
                 PR-ready
```

Agent 会输出可追踪的 Query 优先级、Query → Page 映射、完整页面 Brief、批量页面清单、Preview/QA 证据和 MVP 效率指标。它不会替人批准页面方向、产品卖点或最终上线。

## MVP 范围

- 一次只处理 3–5 个获批的高意图页面。
- 支持 `optimize-existing`、`create-use-case`、`create-comparison`、`create-landing`、`create-blog` 五类决策。
- Gate 1 未通过不能生成页面；Gate 2 有 `Fail` 或必要项 `Not run` 时不能进入 PR-ready。
- 页面实现通过目标仓库已有的 Page Skill 完成；对 OJO 项目默认使用 `ojo-solution-pages`。
- PR、合并和上线仍遵守目标仓库自己的权限与发布流程。

## 仓库结构

```text
SKILL.md                         Agent 主工作流
agents/openai.yaml               Codex 展示与默认调用信息
references/                      输入、优先级、产物、QA、指标规范
scripts/workflow_state.py        双 Gate 状态机与 JSON 校验
assets/templates/                Run config、Query Bank、Page Brief 模板
examples/synthetic/              不含真实业务数据的演示输入
tests/                           状态机自动测试
```

## 在 Codex 中使用

把仓库作为 Skill 安装或放到项目可发现的 skills 目录，然后调用：

```text
Use $ojo-query-to-page-agent to turn this query bank into a gated batch of 3–5 high-intent pages.
```

Agent 会先读取八类输入并停在 Gate 1。只有明确批准候选 Cluster 后才会继续生成 Brief 和页面。

## 本地验证状态机

只依赖 Python 标准库：

```bash
python3 -m unittest discover -s tests -v
```

用合成数据初始化一次演示 Run：

```bash
python3 scripts/workflow_state.py init \
  --config examples/synthetic/config.json \
  --run-dir .runs/demo

python3 scripts/workflow_state.py record-analysis \
  --run-dir .runs/demo \
  --analysis examples/synthetic/prioritization.json
```

查看状态：

```bash
python3 scripts/workflow_state.py status --run-dir .runs/demo
```

Gate 决策必须由具名人类 Reviewer 提交。演示数据仅用于校验工作流，不代表真实搜索机会、产品能力或发布建议。

## 10–20 页扩展条件

先完成一个 3–5 页 MVP，并记录单页人工耗时、Agent 自动完成率、QA Issue 数量、生产周期和上线成功率。只有当模板没有系统性失败、人工返工下降且跨页面复用成立时，才新建 10–20 页 Batch。

## License

[MIT](LICENSE)
