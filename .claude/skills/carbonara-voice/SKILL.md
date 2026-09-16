---
name: carbonara-voice
description: >
  The written voice of the carbonara repo — commit messages, PR descriptions,
  code comments, docstrings, AND Markdown documentation (README, the project
  spec/proposal, limitations notes). Mirrors this team's house register: terse,
  factual, no selling. Read this BEFORE writing a commit, opening a PR, adding a
  comment/docstring, or writing/editing any .md file. Pairs with carbonara-craft
  (code idioms).
---

# carbonara-voice

Prose in this repo is quiet and factual. It states what changed and why, never
sells, never over-explains. If an explanation is longer than the thing it
explains, cut the explanation.

## Commit messages

Loose conventional commits, lowercase, imperative-ish. Format:
`type(scope): summary` — scope optional, `(#N)` PR suffix added on merge.

- **Types:** `feat`, `fix`, `refacto`, `perf`, `test`, `chores`, `docs`, `security`. (`chores` plural and `refacto` are house forms — use them.)
- Scope is the area touched: `feat(fill-ladder):`, `fix(ingest):`, `test(core):`, `refacto(ledger):`.
- Summary is short and concrete — what changed, not a paragraph.

```text
feat(fill-ladder): grouped-median tier with support and dispersion guards
fix(ingest): reject duplicate upload by content hash instead of filename
test(normalize): cover 70/30 CO/PL composition parse
refacto(ledger): move event schema to a frozen dataclass
chores: bump duckdb to 1.1.3
```

Keep hygiene clean: no `wip`, `ud`, `nits`, or bare one-word commits — every
message names its change. An emoji is fine when it's apt (`🐍`), never required.

**Claude-authored commits** end with the trailer:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Pull requests

Lead with the substance. Small PR: a short bullet list of what changed. Larger
PR: one plain paragraph of the *why* and the shape of the change, then bulleted
sections.

```text
- Add grouped-median fill tier with support (N≥5) and dispersion (robust CV ≤ 0.30) guards
- Reject the median when it falls outside the plausibility band; fall through to reference constant
- Ledger + Bloodline lineage written per fill, with an uncertainty range
- Doctest covers tight / high-spread / sparse groups
```

Factual, no hype. Note follow-ups or known ceilings honestly. PR descriptions
end with:
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Comments

Sparse. The code carries the *what*; a comment earns its place only by
explaining the *why* — a non-obvious choice, a governance reason, a deliberate
limit.

```python
# Preserve the raw value+unit beside the normalized grams: provenance must be
# able to point at the original cell, not just the derived one.
component_weight_g = to_grams(raw_value, raw_unit)

# ponytail: linear supplier scan, fine at ~500 rows; build an index if it grows.
```

Do **not** narrate the obvious (`# increment counter`), leave commented-out
code, or restate the signature in words. Delete a comment before it goes stale.

## Docstrings

- **Modules:** one line stating the module's job.
  ```python
  """Parse and normalize free-text material and composition fields."""
  ```
- **Functions/classes:** one line of intent, in the imperative. Add args/returns
  detail only when the signature isn't self-evident.
  ```python
  def resolve_country(raw: str) -> str | None:
      """Resolve a raw country string to an ISO-3166 alpha-2 code, or None."""
  ```
- **NumPy-style sections** when they add value — a `References` block citing the
  source of reference data (Ecobalyse/ADEME, PEFCR), or `Examples` as a doctest.
  ```python
  """Load the material emission factors.

  References
  ----------
  [1] ADEME Base Empreinte / Ecobalyse — https://ecobalyse.beta.gouv.fr/
  """
  ```
- A docstring with a `>>>` example is a tested example — keep it correct
  (`carbonara-craft` covers the doctest-as-documentation style).

## Documentation & Markdown prose

Applies to the README, the project spec/proposal, the limitations note, and any
`.md` in the repo. Same register as the rest of the repo: write for a reviewer
skimming, state what is true, and stop.

- **Lead with substance.** Open with what the thing *is* and what it does, in a
  sentence or two — not a preamble, a mission statement, or a sales pitch.
- **Structure for scanning.** Short sections with plain headings; tables for
  structured comparisons (options, thresholds, boundaries); numbered lists for
  ordered procedures. One idea per paragraph.
- **Factual, not promotional.** Cut hype and self-congratulation ("the strongest
  story", "turns a weakness into strength", "maximally on-message"). State the
  design decision and its reason; let the reader judge. Prefer "X, because Y"
  over adjectives.
- **Say what it is *not*.** Name non-goals and limits explicitly — an honest
  boundary reads as judgment, and it keeps claims inside what the work proves
  ([§15 of the spec](../../../PROJECT-BRIEF.md)).
- **A standalone document has no changelog.** A spec or proposal states the
  current design as if it were always the plan. Don't narrate what an earlier
  draft said or what changed between versions — that belongs in git history, not
  the document.
- **No meta-framing.** A spec describes what the project *does* and what it will
  *show* — not that it is a portfolio, an application, or a role-scoped project.
  State scope boundaries as the project's own design choices ("deliberately out
  of scope"), never as some external role's requirements.
- **Code blocks in docs are real.** Every `>>>` block in the README is executed
  by pytest (`--doctest-glob=*.md`); keep it correct. Non-doctest snippets stay
  copy-pasteable and honest about prerequisites.
- **Cite reference data at the point of use.** When a number or factor comes from
  an external source, name the source (and version) inline or in a short
  references list — provenance applies to prose too.
