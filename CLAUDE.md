# CLAUDE.md

Session instructions for the carbonara connector. Read this first, every session.
The full design and the phase plan live in [PROJECT-BRIEF.md](PROJECT-BRIEF.md)
(§16 is the phase-by-phase build plan); this file is *how we work*, not *what we
build*.

## Repo map

```text
carbonara/        the connector package (the data path — kept deterministic)
tests/            cross-module + README/behavior tests
references/       versioned reference/factor CSVs, one citation per row
fixtures/         generated fixtures + retained ground truth
specs/            one spec per phase, named after its branch (specs/<branch>.md)
PROJECT-BRIEF.md  the design + phased build plan (§16)
CLAUDE.md         this file — the session workflow
.claude/skills/   the build-standard skills (below)
.claude/hooks/    determinism guard + ruff-on-edit (fire automatically)
pyproject.toml    uv/ruff/ty/pytest config     uv.lock  pinned deps
```

## Core principles (in priority order)

1. **Determinism first.** Same input + same rule versions ⇒ byte-identical
   output, lineage, and ledger. No LLM, no unseeded randomness, no wall-clock, no
   env reads in `carbonara/`. This outranks everything else — a faster or shorter
   change that breaks it does not land. (`carbonara-correctness` §1; the
   determinism guard enforces it on edit.)
2. **Portability.** Runs on any machine with `uv` and Python ≥ 3.11, offline.
   Deps pinned in `uv.lock`; reference data versioned in-repo; no absolute paths,
   no machine-specific config, no network in the data path or the tests. Prefer
   stdlib and already-installed deps over new ones.
3. **Results backed by data.** Every published number traces to a rule, a source
   row, and a factor version (ledger + Bloodline spine). Filled values carry an
   uncertainty range; fill accuracy is *measured* against ground truth, never
   claimed. Stay inside the claims boundaries (brief §15).
4. **Clean code, tested, version-controlled.** Small single-concern modules,
   typed, one runnable check per non-trivial unit, small green commits. This is
   the house baseline, not a nice-to-have.

## Communication

- **Result first:** what changed / passed / failed, then the details.
- Plain English, short sentences. No task restatement, no "I will now…", no
  closing summary that repeats the middle.
- One sentence if it fits; explanations ≤ 4 sentences.
- **Report after a task:** files touched, commands run, result, open risks, next
  step — nothing else.

## The build harness

### Skills — launch the matching one *before* the work

| Skill | Launch before… |
|---|---|
| `carbonara-craft` | writing/refactoring any Python, choosing a dependency |
| `carbonara-correctness` | landing anything in the data path, adding a rule, reviewing |
| `carbonara-tests` | writing or changing any test |
| `carbonara-voice` | writing a commit, PR, comment/docstring, or any `.md` file |
| `carbonara-pr` | opening or finalizing a phase PR (structure/process; pairs with `carbonara-voice`) |
| `carbonara-efficiency` | fan-out reads, wiring an external source, long multi-turn work |

### Hooks — fire automatically, no action needed

- **ruff-on-edit** (PostToolUse, any `*.py`): formats + lint-fixes the edited file.
- **determinism-guard** (PostToolUse, `carbonara/*.py`): blocks LLM calls,
  unseeded randomness, wall-clock, `uuid4`, and env reads in the connector
  package. If it fires on legitimately non-deterministic code, that code belongs
  *outside* `carbonara/` (a generator or script), or the value should be injected.

## Git workflow — one branch + one PR per phase

- **Phase 0 was committed directly to `main`** (repo bootstrap). From **Phase 1
  on, every phase gets its own branch and one PR.**
- Branch name: `phase-<n>-<slug>` (e.g. `phase-1-contract-and-fixture`).
- **Start a phase (local):**
  ```sh
  git switch main && git pull --ff-only
  git switch -c phase-<n>-<slug>
  ```
- **Spec first, as actionable steps.** Break the phase into an ordered list of
  actionable steps in `specs/phase-<n>-<slug>.md` (mirrors brief §16, authored
  with `carbonara-voice`), before implementation. The spec is the first step and
  its own commit. **Write it as a senior data architect:** choose the simplest,
  most elegant solution that meets the contract — boring over clever — and cut
  anything speculative. No overengineering.
- **One step = one commit.** Work the phase step by step; each step is a single
  atomic commit, made once it is green (`uv run pytest` + `uv run pre-commit run
  --all-files` clean). Never bundle a whole phase into one commit; never commit
  red or unrelated changes together.
