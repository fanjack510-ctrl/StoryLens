# -*- coding: utf-8 -*-
"""Entry point: real invocation-path qualification (not full canary)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from certification.invocation_path_qualification_runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
