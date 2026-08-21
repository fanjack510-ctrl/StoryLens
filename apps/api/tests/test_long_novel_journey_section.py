"""The journey section: which axis a book gets, and what the axis is allowed to say.

The failure this section exists to end is specific and was shipped: the protagonist journey
was drawn as a staircase whose height was the *stage index*, so every book — mystery, romance,
progression — produced an identical rising line carrying no information. The fix is that the
axis is chosen from the book's profile and carries a quantity that can fall.

So the assertions here are mostly about *refusing* to draw: an engine with no axis returns
``none`` rather than a staircase, and a cognition curve with no downward move says so in the
caveat instead of presenting itself as a complete reading.
"""

from app.narrative_core.long_novel.adapter import build_journey_section


def test_a_mystery_book_is_measured_in_what_the_reader_knows():
    section = build_journey_section(
        axes={"engine": "mystery", "pov": "single_lead"},
        chapter_count=806,
        suspense_actions=[
            {"action_kind": "partial", "chapter_ref": 10, "information_added": "教堂里有低语"},
            {"action_kind": "reveal", "chapter_ref": 40, "information_added": "低语来自葛莫娜"},
            {"action_kind": "twist", "chapter_ref": 60, "information_added": "葛莫娜早已死了"},
        ],
    )
    assert section["axis"] == "cognition"
    assert [point["value"] for point in section["points"]] == [1.0, 4.0, -1.0]
    assert section["caveat"] == ""  # it has a twist, so nothing to warn about


def test_a_mystery_curve_that_never_falls_says_so_rather_than_looking_complete():
    section = build_journey_section(
        axes={"engine": "mystery"},
        chapter_count=806,
        suspense_actions=[{"action_kind": "reveal", "chapter_ref": c} for c in (5, 300, 700)],
    )
    assert section["axis"] == "cognition"
    assert "没有抽到一次反转" in section["caveat"]


def test_a_progression_book_is_measured_on_the_ladder_the_book_names():
    section = build_journey_section(
        axes={"engine": "progression", "pov": "single_lead"},
        chapter_count=1299,
        power_beats=[
            {"entity_ref": "陈伶", "chapter_ref": 41, "kind": "promote", "level": "第一阶", "rank": 1.0},
            {"entity_ref": "陈伶", "chapter_ref": 171, "kind": "gain", "level": "六阶", "rank": 6.0},
            {"entity_ref": "陈伶", "chapter_ref": 324, "kind": "promote", "level": "第三阶", "rank": 3.0},
            {"entity_ref": "韩蒙", "chapter_ref": 32, "kind": "demote", "level": "五阶", "rank": 5.0},
        ],
    )
    assert section["axis"] == "ladder"
    assert section["lead"] == "陈伶"
    assert section["ticks"] == ["1阶", "2阶", "3阶", "4阶", "5阶", "6阶"]
    # Every ranked reading of the lead is on the line; 韩蒙's is not, because he is not the
    # lead. What keeps a skill's rank out of the series is the extraction prompt, not a
    # filter here — see `_LADDER_UP` for why that moved.
    connected = [p for p in section["points"] if p["load_bearing"]]
    assert [p["chapter"] for p in connected] == [41, 171, 324]
    assert section["caveat"] == ""  # 171 → 324 falls, so the ladder is not suspiciously monotone


def test_a_ladder_that_never_falls_is_flagged_rather_than_shown_as_a_clean_climb():
    section = build_journey_section(
        axes={"engine": "progression"}, chapter_count=1299,
        power_beats=[
            {"entity_ref": "甲", "chapter_ref": c, "kind": "promote", "level": f"{n}阶", "rank": float(n)}
            for c, n in ((10, 1), (200, 2), (900, 3))
        ],
    )
    assert "一次下降都没有" in section["caveat"]


