# Run artifact contract

Use this layout unless the target repository requires a different approved location:

```text
run/
├── config.json
├── state.json
├── input-inventory.md
├── prioritization.json
├── gate-1.md
├── page-map.md
├── brief-index.json
├── briefs/
│   └── <page-id>.md
├── page-manifest.draft.json
├── page-manifest.json
├── qa/
│   ├── qa-report.json
│   └── visual-review.md
├── gate-2.md
└── metrics.json
```

## Prioritization JSON

Top-level key `clusters` contains objects with:

```text
cluster_id, cluster_label, primary_query, member_queries, icp,
search_intent, funnel_stage, icp_relevance, commercial_intent,
product_evidence, existing_page, coverage, cannibalization_risk,
recommendation, priority, rationale, evidence, selected
```

Keep evidence as source pointers or short factual notes. `selected: true` means proposed for Gate 1; it is not approval.

## Page map

For every approved cluster, record:

```text
Query cluster | ICP | Intent | Existing page | Recommendation | Page type |
Route | Primary CTA | Priority | Brief
```

## Page brief

Every brief must include:

- target query and supported secondary queries;
- search intent, funnel stage, ICP, visitor decision, and pain;
- OJO differentiation tied to verified capabilities;
- proposed route and page type;
- H1, title, meta description, canonical, robots, and schema plan;
- section-by-section structure and core copy;
- feature-to-benefit-to-proof mapping;
- use-case workflow and artifact evidence;
- primary/secondary CTA labels and destinations;
- FAQ based on real objections, not keyword stuffing;
- internal links in and out, with anchor intent;
- localization scope;
- assumptions, proof gaps, and prohibited claims;
- acceptance criteria.

## Page manifest

Top-level key `pages` contains one object per Gate 1-approved page:

```text
page_id, cluster_id, target_query, page_type, action, route,
existing_page, brief_path, implementation_paths, preview_url
```

The manifest represents the batch scope. Do not silently add pages after Gate 1.

The briefing stage emits `page-manifest.draft.json`. The page-building skill must fill `implementation_paths`, `preview_url`, and optional `evidence_paths`, then remove the top-level `draft` flag. Automated QA refuses a draft manifest.

## QA report JSON

Use top-level `pages`; each page contains `checks`. Each check contains:

```json
{
  "category": "seo",
  "name": "unique-title",
  "status": "Pass",
  "evidence": "Rendered title and source path",
  "owner": "agent",
  "remediation": ""
}
```

Allowed status values are `Pass`, `Warning`, `Fail`, and `Not run`. The batch cannot pass Gate 2 with any `Fail` or required `Not run` check.

Use these required category/name keys so the state helper can detect missing evidence:

```text
seo: title, meta-description, headings, canonical, internal-links, schema,
     query-coverage, duplicate-content
product-conversion: cta, signup-path, core-value-proposition, use-case-clarity
engineering: mobile, component-reuse, build, type-check, ci, performance
```

## Gate records

Each gate record contains the decision, reviewer, timestamp, exact approved scope, notes, warnings accepted, and rejected items. Human approval must be explicit and attributable; the agent cannot approve its own gate.
