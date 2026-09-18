"""Decompose the v1→v2 change in the production-weighted footprint (closed form).

The mart's catalog total ``F = Σ mass_kg × factor`` moves between vintages for two
reasons, and the decomposition splits the change into exactly those. For each
material the **intensity** effect is the emission-factor change weighted by the
before-period mass, ``mass_from × (factor_to − factor_from)``; the **volume/mix**
effect is the rest of that material's footprint delta — the change in production
mass and material composition (brief §9). The two sum to the material's observed
delta by construction, so they reconcile to the total delta exactly; the
reconciliation residual records that it holds.

This is the standard sum decomposition — intensity weighted by the before-period
count — computed directly from the mart. It replaces the icanexplain/ibis
dependency, whose ``SumExplainer`` produced the same split by construction (see
BACKLOG item 5): the closed form is ``intensity_from_factor_change`` summed over
materials, with the remainder as volume/mix.
"""

from __future__ import annotations

import dataclasses

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

    The intensity (inner) effect is weighted by the before-period mass, so this
    closed form is that material's ``intensity_effect`` — a check that ties the
    number to the known factor change (brief §9).
    """
    rows = mart.set_index([_PERIOD, _GROUP])
    mass_from = float(rows.loc[(period_from, material), "mass_kg"])
    factor_from = float(rows.loc[(period_from, material), "factor"])
    factor_to = float(rows.loc[(period_to, material), "factor"])
    return mass_from * (factor_to - factor_from)


def decompose(mart: pd.DataFrame, *, period_from: str = "v1", period_to: str = "v2") -> Decomposition:
    """Split the ``period_from``→``period_to`` change in ``F`` into its two effects.

    ``mart`` is the production-weighted basis: one row per ``vintage`` × ``material``
    with ``mass_kg`` (count) and ``factor`` (fact). Returns per-material and total
    intensity (factor) and volume/mix (mass) effects, with a reconciliation residual.
    """
    frame = mart[mart[_PERIOD].isin((period_from, period_to))]
    before = frame[frame[_PERIOD] == period_from].set_index(_GROUP)[["mass_kg", "factor"]]
    after = frame[frame[_PERIOD] == period_to].set_index(_GROUP)[["mass_kg", "factor"]]
    materials = before.index.union(after.index).sort_values()

    mass_from = before["mass_kg"].reindex(materials, fill_value=0.0)
    mass_to = after["mass_kg"].reindex(materials, fill_value=0.0)
    factor_from = before["factor"].reindex(materials)
    factor_to = after["factor"].reindex(materials)

    footprint_from = (mass_from * factor_from).fillna(0.0)
    footprint_to = (mass_to * factor_to).fillna(0.0)
    delta = footprint_to - footprint_from
    # Intensity is the factor change on the before-period mass; volume/mix is the
    # remainder of the delta. A material new in the after period (mass_from == 0) or
    # absent from it (no factor_to) has an undefined factor difference but zero mass
    # weight there, so ``fillna(0.0)`` puts its whole delta on volume/mix.
    intensity = (mass_from * (factor_to - factor_from)).fillna(0.0)
    volume_mix = delta - intensity

    by_material = pd.DataFrame(
        {
            _GROUP: materials,
            "intensity_effect": intensity.to_numpy(),
            "volume_mix_effect": volume_mix.to_numpy(),
        }
    )

    f_from, f_to = float(footprint_from.sum()), float(footprint_to.sum())
    intensity_effect = float(intensity.sum())
    volume_mix_effect = float(volume_mix.sum())
    observed_delta = f_to - f_from

    return Decomposition(
        period_from=period_from,
        period_to=period_to,
        f_from=f_from,
        f_to=f_to,
        observed_delta=observed_delta,
        intensity_effect=intensity_effect,
        volume_mix_effect=volume_mix_effect,
        residual=observed_delta - (intensity_effect + volume_mix_effect),
        by_material=by_material,
    )
