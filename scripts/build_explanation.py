"""Build and print the v1→v2 footprint explanation, and write it as an artifact.

Runs both vintages through the connector, builds the production-weighted mart via
the DuckDB SQL DAG, decomposes the change with icanexplain, and checks the
explanation: it reconciles to the observed delta, the intensity effect sits on the
planted factor bump alone, and it agrees with the planted ground-truth
decomposition. Writes a JSON artifact (not committed) and prints a short summary.

Run ``python scripts/build_explanation.py [output.json]`` (default
``build/explanation.json``).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys

from analytics.explain import Decomposition, decompose, intensity_from_factor_change
from analytics.mart import footprint_mart, truth_mart

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_FACTOR_MATERIAL = "polyester"  # the only material whose factor changed v1→v2


def _summary(label: str, decomposition: Decomposition, mart_intensity: float) -> dict[str, object]:
    return {
        "source": label,
        "f_from": round(decomposition.f_from, 3),
        "f_to": round(decomposition.f_to, 3),
        "observed_delta": round(decomposition.observed_delta, 3),
        "intensity_effect": round(decomposition.intensity_effect, 3),
        "volume_mix_effect": round(decomposition.volume_mix_effect, 3),
        "residual": decomposition.residual,
        "reconciles": decomposition.reconciles(),
        "intensity_matches_factor_bump": abs(decomposition.intensity_effect - mart_intensity) < 1e-6,
    }


def build_explanation() -> dict[str, object]:
    """Decompose the pipeline and the ground-truth marts and check agreement."""
    pipeline, truth = footprint_mart(), truth_mart()
    pipeline_dec, truth_dec = decompose(pipeline), decompose(truth)

    def gap(observed: float, reference: float) -> float:
        return abs(observed - reference) / max(abs(reference), 1.0)

    return {
        "pipeline": _summary(
            "pipeline", pipeline_dec, intensity_from_factor_change(pipeline, material=_FACTOR_MATERIAL)
        ),
        "ground_truth": _summary(
            "ground_truth", truth_dec, intensity_from_factor_change(truth, material=_FACTOR_MATERIAL)
        ),
        "agreement_vs_ground_truth": {
            "delta_gap": round(gap(pipeline_dec.observed_delta, truth_dec.observed_delta), 4),
            "intensity_gap": round(gap(pipeline_dec.intensity_effect, truth_dec.intensity_effect), 4),
            "volume_mix_gap": round(gap(pipeline_dec.volume_mix_effect, truth_dec.volume_mix_effect), 4),
            "note": "residual gaps are propagated fill error; the two vintages fill different blanked cells",
        },
        "by_material": {
            "pipeline": pipeline_dec.by_material.to_dict(orient="records"),
            "ground_truth": truth_dec.by_material.to_dict(orient="records"),
        },
    }


def main(out: pathlib.Path) -> None:
    explanation = build_explanation()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(explanation, indent=2, default=_json_default), encoding="utf-8")

    pipeline = explanation["pipeline"]
    assert isinstance(pipeline, dict)
    print(f"wrote {out}")
    print(
        f"ΔF = {pipeline['observed_delta']:,} kgCO2e"
        f"  =  intensity {pipeline['intensity_effect']:,}  +  volume/mix {pipeline['volume_mix_effect']:,}"
    )
    matches = pipeline["intensity_matches_factor_bump"]
    print(f"reconciles={pipeline['reconciles']}  intensity_matches_factor_bump={matches}")


def _json_default(value: object) -> object:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    raise TypeError(f"not JSON-serializable: {type(value)!r}")


if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else _ROOT / "build" / "explanation.json"
    main(target)
