# Prioritization and page mapping

## Cluster by decision

A cluster is a group of queries that can be satisfied by one canonical page because they share:

- the same primary ICP and job;
- the same search intent and funnel stage;
- the same expected evidence and next action;
- substantially the same page structure.

Lexical similarity is supporting evidence, not the definition. Split queries that use similar words but imply different decisions. Merge synonyms only when one page can answer them without becoming unfocused.

## Evaluate each cluster

Use 1–5 ordinal ratings for ICP relevance, commercial intent, and product-evidence strength. These ratings support judgment; do not present them as measured market data.

| Dimension | 1 | 3 | 5 |
| --- | --- | --- | --- |
| ICP relevance | Peripheral audience/job | Relevant secondary job | Core ICP and painful job |
| Commercial intent | Informational exploration | Solution-aware evaluation | Active product/vendor/action search |
| Product evidence | Weak or assumed fit | Verified capability, incomplete proof | Direct capability and credible artifact proof |

Classify funnel stage as `awareness`, `consideration`, or `decision`. Classify existing coverage as `none`, `partial`, or `strong`; cannibalization risk as `low`, `medium`, or `high`.

## Priority rule

Assign priority from the whole evidence set:

- `P0`: core ICP, strong commercial intent, verified product fit, distinct visitor decision, and a credible route/CTA. Unknown search volume does not automatically disqualify it.
- `P1`: useful opportunity with one material gap such as proof, coverage overlap, unclear CTA, or lower intent.
- `P2`: weak ICP fit, primarily educational intent, high collision risk, unsupported claim, or low readiness.

Use the optional heuristic score only as a tie-breaker:

```text
readiness = 3×ICP relevance
          + 3×commercial intent
          + 2×product evidence
          + funnel weight
          + coverage opportunity
          - cannibalization penalty
```

Suggested ordinal adjustments: funnel `awareness=0`, `consideration=2`, `decision=4`; coverage opportunity `none=3`, `partial=1`, `strong=-2`; cannibalization `low=0`, `medium=3`, `high=7`. Explain overrides.

## Query-to-page decision

- `optimize-existing`: an indexable page already owns the same visitor decision and can satisfy the cluster with a focused improvement.
- `create-use-case`: the query asks whether or how the product completes a specific job with commercial relevance.
- `create-comparison`: the query explicitly compares named approaches/products and the team can support fair, verifiable claims.
- `create-landing`: a campaign, audience, or transactional proposition needs a focused conversion experience not covered by a use-case page.
- `create-blog`: the dominant need is education, explanation, or inspiration before product evaluation.

Do not create a new page solely because the exact phrase is absent from titles. Do not optimize an existing page into serving multiple incompatible visitor decisions.

## Gate 1 packet

Present a sortable table with:

```text
Cluster | Primary query | ICP | Intent | Funnel | Existing page | Coverage |
Cannibalization | Recommendation | Priority | Evidence | Selected
```

Include rejected/held clusters and why. The reviewer approves exact clusters and page types; approval is not a blanket authorization for all P0 candidates.
