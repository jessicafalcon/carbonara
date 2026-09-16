---
name: carbonara-efficiency
description: >
  Token and compute efficiency for the carbonara build — how to spend Opus 4.8's
  effort and context well (upfront specs, subagents for fan-out, memory,
  strategic compaction) and how the connector caches deterministically at
  runtime (content-hash idempotency, on-disk caches for external APIs). Read
  this when a task will read across many files, when wiring an external data
  source, or when work spans many turns.
---

# carbonara-efficiency

Efficiency here has two faces: spending the model's context/tokens well while
*building*, and caching deterministically while the connector *runs*. Both
matter; neither may compromise the determinism invariants (`carbonara-correctness`).

## Build-time: spend Opus 4.8's effort where it pays

- **Run at `xhigh` effort** for coding/agentic work; drop to `high` only for cost-sensitive stretches. Opus 4.8 respects effort strictly — if reasoning looks shallow, raise effort rather than prompting around it.
- **Specify task + intent + constraints upfront.** This model is autonomous and literal; a well-scoped first turn beats dribbling context over many turns. State scope explicitly ("apply to every ladder tier, not just grouped-median") — it won't silently generalize.
- **Delegate fan-out reads to subagents.** When answering means sweeping many files or the reference repos/CSVs, spawn an `Explore`/`general-purpose` agent and keep the conclusion, not the file dumps. Don't also run the search yourself. Opus 4.8 spawns few subagents by default — ask explicitly when fan-out helps, and batch independent agents in one turn.
- **Don't re-read what's established.** The harness tracks file state after an edit; don't re-Read to "verify." Don't re-derive conventions — they live in the `carbonara-*` skills; invoke the skill instead of reconstructing the rule.
- **Use project memory** for durable, non-obvious facts (tooling decisions, house-style source) so they survive sessions instead of being re-explained.
- **Compact at breakpoints, not mid-task.** After a phase completes or after exploration-before-implementation, a manual `/compact` keeps context lean without dropping working state (the `strategic-compact` skill fires at these points).
- **Prompt caching is automatic** across turns in a session — structure work so the stable context (brief, skills) stays put and only the working delta changes.

## Runtime: cache deterministically, never recompute

The connector is idempotent by design; caching is how that promise is kept
cheaply — and every cache must be reproducible.

- **Content-hash idempotency (already in the pipeline).** Hash raw input bytes on ingest; a re-import of the same bytes is a no-op, not a recompute. This is the primary "don't do the work twice" mechanism ([§7.2](../../../PROJECT-BRIEF.md)).
- **On-disk cache for external calls.** Ecobalyse/ADEME factors and Open Supply Hub lookups are fetched once and cached to a versioned file under `references/` or a local cache dir, keyed by request. Mind rate limits; a cached response is the default, a live fetch the exception.
  - Factor tables ship as **versioned CSVs with a citation per row**, not live calls in the data path — this keeps the footprint reproducible and the factor version auditable.
  - For genuinely pure, repeated in-process lookups, `functools.lru_cache` is the one-line tool — but only on functions that are deterministic and side-effect-free.
- **Cache keys are explicit and stable.** No wall-clock, no random salt in a cache key — a cached result must be reproducible from the same inputs, or it violates determinism.
- **Don't build a cache framework.** A dict, an `lru_cache`, or a CSV on disk covers this. Reach for more only when a profiler says so (`# ponytail:` the shortcut if you cut one).