def test_another_characters_demotion_is_plotted_but_never_joins_the_lead_line():
    section = build_journey_section(
        axes={"engine": "progression"},
        chapter_count=1299,
        power_beats=[
            {"entity_ref": "陈伶", "chapter_ref": 41, "kind": "promote", "level": "一阶", "rank": 1.0},
            {"entity_ref": "陈伶", "chapter_ref": 90, "kind": "promote", "level": "二阶", "rank": 2.0},
            {"entity_ref": "韩蒙", "chapter_ref": 32, "kind": "demote", "level": "五阶", "rank": 5.0},
        ],
    )
    other = [p for p in section["points"] if p["who"] == "韩蒙"]
    assert other and not other[0]["load_bearing"]


def test_an_ensemble_book_gets_screen_time_whatever_its_engine_is():
    section = build_journey_section(
        axes={"engine": "mystery", "pov": "ensemble"},
        chapter_count=806,
        screen_time={"邓肯": [4, 2, 0], "凡娜": [0, 2, 1]},
        screen_time_spans={"邓肯": (3, 700, 451), "凡娜": (29, 806, 127)},
        bins=3,
    )
    assert section["axis"] == "screen_time"
    duncan = next(band for band in section["bands"] if band["name"] == "邓肯")
    assert duncan["share"] == [1.0, 0.5, 0.0]
    assert duncan["first_chapter"] == 3 and duncan["chapters"] == 451


def test_a_bin_nobody_appears_in_is_a_gap_not_an_even_split():
    section = build_journey_section(
        axes={"pov": "ensemble"}, chapter_count=100,
        screen_time={"甲": [1, 0], "乙": [1, 0]}, bins=2,
    )
    assert [band["share"] for band in section["bands"]] == [[0.5, 0.0], [0.5, 0.0]]


def test_an_engine_with_nothing_counted_refuses_to_draw_rather_than_inventing_a_staircase():
    """每种引擎现在都指定了一条轴，但轴名不是画图的许可证——数不出点就仍然不画。

    这条用例原先钉的是「情感/种田/单元 永远是 none」。那是当时的事实，不是该守的规矩：
    该守的是「没有清点结果就不画线」。轴名在没有点时回落为 none，因为 none 的含义正是
    「这本书没有可画的纵轴」，客户端据此改为说明原因。
    """
    for engine in ("romance", "slice_of_life", "episodic_transmigration", "mystery", ""):
        section = build_journey_section(axes={"engine": engine}, chapter_count=500)
        assert section["axis"] == "none"
        assert section["availability"] == "unavailable"
        assert section["points"] == []


def test_every_engine_names_an_axis_and_draws_it_when_the_facts_are_there():
    """四种引擎此前一条线都画不出来，因为轴表里只有悬疑和升级流。"""
    ledger = [
        {"stage_name": "一", "chapter_start": 1, "chapter_end": 16,
         "gained": ["a", "b"], "lost": ["c"], "gained_total": 2, "lost_total": 1},
        {"stage_name": "二", "chapter_start": 17, "chapter_end": 40,
         "gained": ["d"], "lost": ["e", "f", "g"], "gained_total": 1, "lost_total": 3},
    ]
    rels = [
        {"from_entity_ref": "甲", "to_entity_ref": "乙", "relation": "缓和", "chapter_ref": 5, "change_kind": "warm"},
        {"from_entity_ref": "甲", "to_entity_ref": "乙", "relation": "吵翻", "chapter_ref": 20, "change_kind": "rift"},
        {"from_entity_ref": "丙", "to_entity_ref": "丁", "relation": "与主角无关", "chapter_ref": 9, "change_kind": "warm"},
    ]
    romance = build_journey_section(
        axes={"engine": "romance"}, chapter_count=76, ledger=ledger,
        relationship_changes=rels, lead="甲",
    )
    assert romance["axis"] == "relationship"
    # 与主角无关的那一对不计入主角的历程。
    assert [p["chapter"] for p in romance["points"]] == [5, 20]
    # 能跌，正是这条轴存在的理由。
    assert romance["points"][1]["value"] < romance["points"][0]["value"]

    for engine in ("slice_of_life", "episodic_transmigration"):
        section = build_journey_section(
            axes={"engine": engine}, chapter_count=76, ledger=ledger,
        )
        assert section["axis"] == "stakes"
        assert [p["value"] for p in section["points"]] == [1.0, -1.0]


