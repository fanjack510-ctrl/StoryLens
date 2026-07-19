"""Migrate Reader Journey scene profiles from contract v1.1 to v1.2."""

from __future__ import annotations


def _truncate(text: str, max_chars: int = 160) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 1] + "…"


def migrate_v11_profile_dict_to_v12(payload: dict) -> dict:
    """Upgrade a single scene profile dict from v1.1 semantics to v1.2."""
    result = dict(payload)
    evidence = list(result.get("evidence_paragraph_ids") or [])[:2]
    hooks = result.get("hooks") or []

    q_in: list[dict] = []
    q_created: list[dict] = list(result.get("reader_question_created") or [])
    created_questions = {item.get("question", "").strip() for item in q_created if item.get("question")}

    for item in result.get("reader_question_in") or []:
        if not isinstance(item, dict):
            continue
        source = item.get("source", "")
        question = (item.get("question") or "").strip()
        if not question:
            continue
        if source == "created_in_scene":
            if question in created_questions:
                continue
            q_created.append(
                {
                    "question": question,
                    "trigger_summary": _truncate(result.get("scene_value_summary") or question),
                    "strength": 50,
                    "evidence_paragraph_ids": list(evidence),
                }
            )
            created_questions.add(question)
        elif source == "carried_from_previous":
            q_in.append(
                {
                    "question": question,
                    "source": "carried_from_previous",
                    "confidence": item.get("confidence", 0.7),
                }
            )

    q_out: list[dict] = []
    in_questions = {(item.get("question") or "").strip() for item in q_in}
    for item in result.get("reader_question_out") or []:
        if not isinstance(item, dict):
            continue
        question = (item.get("question") or "").strip()
        if not question:
            continue
        origin = item.get("origin")
        out_evidence = list(item.get("evidence_paragraph_ids") or [])
        if not out_evidence:
            for hook in hooks:
                if isinstance(hook, dict) and hook.get("summary"):
                    out_evidence = list(hook.get("evidence_paragraph_ids") or [])[:2]
                    break
            if not out_evidence:
                out_evidence = list(evidence)
        if not origin:
            if not q_in and not in_questions:
                origin = "created_here"
                if question not in created_questions:
                    q_created.append(
                        {
                            "question": question,
                            "trigger_summary": _truncate(result.get("scene_value_summary") or question),
                            "strength": int(item.get("strength") or 50),
                            "evidence_paragraph_ids": list(out_evidence)[:2],
                        }
                    )
                    created_questions.add(question)
            elif question in in_questions:
                origin = "carried"
            else:
                origin = "created_here"
        q_out.append(
            {
                "question": question,
                "origin": origin,
                "strength": int(item.get("strength") or 50),
                "evidence_paragraph_ids": out_evidence[:8],
                "hook_type": item.get("hook_type") or "other",
            }
        )

    result["reader_question_in"] = q_in[:2]
    result["reader_question_created"] = q_created[:2]
    result["reader_question_out"] = q_out[:2]
    return result


def migrate_v11_batch_dict_to_v12(payload: dict) -> tuple[dict, str]:
    contract = str(payload.get("contract_version", "1.1"))
    profiles = []
    for profile in payload.get("profiles") or []:
        if isinstance(profile, dict):
            profiles.append(migrate_v11_profile_dict_to_v12(profile))
    return {"contract_version": "1.2", "profiles": profiles}, contract
