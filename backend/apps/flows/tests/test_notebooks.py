"""
Tests that verify notebooks in notebooks/steps/ retain the metadata required
by papermill.  nbstripout strips cell outputs on commit but must leave
kernelspec and language_info intact — without them papermill cannot determine
which kernel to use and raises ValueError at execution time.
"""

import json
from pathlib import Path

import pytest

NOTEBOOKS_DIR = Path(__file__).resolve().parents[4] / "notebooks" / "steps"


def _notebook_paths():
    return sorted(NOTEBOOKS_DIR.glob("*.ipynb"))


@pytest.mark.parametrize("nb_path", _notebook_paths(), ids=lambda p: p.name)
def test_notebook_has_kernelspec(nb_path):
    nb = json.loads(nb_path.read_text())
    assert "kernelspec" in nb.get("metadata", {}), (
        f"{nb_path.name} is missing metadata.kernelspec — "
        "papermill cannot determine the kernel without it. "
        "Add kernelspec back to the notebook metadata."
    )
    ks = nb["metadata"]["kernelspec"]
    assert ks.get("name"), f"{nb_path.name}: kernelspec.name must not be empty."
    assert ks.get("language"), f"{nb_path.name}: kernelspec.language must not be empty."


@pytest.mark.parametrize("nb_path", _notebook_paths(), ids=lambda p: p.name)
def test_notebook_has_language_info(nb_path):
    nb = json.loads(nb_path.read_text())
    assert "language_info" in nb.get("metadata", {}), (
        f"{nb_path.name} is missing metadata.language_info — "
        "papermill requires this to infer the notebook language. "
        "Add language_info back to the notebook metadata."
    )
    li = nb["metadata"]["language_info"]
    assert li.get("name"), f"{nb_path.name}: language_info.name must not be empty."


@pytest.mark.parametrize("nb_path", _notebook_paths(), ids=lambda p: p.name)
def test_notebook_has_parameters_cell(nb_path):
    """Papermill needs exactly one cell tagged 'parameters' for injection."""
    nb = json.loads(nb_path.read_text())
    tagged = [
        cell
        for cell in nb.get("cells", [])
        if "parameters" in cell.get("metadata", {}).get("tags", [])
    ]
    assert len(tagged) == 1, (
        f"{nb_path.name} must have exactly one cell tagged 'parameters' "
        f"for papermill parameter injection, found {len(tagged)}."
    )
