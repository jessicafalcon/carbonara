"""Phase-6 (stretch) analytics layer: the Lea DAG + icanexplain decomposition.

Lives outside ``carbonara/`` on purpose. It runs *downstream* of the connector,
consuming the pipeline's deterministic per-line footprints, so its heavier
dependencies (lea, icanexplain, ibis) stay off the connector's guaranteed data
path and Lea never reimplements connector logic (brief §11). Everything here is
still deterministic: DuckDB SQL over fixed input and ibis/pandas math, no
wall-clock, no unseeded randomness, no network.
"""

from __future__ import annotations