- **At the exit gate.** When the brief §16 exit gate is green, push the branch
  and open/finalize the PR (`carbonara-voice`), then **stop — do not merge. The
  merge to `main` is the user's call.** Push and PRs are fine at any point;
  only the merge waits for the user.
- **Update Current status after every PR and every merge** (in the same change) —
  the phase, branch, open PR, and the next spec step. A new session resumes from
  it, so it must be current.
- Confirm before force-push, history rewrite, or anything else hard to undo.

### Commit best practices

- **Atomic.** One logical change per commit — the step, nothing bundled in.
- **Commit often**, each time a step is green; small commits are easier to read,
  review, and revert.
- **Never commit broken or unrelated code.**
- **Subject:** imperative, present tense, ≤ 50 characters, no trailing period —
  "Add contract dataclass", not "Added…" or "Fixes bug…". The house
  `type(scope): summary` form and the `Co-Authored-By` trailer are in
  `carbonara-voice`.
- **Body (only when it adds something):** a blank line, then *what* changed and
  *why* (and any side effects) — not *how*; the diff already shows how.
- **Footer:** reference the phase PR or issue when relevant (`Refs #<n>`).

## How the tooling fires across a phase

1. Read this file + the brief's phase section; recall project memory.
2. Branch off `main` (local); write `specs/<branch>.md` as an ordered list of
   actionable steps (launch `carbonara-voice`) — the spec is the first commit.
3. Work step by step — launch `carbonara-craft` / `carbonara-correctness` /
   `carbonara-tests` as you go; the PostToolUse hooks run on every `.py` edit.
4. Each step, once green (`uv run pytest`, then `uv run pre-commit run
   --all-files`): one atomic commit.
5. At the exit gate: push the branch, open/finalize the PR, and stop — the user
   merges. Update Current status once told it's merged.

## Project tooling

```sh
uv sync                              # install deps + dev tools (ruff, ty, pytest, pre-commit)
uv run pytest                        # unit tests + doctests (incl. README)
uv run ruff format . && uv run ruff check --fix .
uv run ty check .
uv run pre-commit run --all-files    # uv-lock, ruff, ty
pre-commit install --hook-type pre-push   # run the gate on push (once, local)
```

Effort: run Opus 4.8 at **xhigh** for this project's coding/agentic work.

## Current status

- **Phase 0 — build harness + repo skeleton: done** (on `main`).
- **Phase 1 — contract + fixture generator: done** (merged, PR #2).
- **Phase 2 — ingest + schema-drift gate: done** (merged, PR #3).
- **Phase 3 — normalize + validate + anomaly events: done** (merged, PR #4).
- **Phase 4 — fill ladder + rule ledger + Bloodline lineage: done** (merged, PR #5).
- **Phase 5 — footprint + brand-facing view + provenance drawer: done** (merged, PR #6).
  Footprint costs `weight_kg × factor(material)` with factor source/version, mapping
  confidence, observed-vs-filled share, and an uncertainty range; each estimate carries
  a ledger event + Bloodline source; unresolved material is flagged (not costed).
  Exact Ecobalyse `cch` factors (`scripts/fetch_factors.py`, token-gated), reference-data
  content-hashing in the run id (`reference_digest`), the slate-dashboard view
  (`carbonara/view.py`), and the trace journey all landed.
- **Phase 6 — (stretch) Lea DAG + icanexplain on two vintages: in progress.**
  Branch `phase-6-lea-and-icanexplain`. Scope confirmed with the user: **both**
  libraries, decomposing a **production-weighted** catalog total `F = Σ qty × weight_kg ×
  factor` (quantity does not enter the Phase-5 per-line footprint, so a real volume
  effect needs this new mart aggregate). The **v2 (2025)** vintage is a deterministic
  transform of v1's clean skeleton (per-archetype volume multiplier + a named
  material-mix shift + 2025 stamp), so the planted ground-truth decomposition stays
  exactly known. Architecture: the carbonara pipeline stays the deterministic core;
  a new `analytics/` package (outside `carbonara/`, carrying the heavier deps) runs
  both vintages through the pipeline, a tiny Lea staging→core→mart DuckDB DAG rolls
  per-line footprints up to `F` by material×vintage, and icanexplain decomposes ΔF into
  volume/mix/intensity — reconciled to the observed delta and validated against
  `decomposition_truth.csv`, both within tolerance. Spec + 8 steps in
  `specs/phase-6-lea-and-icanexplain.md`. Also adds a `carbonara-pr` PR-writing skill.
  **Next: step 1 committed (spec + this status); step 2 — the PR-writing skill.**

_Update after every PR and merge (rule above): phase, branch, open PR, next spec step._
