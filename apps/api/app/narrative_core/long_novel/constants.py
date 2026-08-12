"""Frozen constants for the LongNovelAnalysisEngine (Phase 1 Foundation).

Every value here is transcribed from the frozen design contracts
(``DESIGN_FREEZE.md``, 2026-08-12). Each carries its **classification**, because the
classification decides what may be done to it:

``DERIVED CONSTRAINT``
    Computed from other values. Changing it directly is a defect; change its inputs.
``SAFETY GUARD``
    A deliberate margin or ceiling. May be tightened, never loosened without a contract change.
``EMPIRICAL STARTING DEFAULT``
    A measured-or-to-be-measured value. Tunable at its phase gate without breaking the freeze.

Nothing in this module may be duplicated elsewhere in the package: the frozen documents
have exactly one definition per concept, and so does this code.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- versions
# These participate in semantic_compat_key, so bumping any of them invalidates reuse
# (which is the point: it must invalidate rather than silently corrupt).
ENGINE_SEMANTICS_VERSION: Final[str] = "lne-1.0.0"
ASSET_SCHEMA_VERSION: Final[str] = "block_asset.v1"
SEMANTIC_CONTRACT_VERSION: Final[str] = "lne-semantic-1.0.0"
NORMALIZATION_VERSION: Final[str] = "norm-1.0.0"
FACT_KEY_ALGORITHM_VERSION: Final[str] = "factkey-1.0.0"
PROJECTION_ALGORITHM_VERSION: Final[str] = "proj-1.0.0"
RESOLUTION_ALGORITHM_VERSION: Final[str] = "resolve-1.0.0"

# --------------------------------------------------------------------------- separators
# Field separator inside a hashed tuple, and record separator inside a hashed list.
# Both are control characters that cannot occur in normalised novel text, so no field
# value can forge a boundary.
FIELD_SEP: Final[str] = "\x1f"
RECORD_SEP: Final[str] = "\x1e"

# --------------------------------------------------------------------------- output budget
OUTPUT_UTILISATION: Final[float] = 0.80  # SAFETY GUARD (03 §2.5.4)
JSON_ENVELOPE_TOKENS: Final[int] = 150  # DERIVED CONSTRAINT (03 §2.5.4)
OUTPUT_FLOOR_BLOCK_EXTRACTION: Final[int] = 4096  # DERIVED CONSTRAINT (03 §2.5.4)
CONSERVATIVE_MAX_OUTPUT_TOKENS: Final[int] = 4096  # SAFETY GUARD, unprobed default (01 §4.6)
OUTPUT_LADDER: Final[tuple[int, ...]] = (4096, 6000, 7000, 8000, 16000)  # EMPIRICAL DEFAULT
MIN_VIABLE_CHAPTERS_PER_BLOCK: Final[int] = 4  # SAFETY GUARD (03 §2.5.4)

# --------------------------------------------------------------------------- block sizing
TARGET_BLOCK_TOKENS: Final[int] = 40_000  # EMPIRICAL DEFAULT — retry-unit preference
HARD_BLOCK_TOKENS: Final[int] = 60_000  # SAFETY GUARD — absolute ceiling
ANCHOR_TOKENS: Final[int] = 4  # EMPIRICAL DEFAULT — cost of one inline [p:N] marker

# --------------------------------------------------------------------------- per-fact costs
# CONSERVATIVE ESTIMATED SERIALIZED TOKEN BOUNDS (03 §2.5.2), NOT physical bounds.
# Do not re-tune these to chase single tokens: the OUTPUT_UTILISATION margin, plan-time
# preflight, calibration and truncation escalation are what make the planner safe.
TOK_SIGNAL: Final[int] = 33
TOK_EVENT: Final[int] = 62
TOK_STATE: Final[int] = 56
TOK_CAUSAL: Final[int] = 13
TOK_SUSPENSE_ACTION: Final[int] = 46
TOK_RELATIONSHIP: Final[int] = 61
TOK_GOAL: Final[int] = 48
TOK_CHOICE: Final[int] = 111
TOK_THREAD: Final[int] = 37
TOK_IDENTITY: Final[int] = 25
TOK_MENTION: Final[int] = 17
TOK_PROVISIONAL_ENTITY: Final[int] = 29
TOK_EVIDENCE_REF: Final[int] = 2

# --------------------------------------------------------------------------- structure
PARTITION_TARGET_BLOCKS: Final[int] = 6  # EMPIRICAL DEFAULT (03 §4.1b)
PARTITIONS_PER_STAGE_TARGET: Final[int] = 2  # EMPIRICAL DEFAULT (03 §4.1b)
MAX_STAGES: Final[int] = 14  # SAFETY GUARD (03 §4.1b)
CARRY_PROPAGATION_CEILING: Final[int] = 12  # SAFETY GUARD, not a correctness bound (ADR-08b)

# --------------------------------------------------------------------------- projections
PACING_CURVE_BINS_MAX: Final[int] = 96  # EMPIRICAL DEFAULT (03 §5.1a) — see note below
CHARACTERS_MAX: Final[int] = 24  # DERIVED CONSTRAINT (03 §5.1)
TOPIC_DIGEST_MAX_TOKENS: Final[int] = 1_200  # DERIVED CONSTRAINT (03 §5.3)
ASSESSMENT_INPUT_MAX_TOKENS: Final[int] = 7_140  # DERIVED CONSTRAINT (03 §6.0)
FINAL_INPUT_MAX_TOKENS: Final[int] = 10_740  # DERIVED CONSTRAINT (03 §6.0)
STAGE_INPUT_MAX_TOKENS: Final[int] = 4_200  # DERIVED CONSTRAINT (03 §4.4)

# ``PACING_CURVE_BINS_MAX`` is what makes the pacing projection O(1) in book length.
# The *value* is empirical and is measured at T8.5-13; the *existence of a fixed ceiling*
# is normative. A per-partition curve — the retired form — grew linearly with chapter
# count and violated INV-18 at any book longer than the largest one tested.

# --------------------------------------------------------------------------- repair
REPAIR_SCHEMA_TOKENS: Final[int] = 600  # DERIVED CONSTRAINT (05 §2.3)
REPAIR_ERROR_TOKENS: Final[int] = 300  # DERIVED CONSTRAINT (05 §2.3)
REPAIR_INVALID_HEAD_TOKENS: Final[int] = 800  # SAFETY GUARD — shows the defect, never carries content
REPAIR_RESERVE_FRACTION: Final[float] = 0.15  # EMPIRICAL DEFAULT (05 §6)

# --------------------------------------------------------------------------- thresholds
SATURATION_REPLAN_THRESHOLD: Final[float] = 0.25  # EMPIRICAL DEFAULT (03 §2.5.5)
REPLAN_DRIFT_THRESHOLD: Final[float] = 0.15  # EMPIRICAL DEFAULT (01 §4.6)

# --------------------------------------------------------------------------- retention / display
RAW_RETENTION_DAYS: Final[int] = 30  # EMPIRICAL DEFAULT (02 §5.1)
MAX_QUOTE_CHARS: Final[int] = 200  # EMPIRICAL DEFAULT (03 §2.2)

# --------------------------------------------------------------------------- topology
# The only legal vocabulary (03 §5.1). Assessment is a provider unit of its own and is
# NEVER counted inside "the topics"; `chapters` is deterministic and is never a call.
PRIMARY_PROVIDER_TOPICS: Final[tuple[str, ...]] = ("story", "characters", "suspense", "pacing")
DETERMINISTIC_TOPICS: Final[tuple[str, ...]] = ("chapters",)
ALL_TOPICS: Final[tuple[str, ...]] = PRIMARY_PROVIDER_TOPICS + DETERMINISTIC_TOPICS + ("assessment",)

#: Topic rows written before assessment runs (4 primary + 1 deterministic).
TOPIC_ROWS_BEFORE_ASSESSMENT: Final[int] = 5
#: Provider calls made before assessment runs (the deterministic topic costs nothing).
TOPIC_PROVIDER_CALLS_BEFORE_ASSESSMENT: Final[int] = 4


def full_run_provider_calls(n_blocks: int, n_stages: int) -> int:
    """Total provider calls for a complete run, before any repair attempt.

    The single derivation of this figure in code (04 §5.5): blocks + stages + the four
    primary topics + assessment + final. ``chapters`` contributes zero and appears in no
    term. For the 542-chapter reference book this yields 105 (probed) or 154 (unprobed).
    """
    if n_blocks < 0 or n_stages < 0:
        raise ValueError("n_blocks and n_stages must be non-negative")
    return n_blocks + n_stages + TOPIC_PROVIDER_CALLS_BEFORE_ASSESSMENT + 1 + 1
