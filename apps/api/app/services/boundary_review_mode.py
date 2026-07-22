"""Canonical boundary review UX mode for product surfaces.

Formal environments always use confirm_only. manual_editor is retained for
future internal tooling and must not be exposed by default navigation.
"""

from __future__ import annotations

import os
from typing import Literal

BoundaryReviewMode = Literal["confirm_only", "manual_editor"]

DEFAULT_BOUNDARY_REVIEW_MODE: BoundaryReviewMode = "confirm_only"
_ENV_KEY = "STORYLENS_BOUNDARY_REVIEW_MODE"


def get_boundary_review_mode() -> BoundaryReviewMode:
    raw = (os.environ.get(_ENV_KEY) or DEFAULT_BOUNDARY_REVIEW_MODE).strip().lower()
    if raw == "manual_editor":
        return "manual_editor"
    return "confirm_only"


def is_confirm_only() -> bool:
    return get_boundary_review_mode() == "confirm_only"
