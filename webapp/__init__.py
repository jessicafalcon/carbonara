"""A thin web transport over the connector: upload → review → re-run.

This package holds no business logic. It renders and routes; every value it shows
comes from ``carbonara.pipeline.run`` and ``carbonara.review.ReviewQueue``, which
stay the single source of truth. It lives outside ``carbonara/`` on purpose — the
determinism guard governs the connector, not this transport (backlog item 4).
"""

from __future__ import annotations
