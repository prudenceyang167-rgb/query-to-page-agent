# Automated QA rubric

Run repository-native checks first, then inspect rendered pages. Record commands, tool outputs, screenshots, source paths, and URLs as evidence. Never infer a pass from absence of an error message.

## SEO

- unique title and meta description, within project rules;
- one descriptive H1 and logical H2 hierarchy;
- self-consistent canonical, route, sitemap, locale alternates, and robots;
- structured data is valid, conservative, and supported by visible content;
- crawlable contextual internal links in and useful links out;
- primary and supporting query concepts are covered naturally;
- no material duplication with other pages in the batch or existing site;
- essential copy and links remain available without animation/canvas execution.

## Product and conversion

- primary CTA exists, works, and reaches the intended signup/conversion path;
- value proposition states a specific job and outcome;
- mechanism and artifact proof support the promise;
- use case is clear to the target ICP without internal terminology;
- claims match verified capabilities and known limits;
- objections and FAQ are useful and do not invent product behavior.

## Engineering and design

- repository build, type check, relevant tests, and lint complete successfully;
- routes and malformed URL behavior work as intended;
- shared components are reused where semantics match;
- new abstractions are justified by actual repetition;
- desktop and mobile layouts are intentionally composed;
- no overflow, clipped text, broken focus order, unusable tap targets, or inaccessible contrast;
- meaningful images have useful alt text and decorative images have empty alt text;
- motion has a reduced-motion fallback;
- first-screen media is sized, optimized, and deferred appropriately;
- LCP/CLS or the project's equivalent performance evidence shows no material regression.

## Severity

- `Fail`: broken build/route/CTA, indexation error, unsupported claim, serious mobile/accessibility defect, canonical collision, or material performance regression.
- `Warning`: launchable only with an explicit tradeoff, missing non-critical proof, minor content/design concern, or a check with incomplete evidence.
- `Not run`: the check was skipped, unavailable, or blocked. Required checks remain blocking.
- `Pass`: observable evidence supports the acceptance criterion.

## Gate 2 view

For each page show:

1. target query, visitor decision, route, and primary CTA;
2. desktop and mobile preview links/screenshots;
3. claims and proof gaps;
4. Pass/Warning/Fail/Not run counts by category;
5. blocking failures and proposed remediation;
6. accepted warnings that require human confirmation.
