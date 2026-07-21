"""Tests for short-fragment scene boundary consolidation."""

from types import SimpleNamespace

from app.services.scene_fragment_consolidation import (
    BoundaryMeta,
    consolidate_boundary_ids,
)
from app.services.scene_pipeline import scene_ranges


def _paras(texts: list[str]):
    return [
        SimpleNamespace(id=f"P{i:04d}", paragraph_index=i, normalized_text=text)
        for i, text in enumerate(texts)
    ]


def _range_texts(paragraphs, boundary_ids, boundary_meta=None):
    from app.services.scene_fragment_consolidation import consolidate_boundary_ids

    kept = consolidate_boundary_ids(paragraphs, boundary_ids, boundary_meta)
    ranges = scene_ranges(paragraphs, kept, consolidate_short_fragments=False)
    out = []
    for start, end in ranges:
        chunk = [
            item.normalized_text
            for item in paragraphs
            if start.paragraph_index <= item.paragraph_index <= end.paragraph_index
        ]
        out.append(chunk)
    return out


def test_name_shout_fragment_does_not_split_scene():
    paragraphs = _paras(
        [
            "林舟推开房门，看见桌上的信封。",
            "麦隆——",
            "他没有回答，只是把信封塞进怀里。",
        ]
    )
    kept = consolidate_boundary_ids(paragraphs, [paragraphs[0].id, paragraphs[1].id])
    scenes = _range_texts(paragraphs, [paragraphs[0].id, paragraphs[1].id])
    assert all(scene != ["麦隆——"] for scene in scenes)
    assert "麦隆——" in "".join(scenes[0])
    assert paragraphs[0].id not in kept or paragraphs[1].id not in kept


def test_onomatopoeia_fragment_does_not_split_scene():
    paragraphs = _paras(
        [
            "门轴忽然发出刺耳的响声。",
            "砰！",
            "黑暗里只剩下急促的呼吸。",
        ]
    )
    scenes = _range_texts(paragraphs, [paragraphs[0].id, paragraphs[1].id])
    assert all(scene != ["砰！"] for scene in scenes)


def test_continuous_dialogue_paragraph_breaks_do_not_split():
    paragraphs = _paras(
        [
            "“你真的要走？”",
            "“今晚必须离开。”",
            "“那信封呢？”",
            "“我会带上。”",
        ]
    )
    kept = consolidate_boundary_ids(
        paragraphs, [paragraphs[0].id, paragraphs[1].id, paragraphs[2].id]
    )
    assert kept == []
    assert len(_range_texts(paragraphs, [paragraphs[0].id, paragraphs[1].id, paragraphs[2].id])) == 1


def test_same_place_action_continuation_does_not_split():
    paragraphs = _paras(
        [
            "林舟蹲下身，手指摸过长椅缝隙，尘土沾上袖口。",
            "他继续往里探。",
            "终于触到冰凉的纸角，把它抽了出来。",
        ]
    )
    scenes = _range_texts(paragraphs, [paragraphs[0].id, paragraphs[1].id])
    assert not any(scene == ["他继续往里探。"] for scene in scenes)


def test_explicit_location_change_keeps_boundary():
    paragraphs = _paras(
        [
            "车站大厅的广播还在回响。",
            "十分钟后，他已经站在另一座城市的天桥上。",
        ]
    )
    meta = {
        paragraphs[0].id: BoundaryMeta(
            reason_codes=frozenset({"location_change"}),
            reason_labels=frozenset({"地点发生变化"}),
            concise_reason="地点切换到另一座城市",
        )
    }
    kept = consolidate_boundary_ids(paragraphs, [paragraphs[0].id], meta)
    assert kept == [paragraphs[0].id]


def test_explicit_time_jump_keeps_boundary():
    paragraphs = _paras(
        [
            "他把信封藏进怀里，消失在夜色中。",
            "三天后，审讯室的灯光刺得人睁不开眼。",
        ]
    )
    meta = {
        paragraphs[0].id: BoundaryMeta(
            reason_codes=frozenset({"time_jump"}),
            concise_reason="时间跳转到三天后",
        )
    }
    kept = consolidate_boundary_ids(paragraphs, [paragraphs[0].id], meta)
    assert kept == [paragraphs[0].id]


def test_chapter_end_hook_may_remain_independent():
    paragraphs = _paras(
        [
            "林舟把信封塞进怀里，头也不回地走进雨里。",
            "信封内侧，一行陌生字迹正在慢慢浮现——你还活着吗？",
        ]
    )
    meta = {
        paragraphs[0].id: BoundaryMeta(
            reason_codes=frozenset({"explicit_scene_separator"}),
            concise_reason="章尾独立钩子",
        )
    }
    kept = consolidate_boundary_ids(paragraphs, [paragraphs[0].id], meta)
    assert kept == [paragraphs[0].id]
    scenes = _range_texts(paragraphs, [paragraphs[0].id], meta)
    assert len(scenes) == 2
    assert "你还活着吗" in scenes[-1][0]


def test_scene_order_stable_after_consolidation():
    paragraphs = _paras(
        [
            "清晨，林舟走进空荡的车站。",
            "他要在发车前找到遗失的信封。",
            "麦隆——",
            "广播忽然宣布列车改到另一站台。",
            "三小时后，他已在另一座城市的旅馆醒来。",
        ]
    )
    meta = {
        paragraphs[3].id: BoundaryMeta(
            reason_codes=frozenset({"time_jump", "location_change"}),
            concise_reason="时间与地点同时跳转",
        )
    }
    kept = consolidate_boundary_ids(
        paragraphs, [paragraphs[1].id, paragraphs[2].id, paragraphs[3].id], meta
    )
    assert paragraphs[2].id not in kept
    assert paragraphs[3].id in kept
    scenes = _range_texts(
        paragraphs, [paragraphs[1].id, paragraphs[2].id, paragraphs[3].id], meta
    )
    assert "麦隆——" in "".join(scenes[0])
    assert "旅馆" in "".join(scenes[-1])


def test_no_single_residue_sentence_scene():
    paragraphs = _paras(
        [
            "他把门关上，靠着墙喘气。",
            "麦隆——",
            "走廊尽头传来脚步声。",
            "砰！",
            "他终于意识到自己逃不掉了。",
        ]
    )
    scenes = _range_texts(
        paragraphs, [paragraphs[0].id, paragraphs[1].id, paragraphs[2].id, paragraphs[3].id]
    )
    assert all(scene not in (["麦隆——"], ["砰！"]) for scene in scenes)
    assert not any(len(scene) == 1 and len(scene[0]) <= 8 for scene in scenes)
