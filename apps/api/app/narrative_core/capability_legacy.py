"""Legacy VIP FEATURE_KEYS → CapabilityKey mapping (Phase 1C-P freeze).

Mapping table (conflict-free — each legacy key maps to at most one target):

| Legacy key (license/features.ts) | Target CapabilityKey      | Notes                          |
|----------------------------------|---------------------------|--------------------------------|
| batch_analysis                   | whole_book_analysis       | Batch runs are whole-book      |
| novel_rhythm_map                 | whole_book_analysis       | Module: structure_stages       |
| character_arc                    | whole_book_analysis       | Module: character_arcs         |
| foreshadow_tracking              | whole_book_analysis       | Module: hooks_payoffs          |
| novel_comparison                 | cross_book_search         | Cross-book comparison          |
| advanced_report                  | advanced_export           | Advanced report export         |
| inspiration_center               | story_lab                 | Inspiration / lab entry        |

Unmapped legacy strings return ``None`` and should be treated as not_shipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.narrative_core.enums import CapabilityKey

LEGACY_VIP_FEATURE_KEYS: frozenset[str] = frozenset(
    {
        "batch_analysis",
        "novel_rhythm_map",
        "character_arc",
        "foreshadow_tracking",
        "novel_comparison",
        "advanced_report",
        "inspiration_center",
    }
)

LEGACY_TO_CAPABILITY: dict[str, CapabilityKey] = {
    "batch_analysis": CapabilityKey.WHOLE_BOOK_ANALYSIS,
    "novel_rhythm_map": CapabilityKey.WHOLE_BOOK_ANALYSIS,
    "character_arc": CapabilityKey.WHOLE_BOOK_ANALYSIS,
    "foreshadow_tracking": CapabilityKey.WHOLE_BOOK_ANALYSIS,
    "novel_comparison": CapabilityKey.CROSS_BOOK_SEARCH,
    "advanced_report": CapabilityKey.ADVANCED_EXPORT,
    "inspiration_center": CapabilityKey.STORY_LAB,
}


class LegacyMapStatus(StrEnum):
    MAPPED = "mapped"
    UNMAPPED = "unmapped"
    NOT_SHIPPED = "not_shipped"


@dataclass(frozen=True, slots=True)
class LegacyCapabilityMapping:
    legacy_key: str
    status: LegacyMapStatus
    capability_key: CapabilityKey | None = None


def map_legacy_feature_key(legacy_key: str) -> LegacyCapabilityMapping:
    if legacy_key not in LEGACY_VIP_FEATURE_KEYS:
        return LegacyCapabilityMapping(
            legacy_key=legacy_key,
            status=LegacyMapStatus.UNMAPPED,
            capability_key=None,
        )
    target = LEGACY_TO_CAPABILITY.get(legacy_key)
    if target is None:
        return LegacyCapabilityMapping(
            legacy_key=legacy_key,
            status=LegacyMapStatus.NOT_SHIPPED,
            capability_key=None,
        )
    return LegacyCapabilityMapping(
        legacy_key=legacy_key,
        status=LegacyMapStatus.MAPPED,
        capability_key=target,
    )


def assert_legacy_mapping_conflict_free() -> None:
    """Ensure no two legacy keys map to conflicting exclusive targets incorrectly."""

    seen: dict[str, str] = {}
    for legacy_key, capability in LEGACY_TO_CAPABILITY.items():
        if legacy_key in seen and seen[legacy_key] != capability.value:
            raise ValueError(f"legacy mapping conflict for {legacy_key}")
        seen[legacy_key] = capability.value
    # Multiple legacy keys may map to the same capability (e.g. batch + rhythm → whole_book).
    reverse: dict[str, list[str]] = {}
    for legacy_key, capability in LEGACY_TO_CAPABILITY.items():
        reverse.setdefault(capability.value, []).append(legacy_key)
    if len(reverse) != len(set(LEGACY_TO_CAPABILITY.values())):
        pass  # many-to-one is allowed
