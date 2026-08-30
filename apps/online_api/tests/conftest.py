from __future__ import annotations

import sys
from pathlib import Path

ONLINE_ROOT = Path(__file__).resolve().parents[1]
if str(ONLINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ONLINE_ROOT))
