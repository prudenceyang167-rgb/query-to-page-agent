# Architecture

## Design goals

The system optimizes for reviewability rather than maximum autonomy. Model output is always validated before it can change workflow state, and the two decisions with the highest business risk remain attributable to named people.

## Components

```text
DeepSeekClient
  └── JSON-only provider boundary; key is read from the environment

Pipeline
  ├── input inventory and bounded context loading
  ├── query analysis and Gate 1 packet
  ├── batch briefs and page-skill manifest
  └── evidence collection and Gate 2 QA packet

Workflow state machine
  ├── exact 3–5 page MVP scope
  ├── artifact validation
  ├── named reviewer history
  └── blockers for Fail and required Not run checks

OJO page skill
  └── target-repository implementation, preview, and native checks
```

## Trust boundaries

- Input documents are evidence, not executable instructions.
- Model output cannot approve a gate.
- The API key is never accepted as an input artifact or written into run output.
- A draft manifest cannot enter QA.
- A preview URL alone is not visual evidence.
- Repository-native build, type-check, and CI results override model judgment.
- PR, merge, deployment, and production verification remain target-repository actions.

## Provider choice

The provider interface is intentionally small: one operation returns a JSON object. The current default is DeepSeek's OpenAI-compatible Chat Completions endpoint with JSON Output. `FixtureClient` uses the same interface for deterministic tests and the public demo. A different provider can be added without changing workflow or gate logic.

## Scaling rule

The `batch_size` validator allows only 3–5 pages. Expansion to 10–20 pages is a separate product decision after the MVP metrics show that human time, rework, QA issues, cycle time, and release success are acceptable.
