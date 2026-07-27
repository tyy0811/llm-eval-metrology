"""The engine import boundary holds, and the checker that enforces it actually works."""

from __future__ import annotations

from pathlib import Path

import check_imports

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE = REPO_ROOT / "metrology"


def test_engine_package_imports() -> None:
    import metrology

    assert metrology.__version__ == "0.0.0"


def test_engine_tree_has_no_disallowed_imports() -> None:
    assert check_imports.scan([ENGINE]) == []


def test_checker_exits_zero_on_the_real_engine() -> None:
    assert check_imports.main([str(ENGINE)]) == 0


def test_stdlib_numpy_scipy_and_relative_imports_are_allowed(tmp_path: Path) -> None:
    module = tmp_path / "allowed.py"
    module.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "import numpy as np",
                "from scipy import stats",
                "import scipy.special",
                "from . import sibling",
                "from .other import thing",
                "import metrology",
            ]
        ),
        encoding="utf-8",
    )
    assert check_imports.scan([module]) == []


def test_forbidden_third_party_is_flagged(tmp_path: Path) -> None:
    module = tmp_path / "forbidden.py"
    module.write_text("import pandas as pd\n", encoding="utf-8")

    found = check_imports.scan([module])

    assert len(found) == 1
    assert found[0].module == "pandas"
    assert found[0].lineno == 1


def test_from_import_of_forbidden_package_is_flagged(tmp_path: Path) -> None:
    module = tmp_path / "forbidden_from.py"
    module.write_text("from matplotlib import pyplot\n", encoding="utf-8")

    found = check_imports.scan([module])

    assert [v.module for v in found] == ["matplotlib"]


def test_submodule_import_is_reported_by_its_root(tmp_path: Path) -> None:
    module = tmp_path / "nested.py"
    module.write_text("import requests.adapters\n", encoding="utf-8")

    assert [v.module for v in check_imports.scan([module])] == ["requests"]


def test_checker_exits_nonzero_when_boundary_is_broken(tmp_path: Path) -> None:
    module = tmp_path / "bad.py"
    module.write_text("import torch\n", encoding="utf-8")

    assert check_imports.main([str(module)]) == 1


def test_missing_target_is_not_a_violation(tmp_path: Path) -> None:
    assert check_imports.main([str(tmp_path / "does_not_exist")]) == 0
