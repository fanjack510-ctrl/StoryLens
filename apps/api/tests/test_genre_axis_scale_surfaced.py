"""类型专项的刻度要上屏：分数旁边得能回答「5 分长什么样」。"""
from app.narrative_core.long_novel.chapter_focus import CHAPTER_FOCI, anchors_for


def test_every_registered_axis_can_state_its_scale():
    """锚点此前只进提示词。GenreAxis 的文档已经写明没有锚点的后果——

    clarity 在 42 个真实场景里 81% 返回 5，setup_consistency 从没低于 4。那个道理对读者
    同样成立：只给一个 0/5 和一句针对本场的理由，读者无从判断这把尺子严不严。
    """
    keys = [axis.key for focus in CHAPTER_FOCI for axis in focus.axes]
    assert keys, "轴注册表不应为空"
    for key in keys:
        scale = anchors_for(key)
        assert scale, f"{key} 没有锚点"
        # 三档：两端加一个中间档。中间档取 2 还是 3 由这条轴自己定——character_truth 用的
        # 是 0/2/5，因为「说得通但换个人也成立」正落在 2 上。只有两端而没有中间档才不成
        # 其为刻度：那样读者只知道最好和最坏，判断不了自己在哪。
        assert "0=" in scale, f"{key} 的锚点缺 0="
        assert "5=" in scale, f"{key} 的锚点缺 5="
        assert any(f"{n}=" in scale for n in (1, 2, 3, 4)), f"{key} 的锚点没有中间档"


def test_an_unknown_key_returns_empty_rather_than_guessing():
    """取不到就空着——界面据此不画刻度，而不是画一把编出来的尺子。"""
    assert anchors_for("no_such_axis") == ""
    assert anchors_for("") == ""


def test_the_read_path_attaches_the_scale_to_stored_axes():
    """按 key 现取，所以这次改动之前跑的报告也能显示刻度。"""
    import inspect

    from app.services import reader_journey_visualization as viz

    source = inspect.getsource(viz)
    assert "anchors_for" in source
    assert 'row["anchors"] = scale' in source
