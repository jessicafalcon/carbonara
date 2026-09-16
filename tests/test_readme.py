"""Run the README doctests under pytest, so the docs can't drift from the code."""

from __future__ import annotations

import doctest
import pathlib


def test_readme_doctests() -> None:
    readme = pathlib.Path(__file__).parent.parent / "README.md"
    result = doctest.testfile(
        str(readme),
        module_relative=False,
        optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE,
    )
    assert result.failed == 0, f"{result.failed} README doctest(s) failed"
