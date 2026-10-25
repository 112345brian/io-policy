"""The README example, run as a test so it cannot rot."""
from __future__ import annotations

import runpy
from pathlib import Path


def test_the_readme_example_runs():
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "examples" / "quickstart.py"))
    assert namespace["results"] == ["allowed", "served_local", "refused"]
