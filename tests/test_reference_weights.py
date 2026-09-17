"""Reference weights load with bands that cover the fixture and exclude the outlier."""

from __future__ import annotations

from carbonara.references import reference_weights


def test_shell_fabric_band_covers_range_and_excludes_the_5000g_outlier():
    shell = reference_weights()["shell fabric"]
    assert shell.in_band(154.0)  # a plausible TSH shell
    assert shell.in_band(661.0)  # the heaviest legitimate shell
    assert not shell.in_band(5000.0)  # the planted implausible value


def test_webbing_strap_uses_a_widened_band():
    strap = reference_weights()["webbing strap"]
    assert strap.in_band(9.0) and strap.in_band(92.0)  # natural spread wider than 10x


def test_every_component_has_a_positive_ordered_band():
    for component, ref in reference_weights().items():
        assert 0 < ref.band_low_g <= ref.ref_weight_g <= ref.band_high_g, component
