---
name: ojo-query-to-page-agent
description: Turn an ICP, query bank, product evidence, sitemap, use-case taxonomy, page-building skill, design system, and SEO rules into a human-gated batch of 3–5 high-intent marketing pages. Use for query clustering and prioritization, query-to-page mapping, page briefs, implementation orchestration, preview QA, and PR-ready handoff; do not use for ungated mass publishing or unsupported product claims.
---

# OJO Query-to-Page Agent

Produce a small, reviewable batch of pages that earn distinct search intent and can be shipped through the target repository's normal review process. Optimize for business relevance and evidence, not page count.

## Load the run context

Before scoring queries, read [references/input-contract.md](references/input-contract.md). Resolve and inspect every supplied input. Current repository content is authoritative for existing coverage, product capabilities, routes, design conventions, and release checks.

If the configured page skill is `ojo-solution-pages`, read its complete `SKILL.md` and only the references it routes to for the current work. If the requested page skill is missing, stop before implementation and report the missing dependency; prioritization and briefing may still proceed.

Create a run directory outside production source, or under the repository's approved planning-artifact location. Use `scripts/workflow_state.py` to initialize and enforce the two gates when practical. Do not overwrite an existing run.

## Run the workflow

Read [references/prioritization-rubric.md](references/prioritization-rubric.md) for the scoring and page-mapping contract, and [references/artifact-contract.md](references/artifact-contract.md) for exact outputs.

1. Cluster queries by shared visitor decision, not lexical similarity alone. Separate clusters when the ICP, job, funnel stage, or required page experience differs.
2. Evaluate search intent, ICP relevance, commercial intent, funnel stage, current coverage, and cannibalization risk. Cite the supplied evidence behind non-obvious judgments. Label unknowns instead of inventing search volume, conversion, customer proof, or product capability.
3. Recommend `optimize-existing`, `create-use-case`, `create-comparison`, `create-landing`, or `create-blog`. Prefer improving an existing canonical page when it already satisfies the same visitor decision.
4. Assign P0/P1/P2. Select only 3–5 P0 candidates for the MVP, and create the Gate 1 packet. Do not draft or implement pages until a human explicitly approves Gate 1.
5. For each approved candidate, create a complete page brief. Claims must resolve to supplied product evidence; record proof gaps and copy assumptions.
6. Invoke the configured page skill for each page. Work as one controlled batch while keeping route changes independently reviewable. Reuse existing components, visual language, metadata helpers, and IA. Do not create a shared abstraction until at least two approved pages demonstrate the same semantic need.
7. Create previews and run the checks in [references/qa-rubric.md](references/qa-rubric.md). Classify every check as `Pass`, `Warning`, `Fail`, or `Not run`, with evidence. A missing check is `Not run`, never `Pass`.
8. Present Gate 2 with page direction, claims, copy, visual previews, CTA paths, QA summary, and unresolved warnings. Do not commit, push, open a PR, merge, deploy, publish, or release until the relevant explicit authorization and repository gates are satisfied.
9. After Gate 2 approval, prepare the PR using the repository's own contribution process. Treat production release as a separate human decision unless the user explicitly authorized it.

## Batch invariants

- MVP batch size is 3–5 approved pages; larger batches require a new run after the MVP metrics are reviewed.
- Each page owns one primary query cluster and one visitor decision.
- One canonical URL owns a given intent. Redirects, canonicals, and internal links must agree.
- No fabricated proof, customers, integrations, performance figures, rankings, or testimonials.
- Preserve the existing IA unless the human explicitly approves an IA change.
- Page implementation must reuse existing components where semantics match, be responsive, control first-screen cost, and pass the target repository's build and type checks.
- A PR is not a release. A preview is not indexable production content.

## Handoff

Return the run directory, selected cluster table, page-to-query map, briefs, implementation paths, preview links, QA matrix, gate decisions, and PR/release state. Record the MVP metrics defined in [references/metrics.md](references/metrics.md) so the next decision—repeat, revise, or expand to 10–20 pages—is evidence-based.
