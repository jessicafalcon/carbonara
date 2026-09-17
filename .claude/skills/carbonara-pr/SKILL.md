---
name: carbonara-pr
description: >
  How pull requests are structured and shipped in the carbonara repo — the PR
  title, the description sections, the pre-push checklist, and who to tag. Read
  this BEFORE opening or finalizing a phase PR. Governs PR structure and process;
  pairs with carbonara-voice (which governs the wording of the title and body).
---

# carbonara-pr

PR structure and process for this repo. `carbonara-voice` sets the *register*
(terse, factual, no selling); this skill sets the *shape* — what a PR contains and
what must be true before it is pushed. Adapted from a PR best-practices guide[1]
to this project's one-branch-one-PR-per-phase, single-maintainer workflow.

## Title

One line, the same `type(scope): summary` form as a commit (`carbonara-voice`),
naming the phase: `feat(phase-6): Lea + icanexplain two-vintage decomposition`.
Imperative, ≤ ~60 characters, no trailing period. The title answers *what
changes*; the body answers *why* and *how it was checked*.

## Description

Lead with substance. Structure it so a reviewer skimming sees the shape at once:

- **Why / what** — one short paragraph: the phase objective and the shape of the
  change. For a small PR, skip the paragraph and open with the bullets.
- **What changed** — a bulleted list, one line per logical change, in build order
  (mirrors the phase's ordered steps).
- **How it was tested** — the commands run and what they prove (`uv run pytest`,
  `uv run pre-commit run --all-files`; the exit-gate check for the phase). State
  results, do not imply them.
- **Known ceilings / out of scope** — deliberate limits and deferrals, named
  honestly (the spec's "Deliberately out of scope" section, condensed).
- **Refs** — the phase, and any issue (`Refs #<n>`).

End the body with the PR trailer from `carbonara-voice`:
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Before you push

The PR is opened only once these are true — the same gate each phase commits to:

- `uv run pytest` is green (unit + doctests, incl. the README).
- `uv run pre-commit run --all-files` is clean (uv-lock, ruff, ty).
- The phase's brief §16 exit gate passes on a clean re-run.
- No debug scaffolding, commented-out code, or stray print left in the diff.
- The diff is self-explanatory: a reviewer should not have to ask why a line is
  there. If a choice is non-obvious, a `# ponytail:` or a one-line comment already
  explains it (`carbonara-voice`), not the PR thread.
- House standards hold: ruff/ty clean, house idioms (`carbonara-craft`), every
  non-trivial unit has its check (`carbonara-tests`).

Push and open the PR at the exit gate — then **stop. The merge to `main` is the
user's call** (CLAUDE.md git workflow). Confirm before any force-push or history
rewrite.

## Tag the reviewer

Request review from the maintainer (the repo owner); do not tag broadly.

## Deliberately not adopted here

Two common PR practices do not fit this project's workflow, and are left out on
purpose:

- **Splitting into small / atomic PRs.** The workflow is deliberately one branch
  and one PR per phase (CLAUDE.md). Atomicity lives at the *commit* — one green,
  single-concern commit per step — not at the PR. A phase is reviewed as a whole.
- **Multi-reviewer feedback etiquette** (respond to every comment, resolve
  threads, explain each force-push to reviewers). A single maintainer reviews and
  merges; there is no multi-party review cycle to service. Keep the force-push
  discipline itself — confirm before rewriting pushed history — as a safety rule,
  not as reviewer etiquette.

---

[1] Pull Request Best Practices: A Comprehensive Guide for Developers —
https://virangaj.medium.com/pull-request-best-practices-a-comprehensive-guide-for-developers-679fdbafeb25
