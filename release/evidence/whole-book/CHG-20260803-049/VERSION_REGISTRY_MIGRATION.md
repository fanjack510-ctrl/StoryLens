# VERSION / REGISTRY / MIGRATION — CHG-20260803-049

## Version pins
| Source | Value |
|---|---|
| `VERSION` | 1.2.0 |
| `apps/desktop/package.json` | 1.2.0 |
| `apps/desktop/src-tauri/tauri.conf.json` | 1.2.0 |
| `release/baseline.json` version | **1.0.5** (debt T1) |
| `release/unreleased.json` base_version | **1.0.5** (debt T1) |
| `version_manager.py check` | **PASS** |

## Change registry
`scripts/change_registry.py check` → **FAIL** (full list in `CHANGE_REGISTRY_CHECK.txt`).
Classes: base_version mismatch; invalid status `integrated`; missing `release_impact`; head_inclusion not ancestor; unregistered commits including CHG-046/047/048 merge/product/evidence SHAs.

## Migrations
| Item | Value |
|---|---|
| `len(NARRATIVE_MIGRATION_ORDER)` | **16** (001–016 incl. whole-book 011–016) |
| Tests still locking 13/14 | OBSOLETE_TEST O2 |
| Product migration order appears intentional for Free whole-book | do not renumber |

## check_project
FAIL at change_registry step; version step PASS; not TIMEOUT on this HEAD.
