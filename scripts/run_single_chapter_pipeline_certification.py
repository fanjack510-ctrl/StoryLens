# -*- coding: utf-8 -*-
"""CLI entry: Phase 1D-B1 offline pipeline certification."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from certification.pipeline_cert_runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
