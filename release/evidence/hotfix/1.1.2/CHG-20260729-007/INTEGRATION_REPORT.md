# CHG-20260729-007 INTEGRATION REPORT (evidence)

## Reachability (pre-006 merge)

| Change | Verified/Issue Head | Ancestor of hotfix/1.1.2 @ 5955453 |
|--------|---------------------|-------------------------------------|
| CHG-040 | 956afe02… | YES |
| CHG-041 | 15d746e / 5900615 | YES |
| CHG-001 | 1bdaf11f… | YES |
| CHG-002 | 46754919… | YES |
| CHG-003 | c888330c… | YES |
| CHG-004 | fb22604a… | YES |
| CHG-005 | 9a91258e… | YES |
| CHG-006 | ea2df6cb… | NO → FF merged |

## Integration action

- Fast-forward `hotfix/1.1.2` 5955453 → 8206a27 (includes CHG-006 + MG PASS)
- No duplicate merges of 040–005
- CHG-042 not included

## Version

`version_manager.py set 1.1.2` + check PASS

## Migrations (TEMP)

`%TEMP%\storylens-v112-integration\` — fresh + second pass + upgrade-from-minimal-v111 PASS

## Private

PRIVATE CODE CHANGE: NO  
Private HEAD unchanged for product code; CHG-040 private already on private hotfix/1.1.2.
