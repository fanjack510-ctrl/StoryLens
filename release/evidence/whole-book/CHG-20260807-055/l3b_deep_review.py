#!/usr/bin/env python3
"""Post-run deep review for CHG-055 L3-B (isolated DB only)."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:\Dstorylens-wt-1.2.0-after-1.1.2")
EVIDENCE = ROOT / "release" / "evidence" / "whole-book" / "CHG-20260807-055"
DB = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-medium\storylens_l3_medium.db")
SRC = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-medium\medium_41ch_source.txt")

os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + DB.as_posix()


def main() -> int:
    from sqlalchemy import select

    from app.db.models import (
        BookSnapshotParagraph,
        NarrativeAsset,
        NarrativeAssetEvidence,
        NarrativeAssetVersion,
        NarrativeEntity,
        WholeBookCheckpoint,
        WholeBookProviderAttempt,
    )
    from app.db.session import SessionLocal, create_db
    from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
        get_run_chapter_functions_product_v1,
    )
    from app.narrative_core.services.whole_book_minimal_read_v1_service import get_run_overview
    from app.narrative_core.services.whole_book_structure_product_v1_service import (
        get_run_structure_product_v1,
    )

    create_db()
    text = SRC.read_text(encoding="utf-8")
    out: dict = {}

    with SessionLocal() as session:
        ov = get_run_overview(session, 1)
        out["overview"] = ov

        st = get_run_structure_product_v1(session, 1)
        stages = []
        if isinstance(st, dict):
            payload = st.get("structure") or st
            if isinstance(payload, dict):
                stages = payload.get("stages") or []
            elif isinstance(payload, list):
                stages = payload
        struct_issues = []
        prev_end = None
        for i, s in enumerate(stages if isinstance(stages, list) else []):
            if not isinstance(s, dict):
                continue
            cs = (
                s.get("chapter_start")
                or s.get("start_chapter_order")
                or (s.get("range") or {}).get("start")
                or (s.get("full_selected_range") or {}).get("start_chapter_order")
            )
            ce = (
                s.get("chapter_end")
                or s.get("end_chapter_order")
                or (s.get("range") or {}).get("end")
                or (s.get("full_selected_range") or {}).get("end_chapter_order")
            )
            try:
                cs_i = int(cs)
                ce_i = int(ce)
            except Exception:
                struct_issues.append({"i": i, "issue": "missing_range"})
                continue
            if cs_i > ce_i:
                struct_issues.append({"i": i, "issue": "start_gt_end", "cs": cs_i, "ce": ce_i})
            if cs_i < 0 or ce_i > 41:
                struct_issues.append({"i": i, "issue": "oob", "cs": cs_i, "ce": ce_i})
            if prev_end is not None and cs_i + 1 < prev_end - 5:
                struct_issues.append(
                    {"i": i, "issue": "severe_backtrack", "cs": cs_i, "prev_end": prev_end}
                )
            prev_end = max(prev_end or ce_i, ce_i)
        out["structure_stage_count"] = len(stages) if isinstance(stages, list) else 0
        out["structure_issues"] = struct_issues
        out["structure_sample"] = (stages[:2] if isinstance(stages, list) else None)

        cf_all: list[dict] = []
        cursor = None
        while True:
            page = get_run_chapter_functions_product_v1(session, 1, limit=50, cursor=cursor)
            if page is None:
                break
            items = page.get("chapters") or page.get("items") or []
            if isinstance(items, list):
                cf_all.extend([x for x in items if isinstance(x, dict)])
            cursor = (page.get("pagination") or {}).get("next_cursor") or page.get("next_cursor")
            if not cursor:
                break
        if not cf_all:
            cp = session.scalar(
                select(WholeBookCheckpoint).where(
                    WholeBookCheckpoint.run_id == 1,
                    WholeBookCheckpoint.checkpoint_key == "chapter_functions_result_v2",
                )
            )
            if cp:
                payload = json.loads(cp.payload_json or "{}")
                cf_all = [c for c in (payload.get("chapters") or []) if isinstance(c, dict)]

        by_order = {
            int(c.get("chapter_order")): c
            for c in cf_all
            if c.get("chapter_order") is not None
        }
        orders = sorted(by_order)
        mid = len(orders) // 2
        sample_orders = sorted(
            set(orders[:5] + orders[max(0, mid - 5) : mid + 5] + orders[-5:])
        )
        samples = []
        for o in sample_orders:
            c = by_order[o]
            samples.append(
                {
                    "chapter_order": o,
                    "primary": c.get("primary_function"),
                    "secondary": c.get("secondary_functions"),
                    "has_evidence": bool(
                        c.get("evidence")
                        or c.get("evidences")
                        or c.get("primary_evidence")
                    ),
                }
            )
        out["cf_total"] = len(by_order)
        out["cf_sample_count"] = len(samples)
        out["cf_samples"] = samples
        out["cf_primary_dist"] = dict(
            Counter(str(c.get("primary_function")) for c in cf_all)
        )

        ents = list(session.scalars(select(NarrativeEntity).limit(30)))
        ent_check = []
        for e in ents[:8]:
            name = e.canonical_name or ""
            ent_check.append({"name": name, "in_text": bool(name) and name in text})
        out["entity_check"] = ent_check

        # Events via assets
        assets = list(session.scalars(select(NarrativeAsset).limit(80)))
        event_like = [
            a
            for a in assets
            if "event" in str(getattr(a, "asset_type", "") or "").lower()
            or "event" in str(getattr(a, "kind", "") or "").lower()
        ]
        out["event_asset_count"] = len(event_like)
        out["event_asset_sample"] = [
            {
                "id": a.id,
                "type": getattr(a, "asset_type", None) or getattr(a, "kind", None),
                "title": getattr(a, "title", None) or getattr(a, "display_name", None),
            }
            for a in event_like[:10]
        ]

        evidences = list(session.scalars(select(NarrativeAssetEvidence).limit(300)))
        versions = {v.id: v for v in session.scalars(select(NarrativeAssetVersion))}
        assets_by_id = {a.id: a for a in session.scalars(select(NarrativeAsset))}
        buckets = {
            "overview": [],
            "characters_events": [],
            "structure": [],
            "chapter_functions": [],
            "other": [],
        }
        for ev in evidences:
            v = versions.get(ev.asset_version_id)
            a = assets_by_id.get(getattr(v, "asset_id", None)) if v else None
            kind = " ".join(
                [
                    str(getattr(v, "asset_type", "") or ""),
                    str(getattr(a, "asset_type", "") or ""),
                    str(getattr(a, "kind", "") or ""),
                    str(getattr(v, "label", "") or ""),
                ]
            ).lower()
            if "overview" in kind:
                buckets["overview"].append(ev)
            elif "structure" in kind or "stage" in kind:
                buckets["structure"].append(ev)
            elif "chapter" in kind or "function" in kind:
                buckets["chapter_functions"].append(ev)
            elif "entity" in kind or "event" in kind or "character" in kind:
                buckets["characters_events"].append(ev)
            else:
                buckets["other"].append(ev)
        out["evidence_bucket_sizes"] = {k: len(v) for k, v in buckets.items()}

        checked = []
        for name, n in [
            ("overview", 4),
            ("characters_events", 6),
            ("structure", 4),
            ("chapter_functions", 6),
        ]:
            pool = buckets[name] or buckets["other"] or evidences
            for ev in pool[:n]:
                para = (
                    session.get(BookSnapshotParagraph, ev.snapshot_paragraph_id)
                    if ev.snapshot_paragraph_id
                    else None
                )
                ok = (
                    ev.book_snapshot_id == 1
                    and ev.snapshot_paragraph_id is not None
                    and int(ev.end_offset or 0) >= int(ev.start_offset or 0)
                    and para is not None
                    and getattr(para, "snapshot_id", None) == 1
                )
                checked.append(
                    {
                        "bucket": name,
                        "ok": bool(ok),
                        "chapter_id": getattr(para, "chapter_id", None),
                        "snap": ev.book_snapshot_id,
                    }
                )
        out["evidence_review"] = {
            "checked": len(checked),
            "pass": sum(1 for c in checked if c["ok"]),
            "fail": sum(1 for c in checked if not c["ok"]),
            "items": checked,
        }

        key = os.environ.get("STORYLENS_ALIYUN_API_KEY", "")
        if not key:
            from app.services.credentials.keyring_store import KeyringCredentialStore

            key = KeyringCredentialStore().get("aliyun_qwen_plus") or ""
        leaks = []
        for p in EVIDENCE.rglob("*"):
            if not p.is_file() or p.suffix not in {".md", ".json", ".txt", ".py"}:
                continue
            raw = p.read_text(encoding="utf-8", errors="ignore")
            if key and len(key) > 8 and key in raw:
                leaks.append(str(p))
            if re.search(r"sk-[a-zA-Z0-9]{20,}", raw):
                leaks.append(str(p) + ":sk-pattern")
        for a in session.scalars(select(WholeBookProviderAttempt)):
            msg = getattr(a, "error_message_safe", None) or ""
            if key and key in str(msg):
                leaks.append(f"attempt:{a.id}")
        out["secret_leaks"] = leaks

        # Overview hallucination light
        major = 0
        if isinstance(ov, dict):
            blob = json.dumps(ov, ensure_ascii=False)
            # protagonist names from entity check
            for name in ["何晓月", "上官飞", "叶秋水"]:
                if name in blob and name not in text:
                    major += 1
        out["major_hallucination_count"] = major

    (EVIDENCE / "MEDIUM_DEEP_REVIEW.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("DEEP_REVIEW_OK")
    print("STRUCT_ISSUES", len(out["structure_issues"]))
    print("CF_TOTAL", out["cf_total"], "SAMPLES", out["cf_sample_count"])
    print(
        "EVIDENCE",
        out["evidence_review"]["pass"],
        "/",
        out["evidence_review"]["checked"],
    )
    print("LEAKS", out["secret_leaks"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