def test_an_axis_that_came_up_empty_falls_back_to_stakes_rather_than_to_a_blank_page():
    """得失累计只要每一程的得失条数，任何书都有——所以它同时是本轴也是兜底。"""
    ledger = [
        {"stage_name": "一", "chapter_start": 1, "chapter_end": 16,
         "gained": ["a"], "lost": [], "gained_total": 1, "lost_total": 0},
    ]
    section = build_journey_section(
        axes={"engine": "romance"}, chapter_count=76, ledger=ledger,
        relationship_changes=[], lead="甲",
    )
    assert section["axis"] == "stakes"
    assert section["points"]


def test_a_progression_book_with_no_named_rank_does_not_pretend_to_have_a_ladder():
    section = build_journey_section(
        axes={"engine": "progression"}, chapter_count=500,
        power_beats=[{"entity_ref": "某人", "chapter_ref": 5, "kind": "gain", "level": "", "rank": None}],
    )
    assert section["availability"] == "unavailable"
    assert section["points"] == []


def test_every_journey_shape_validates_as_the_contract_model():
    """The dict looked right and the model rejected it.

    ``conform`` types an unsupplied field as ``""``, which is correct for a string and wrong
    for a ``StrEnum``: every builder returned ``availability=""`` and every assertion in this
    file passed, because they all read the dict. The whole pipeline then failed on the last
    step of a full run. Validating through the model is the only assertion that would have
    caught it, so it is made once for all three shapes.
    """
    from app.narrative_core.whole_book_v2.contracts import JourneyResult

    shapes = [
        build_journey_section(axes={"engine": "mystery"}, chapter_count=100,
                              suspense_actions=[{"action_kind": "reveal", "chapter_ref": 3}]),
        build_journey_section(axes={"engine": "progression"}, chapter_count=100,
                              power_beats=[{"entity_ref": "甲", "chapter_ref": 3,
                                            "kind": "promote", "level": "一阶", "rank": 1.0}]),
        build_journey_section(axes={"pov": "ensemble"}, chapter_count=100,
                              screen_time={"甲": [1, 2]}, screen_time_spans={"甲": (1, 90, 12)},
                              bins=2),
        build_journey_section(axes={"engine": "romance"}, chapter_count=100),
        build_journey_section(axes={}, chapter_count=100),
    ]
    for shape in shapes:
        JourneyResult.model_validate(shape)


def test_the_ledger_drops_projected_costs_and_keeps_what_happened():
    """The measurement this filter exists for.

    A choice's ``costs``/``gains`` describe what an option might bring. On 《深海余烬》 62% of
    the recorded costs begin 「可能」 — risks weighed, not prices paid — which is why the
    「失去」 column read as vague plot summary. Keeping them would make the count 815; dropping
    them makes it 18, and the 18 are things the text says occurred.
    """
    from app.narrative_core.long_novel.adapter import build_stage_ledger

    ledger = build_stage_ledger(
        [{"chapter": 1, "chapter_end": 100, "stage_name": "启航"}],
        lead="邓肯",
        choices=[
            {"entity_ref": "邓肯", "chapter": 10,
             "gains": ["发现罗盘是异常物品", "可能获取情报"],
             "costs": ["放弃橡木街房子", "可能被识破", "或许无法脱身"]},
            {"entity_ref": "凡娜", "chapter": 20, "gains": ["履行职责"], "costs": ["可能死亡"]},
        ],
    )
    stage = ledger[0]
    assert stage["gained"] == ["发现罗盘是异常物品"]
    assert stage["lost"] == ["放弃橡木街房子"]
    # 凡娜 is not the lead, so none of her trade-offs are on the protagonist's ledger.
    assert stage["gained_total"] == 1 and stage["lost_total"] == 1


