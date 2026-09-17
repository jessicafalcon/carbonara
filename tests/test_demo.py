"""The scripted walkthrough runs deterministically and tells the applied-loop story."""

from __future__ import annotations

import importlib.util
import pathlib

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "demo.py"


def _load_demo():
    spec = importlib.util.spec_from_file_location("carbonara_demo", _DEMO)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_walkthrough_is_deterministic():
    demo = _load_demo()
    assert demo.walkthrough() == demo.walkthrough()


def test_walkthrough_tells_the_applied_loop_story():
    lines = "\n".join(_load_demo().walkthrough())
    # The eight steps, the drift-gate proposal, the approval, and the chained trace.
    assert "2. drift gate  · review_required; proposes rename vendor → supplier" in lines
    assert "reviewer approved at 2026-01-01T00:00:00Z" in lines
    assert "approvals applied to 3 cells: r0065, r0145, r0178" in lines
    assert "spine: normalize_material › reference_resolve" in lines
    assert "alias:Organic cottn" in lines


def test_main_prints_the_walkthrough(capsys):
    demo = _load_demo()
    demo.main()
    assert "five-minute walkthrough" in capsys.readouterr().out
