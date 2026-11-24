"""Runtime bootstrapper launching OmniOps using the project's shared virtual environment."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_VENVS = (
    PROJECT_ROOT.parent / ".venv",
    Path("/home/bakar/Documents/NAVTTC/.venv"),
)


def _find_python_interpreter() -> Path | None:
    for venv in CANDIDATE_VENVS:
        py = venv / "bin" / "python"
        if py.is_file():
            return py
    return None


def main() -> None:
    target_py = _find_python_interpreter()
    if target_py is not None:
        target_venv = target_py.parents[1].resolve()
        if Path(sys.prefix).resolve() != target_venv:
            os.execv(str(target_py), [str(target_py), str(PROJECT_ROOT / "run.py")])

    import uvicorn

    from omniops.agent.config import load_settings

    settings = load_settings()
    print(f"Using Python: {sys.executable}", flush=True)
    print(f"OmniOps Ontology Operations Center: http://{settings.host}:{settings.port}", flush=True)
    uvicorn.run("omniops.app:app", host=settings.host, port=settings.port, access_log=False)
