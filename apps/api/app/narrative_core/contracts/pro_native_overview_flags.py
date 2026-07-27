"""STEP 2.2 Feature Flag + Fixture Engine identity for native Overview.

WHOLE_BOOK_RUNS_ENDPOINT_DISABLED remains True for the legacy whole-book
analysis production create path. Native Overview walking skeleton is gated
separately by PRO_NATIVE_OVERVIEW_ENABLED (default False).

Prefer expressing walking-skeleton metadata via engine_id / engine_version /
prompt_version (and response warnings) — do not add DB boolean columns for
engine_mode / walking_skeleton / production_ready.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Feature flag — default OFF for all installs
# ---------------------------------------------------------------------------

_ENV_FLAG = "PRO_NATIVE_OVERVIEW_ENABLED"


def is_pro_native_overview_enabled() -> bool:
    """Backend-authoritative gate. Frontend flag must not bypass this."""

    raw = os.environ.get(_ENV_FLAG, "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# Compile-time / docs alias (always False at import; runtime uses env).
PRO_NATIVE_OVERVIEW_ENABLED_DEFAULT = False

# ---------------------------------------------------------------------------
# Fixture engine identity (never pretend to be a real model / provider)
# ---------------------------------------------------------------------------

FIXTURE_ENGINE_ID = "fixture-native-overview-v1"
FIXTURE_ENGINE_VERSION = "walking-skeleton-1"
FIXTURE_PROMPT_VERSION = "fixture-no-prompt"

# Formal Private engine id (implemented in STEP 2.3-B). Loader must not silently
# fall back to Fixture when this id is requested.
PRIVATE_NATIVE_OVERVIEW_ENGINE_ID = "private-native-overview-v1"

FIXTURE_DEVELOPMENT_WARNING = (
    "Fixture execution does not call a provider."
)
WALKING_SKELETON_USER_NOTICE = (
    "当前为行走骨架验证，不调用真实 AI Provider。"
)
