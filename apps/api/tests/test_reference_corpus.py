from pathlib import Path

from app.narrative_core.material_lab.reference_corpus import classify_reference_file
from app.narrative_core.material_lab.materials import _make_title


def test_reference_corpus_accepts_supported_novel(tmp_path: Path) -> None:
    body = "\n".join(
        f"第{i}章 现场\n刑警走进房间，法医说尸体旁的线索不对劲。\n“凶手留下了证据。”"
        for i in range(1, 90)
    )
    path = tmp_path / "刑警谜案.txt"
    path.write_text(body * 12, encoding="utf-8")

    result = classify_reference_file(path, tmp_path)

    assert result.decision == "accepted"
    assert result.genre_slug == "xuanyi"
    assert result.chapter_markers_sampled >= 4


def test_reference_corpus_rejects_nonfiction(tmp_path: Path) -> None:
    path = tmp_path / "营销管理研究报告.txt"
    path.write_text(
        ("本章学习目标：理解营销管理。\n参考文献：研究表明用户需求重要。\n" * 1600),
        encoding="utf-8",
    )

    result = classify_reference_file(path, tmp_path)

    assert result.decision == "rejected"
    assert result.genre_slug == ""


def test_reference_corpus_prioritizes_explicit_infinite_flow_title(tmp_path: Path) -> None:
    body = "\n".join(
        f"第{i}章 宇宙副本\n轮回者进入主神空间，完成任务才能返回现实。\n"
        "宇宙飞船穿过末日废墟，失败者会被主神抹杀。"
        for i in range(1, 90)
    )
    path = tmp_path / "无限宇宙流.txt"
    path.write_text(body * 12, encoding="utf-8")

    result = classify_reference_file(path, tmp_path)

    assert result.decision == "accepted"
    assert result.genre_slug == "wuxianliu"


def test_plain_resource_title_does_not_claim_unknown_origin() -> None:
    assert _make_title("object_anomaly", "灵石", "灵石丹药", "修炼资源") == "修炼资源·灵石丹药"
    assert _make_title(
        "object_anomaly", "钥匙", "私人物件", "实物线索", owner_conflict=True
    ) == "实物线索·私人物件"
