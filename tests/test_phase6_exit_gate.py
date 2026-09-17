"""Phase-6 exit gate (brief §16): a repeatable metric with a reconciled,
ground-truth-validated explanation.

Walks the whole journey in one place: generate the two vintages deterministically,
run both through the connector, build the production-weighted mart via the DuckDB
SQL DAG, decompose the v1→v2 change with icanexplain, and confirm it reconciles to
the observed delta and matches the planted ground truth — all byte-reproducible.
"""

from __future__ import annotations

import pathlib

import pandas as pd

from analytics.explain import decompose, intensity_from_factor_change
from analytics.mart import footprint_mart, truth_mart
from fixtures import generate

_POLYESTER = "polyester"  # the one material whose factor was revised v1→v2


def test_vintage_generation_is_byte_reproducible(tmp_path: pathlib.Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    generate.write_fixtures(first)
    generate.write_fixtures(second)
    for name in ("bom_v2.csv", "ground_truth_v2.csv", "decomposition_truth.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_metric_is_repeatable() -> None:
    # The mart and the decomposition reproduce across a full re-run.
    pd.testing.assert_frame_equal(footprint_mart(), footprint_mart())
    first, second = decompose(footprint_mart()), decompose(footprint_mart())
    assert (first.observed_delta, first.intensity_effect, first.volume_mix_effect) == (
        second.observed_delta,
        second.intensity_effect,
        second.volume_mix_effect,
    )


def test_explanation_reconciles_and_matches_ground_truth() -> None:
    mart = footprint_mart()
    pipeline = decompose(mart)
    truth = decompose(truth_mart())

    # Reconciles to the observed delta (the §16 gate).
    assert pipeline.reconciles()
    assert abs((pipeline.intensity_effect + pipeline.volume_mix_effect) - pipeline.observed_delta) < 1e-6

    # The intensity effect is the planted factor bump, on polyester alone.
    intensity = pipeline.by_material.set_index("material")["intensity_effect"]
    assert abs(intensity[_POLYESTER]) > 1.0
    assert intensity.drop(_POLYESTER).abs().max() < 1e-6
    assert abs(pipeline.intensity_effect - intensity_from_factor_change(mart, material=_POLYESTER)) < 1e-6

    # Validated against the planted ground-truth decomposition: same direction on
    # every effect (magnitudes carry propagated fill error, reported separately).
    assert (pipeline.intensity_effect > 0) == (truth.intensity_effect > 0)
    assert (pipeline.volume_mix_effect < 0) == (truth.volume_mix_effect < 0)
    assert (pipeline.observed_delta < 0) == (truth.observed_delta < 0)
    assert truth.reconciles()
