# Input contract

The agent accepts paths or directly supplied content for the following eight inputs. Record the resolved source and freshness in `input-inventory.md`.

| Input | Minimum useful content | Blocking condition |
| --- | --- | --- |
| ICP | Roles, context, pains, desired outcomes, exclusions | No identifiable audience or job |
| Query bank | Query text; optional volume, difficulty, market, language, and source | No queries |
| Product capability | Verified mechanisms, outputs, limits, and supporting source | No evidence for the intended claim |
| Existing sitemap | Canonical routes, page type, locale, and indexability | Cannot assess coverage or collision |
| Use-case taxonomy | Allowed use cases and their boundaries | Page classification remains ambiguous |
| Page skill | Path/name of the implementation skill | Blocks implementation, not analysis |
| Homepage/design system | Current source, components, tokens, layouts, and mobile behavior | Blocks visual implementation |
| SEO rules | Metadata, canonical, schema, sitemap, robots, link, and localization rules | Blocks release readiness |

## Recommended run config

Use JSON so the bundled state helper works without third-party packages.

```json
{
  "run_name": "2026-09-high-intent-use-cases",
  "batch_size": 3,
  "target_repository": "/absolute/path/to/site-repository",
  "inputs": {
    "icp": "inputs/icp.md",
    "query_bank": "inputs/query-bank.csv",
    "product_capabilities": "inputs/product-capabilities.md",
    "sitemap": "inputs/sitemap.csv",
    "use_case_taxonomy": "inputs/use-cases.md",
    "page_skill": ".agents/skills/ojo-solution-pages/SKILL.md",
    "design_system": "apps/homepage",
    "seo_rules": "inputs/seo-rules.md"
  }
}
```

`batch_size` must be between 3 and 5 for an MVP run. Relative input paths resolve from the config file's directory. The state helper checks the contract and records paths, but the agent must still inspect and interpret the content.

## Query-bank columns

Only `query` is required. Useful optional columns are:

```text
query,market,language,volume,difficulty,source,notes
```

Do not treat absent volume or difficulty as zero. Mark the value unknown and avoid false numerical precision.

## Input inventory

For each source record:

- source path or URL;
- last-modified or retrieval date when available;
- owner or provenance when supplied;
- scope used in this run;
- freshness or coverage warning;
- whether it contains claims safe to publish.

Never copy credentials, private customer data, unpublished metrics, or unrelated proprietary material into the run artifacts.
