"""The version is written in two places; this is what keeps them equal.

v1.2.0 shipped with `pyproject.toml` at 1.2.0 and `__version__` at 1.1.0, so the
published wheel reported a version it was not. Nothing caught it: the packaging
metadata and the runtime constant are read by different things and neither
consults the other. Consumers pin by packaging metadata but log and branch on
`__version__`, so a mismatch is a lie told to whoever is debugging.

Same shape as the schema drift test: two hand-maintained representations of one
fact, reconciled mechanically rather than by remembering.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import edgar_lakehouse_contracts

REPO_ROOT = Path(__file__).parents[1]


def test_runtime_version_matches_packaging_metadata() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = pyproject["project"]["version"]
    assert edgar_lakehouse_contracts.__version__ == declared, (
        f"version drift: pyproject.toml says {declared!r} but "
        f"__version__ is {edgar_lakehouse_contracts.__version__!r}. "
        "Both must move together in the same commit as the release."
    )


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", edgar_lakehouse_contracts.__version__), (
        f"not a semver string: {edgar_lakehouse_contracts.__version__!r}"
    )
