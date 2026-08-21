"""Container entry point for the Lunit L2 conversation driver."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lunit_harness.api.routes import create_app  # noqa: E402


app = create_app()
