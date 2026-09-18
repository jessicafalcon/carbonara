"""Phase-6 (stretch) analytics layer: the DuckDB SQL DAG + closed-form decomposition.

Lives outside ``carbonara/`` on purpose. It runs *downstream* of the connector,
consuming the pipeline's deterministic per-line footprints, so it stays off the
connector's guaranteed data path and never reimplements connector logic (brief
§11). Everything here is deterministic: DuckDB SQL over fixed input and closed-form
pandas arithmetic, no wall-clock, no unseeded randomness, no network.
"""

from __future__ import annotations
