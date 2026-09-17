"""Decompose the v1→v2 change in the production-weighted footprint (icanexplain).

The mart's catalog total ``F = Σ mass_kg × factor`` moves between vintages for two
reasons, and icanexplain's ``SumExplainer`` splits the change into exactly those:
with ``count = mass_kg`` and ``fact = factor``, the **intensity** effect (its
``inner``) is the change in emission factor and the **volume/mix** effect (its
``mix``) is the change in production mass and its material composition (brief §9).
The two contributions reconcile to the observed delta by construction; a
reconciliation residual records that it holds.

icanexplain runs through ibis; ibis's duckdb backend pins an old duckdb, so we
pin its deterministic pandas backend here (the connector runs a newer duckdb).
"""

from __future__ import annotations

import dataclasses

import ibis
import icanexplain as ice
import pandas as pd

__all__ = ["Decomposition", "decompose", "intensity_from_factor_change"]

_GROUP = "material"
_PERIOD = "vintage"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class Decomposition:
    """The v1→v2 footprint change split into intensity and volume/mix effects.

    ``by_material`` carries the per-material split (columns ``material``,
    ``intensity_effect``, ``volume_mix_effect``); the scalars are its column sums
    plus the observed delta. ``residual = observed_delta − (intensity +
    volume_mix)`` is ~0 when the explanation reconciles.
    """

    period_from: str
    period_to: str
    f_from: float
    f_to: float
    observed_delta: float
    intensity_effect: float
    volume_mix_effect: float
    residual: float
    by_material: pd.DataFrame

    def reconciles(self, *, tol: float = 1e-6) -> bool:
        """True when the effects sum to the observed delta within ``tol`` (relative)."""
        scale = max(abs(self.observed_delta), 1.0)
        return abs(self.residual) <= tol * scale


def intensity_from_factor_change(
    mart: pd.DataFrame, *, material: str, period_from: str = "v1", period_to: str = "v2"
) -> float:
    """The exact intensity effect for one material: ``mass_from × (factor_to − factor_from)``.

    icanexplain weights the intensity (inner) effect by the before-period count, so
    this closed form equals that material's ``intensity_effect`` exactly — a check
    that ties the number to the known factor change (brief §9).
    """
    rows = mart.set_index([_PERIOD, _GROUP])
    mass_from = float(rows.loc[(period_from, material), "mass_kg"])
    factor_from = float(rows.loc[(period_from, material), "factor"])
    factor_to = float(rows.loc[(period_to, material), "factor"])
    return mass_from * (factor_to - factor_from)


def _use_pandas_backend() -> None:
    """Pin ibis to its pandas backend (its duckdb backend pins duckdb<1.2)."""
    ibis.set_backend(ibis.pandas.connect({}))


def decompose(mart: pd.DataFrame, *, period_from: str = "v1", period_to: str = "v2") -> Decomposition:
    """Split the ``period_from``→``period_to`` change in ``F`` into its two effects.

    ``mart`` is the production-weighted basis: one row per ``vintage`` × ``material``
    with ``mass_kg`` (count) and ``factor`` (fact). Returns per-material and total
    intensity (factor) and volume/mix (mass) effects, with a reconciliation residual.
    """
    _use_pandas_backend()
    frame = mart[mart[_PERIOD].isin((period_from, period_to))]
    explanation = ice.SumExplainer(fact="factor", period=_PERIOD, group=_GROUP, count="mass_kg")(frame)

    by_material = (
        explanation.reset_index()
        .rename(columns={"inner": "intensity_effect", "mix": "volume_mix_effect"})
        .loc[:, [_GROUP, "intensity_effect", "volume_mix_effect"]]
        .sort_values(_GROUP)
        .reset_index(drop=True)
    )

    totals = frame.assign(footprint=frame["mass_kg"] * frame["factor"]).groupby(_PERIOD)["footprint"].sum()
    f_from, f_to = float(totals.get(period_from, 0.0)), float(totals.get(period_to, 0.0))
    intensity = float(by_material["intensity_effect"].sum())
    volume_mix = float(by_material["volume_mix_effect"].sum())
    observed_delta = f_to - f_from

    return Decomposition(
        period_from=period_from,
        period_to=period_to,
        f_from=f_from,
        f_to=f_to,
        observed_delta=observed_delta,
        intensity_effect=intensity,
        volume_mix_effect=volume_mix,
        residual=observed_delta - (intensity + volume_mix),
        by_material=by_material,
    )