def test_a_person_is_credited_to_the_stage_they_first_appear_in():
    from app.narrative_core.long_novel.adapter import build_stage_ledger

    ledger = build_stage_ledger(
        [{"chapter": 1, "chapter_end": 100, "stage_name": "一"},
         {"chapter": 101, "chapter_end": 200, "stage_name": "二"}],
        lead="邓肯",
        meetings=[
            {"chapter": 9, "other": "爱丽丝", "relation": "从敌对到接纳为船员"},
            {"chapter": 150, "other": "爱丽丝", "relation": "信任加深"},
            {"chapter": 140, "other": "凡娜", "relation": "从陌生到友好"},
        ],
    )
    assert [m["name"] for m in ledger[0]["met"]] == ["爱丽丝"]
    # 凡娜 first appears at chapter 140, which is stage two — a meeting belongs to the stage it
    # happened in, not to the first stage that mentions the person.
    assert [m["name"] for m in ledger[1]["met"]] == ["凡娜"]
    assert all(m["name"] != "爱丽丝" for m in ledger[1]["met"])  # a later change is not a meeting


def test_repeated_phrasing_yields_the_specific_one_not_eight_copies():
    from app.narrative_core.long_novel.adapter import build_stage_ledger

    ledger = build_stage_ledger(
        [{"chapter": 1, "chapter_end": 100, "stage_name": "一"}],
        lead="甲",
        choices=[{"entity_ref": "甲", "chapter": 5,
                  # Exact repeats collapse; so does a phrase literally contained in a longer
                  # one. 「获取情报」 and 「获取邪教徒的情报」 are *not* such a pair — the
                  # characters are not contiguous — and both survive, which is correct: they
                  # say different things.
                  "gains": ["获取情报", "获取情报", "获取情报并撤离", "拯救城邦"], "costs": []}],
    )
    assert ledger[0]["gained"] == ["获取情报并撤离", "拯救城邦"]
    assert ledger[0]["gained_total"] == 4  # the count still reflects everything extracted


def test_no_stages_means_no_ledger_rather_than_an_empty_frame():
    from app.narrative_core.long_novel.adapter import build_stage_ledger

    assert build_stage_ledger([], lead="甲") == []
    assert build_stage_ledger([{"chapter": 1, "chapter_end": 9, "stage_name": "一"}], lead="") == []


def test_a_reversal_must_overturn_something_earlier():
    """Two of seven answers on a real 90-row list pointed the wrong way.

    The chapter numbers are already in hand, so a backwards reversal is caught by arithmetic
    rather than shown to a reader. Filtering a model's answer against data the engine already
    holds is not a second opinion — it is the check that makes the answer usable.
    """
    from app.narrative_core.long_novel.orchestrator import RunCoordinator

    reveals = [
        {"id": "R1", "chapter": 76, "text": "雪莉自称不是湮灭教派"},
        {"id": "R2", "chapter": 210, "text": "他们称雪莉是历史中的漏洞"},
        {"id": "R3", "chapter": 629, "text": "山羊头说萨斯洛卡死了"},
    ]
    accepted = RunCoordinator._accept_reversals(reveals, {"reversals": [
        {"id": "R2", "overturns": "R1", "why": "雪莉与教派有关联"},
        {"id": "R1", "overturns": "R3", "why": "倒序，第76章不可能推翻第629章"},
        {"id": "R2", "overturns": "R9", "why": "悬空 id"},
        {"id": "R3", "overturns": "R3", "why": "自己推翻自己"},
    ]})
    assert [row["chapter"] for row in accepted] == [210]
    assert accepted[0]["overturns_chapter"] == 76


def test_without_a_reversal_finder_the_cognition_curve_simply_cannot_fall():
    """Stated rather than hidden: a run with no reversal call produces a monotone curve.

    That is the honest outcome — block extraction chose `twist` once across 806 chapters — and
    the caveat on the section says so. What must not happen is the curve looking complete.
    """
    section = build_journey_section(
        axes={"engine": "mystery"}, chapter_count=806,
        suspense_actions=[{"action_kind": "reveal", "chapter_ref": c} for c in (10, 300, 700)],
    )
    values = [point["value"] for point in section["points"]]
    assert values == sorted(values)
    assert "没有抽到一次反转" in section["caveat"]
