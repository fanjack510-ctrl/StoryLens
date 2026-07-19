# -*- coding: utf-8 -*-
"""Entry point: Phase 1D-B2 real API canary."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

from certification.real_canary_runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
