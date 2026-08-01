"""F-5 acceptance: the package imports with no pyspark on the path.

Repos 3 and 5 install this package without Spark. The subprocess blocks
pyspark at the import machinery level, which is stricter than a stripped
sys.path — even an accidental transitive import fails loudly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROBE = """
import sys

class _BlockPyspark:
    def find_spec(self, name, path=None, target=None):
        if name == "pyspark" or name.startswith("pyspark."):
            raise ImportError("pyspark is blocked in this environment")
        return None

sys.meta_path.insert(0, _BlockPyspark())

import fin_lakehouse_contracts
import fin_lakehouse_contracts.names
import fin_lakehouse_contracts.envelope
import fin_lakehouse_contracts.models
import fin_lakehouse_contracts.concepts
import fin_lakehouse_contracts.dq
import fin_lakehouse_contracts.spark  # the guard package itself must stay clean

print("IMPORT_OK")
"""


def test_package_imports_without_pyspark(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout
