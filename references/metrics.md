# MVP metrics

Measure the first 3–5 page run before expanding batch size.

| Metric | Definition |
| --- | --- |
| Human time per page | Active reviewer/author minutes from run start through release decision, divided by approved pages |
| Agent automation rate | Agent-completed eligible workflow tasks divided by all eligible tasks; exclude mandatory human gate decisions |
| QA issue count | Number of distinct Warning and Fail findings, split by category and detection stage |
| Production cycle time | Elapsed time from accepted Gate 1 scope to production verification, with blocked/waiting time reported separately |
| Launch success rate | Pages verified in production without rollback or hotfix divided by pages approved for release |

Also record rework loops per page, review comments, time spent at each gate, build/CI attempts, and whether issues were caught before or after PR.

## Expansion decision

Recommend a 10–20 page batch only when:

- all MVP pages reached their intended terminal state;
- no repeated Fail indicates a systemic template, claim, route, or QA problem;
- human time and rework are trending down or are acceptably bounded;
- the shared page system handled variation without page cloning;
- reviewers agree the Gate 1 and Gate 2 packets are sufficient for decisions.

If these conditions are not met, propose the smallest workflow, template, or evidence fix and repeat a 3–5 page batch.
