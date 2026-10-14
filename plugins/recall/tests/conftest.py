"""pytest runs of the RECALL suite get a throwaway per-user state folder.

Hooks write turn state for a project without a store into a per-user folder
(config.user_state_dir). This points RECALL_STATE_DIR at a temp folder when
pytest loads this file, before any test or hook runs, so hook subprocesses
inherit it and a plain `pytest` run never writes into the developer's real
folder. The folder is removed when the run ends.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_tests  # noqa: E402

run_tests.isolate_user_state()
