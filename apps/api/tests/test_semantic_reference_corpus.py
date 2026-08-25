import json
from types import SimpleNamespace

from app.narrative_core.material_lab.service import _legacy_material_dict
from app.narrative_core.material_lab.semantic_reference_corpus import (
    EvidenceAuditBatch,
    EvidenceAuditItem,
    EvidenceCandidate,
    QualityScores,
    ReviewedSemanticMaterial,
    SemanticExtractionBatch,
    SemanticMaterialDraft,
    SemanticReviewBatch,
    filter_ancient_domain_knowledge,
    filter_disaster_domain_knowledge,
    filter_contemporary_domain_knowledge,
    filter_fantasy_domain_knowledge,
    filter_infinite_flow_domain_knowledge,
    filter_farming_domain_knowledge,
    filter_scifi_domain_knowledge,
    filter_urban_domain_knowledge,
    filter_xianxia_domain_knowledge,
    validate_drafts,
    validate_review,
    apply_evidence_audit,
)


def evidence(position: str = "opening") -> EvidenceCandidate:
    return EvidenceCandidate(
        evidence_id="R-1234567890-C0001-P0001",
        source_title="测试小说",
        chapter_index=1,
        chapter_title="第一章",
        paragraph_index=1,
        position=position,
        suggested_category="opening_anomaly",
        text="报案人要求寻找失踪多年的亲属，档案却显示那名亲属早已由报案人亲自办理死亡登记。",
    )


def draft() -> SemanticMaterialDraft:
    return SemanticMaterialDraft(
        draft_id="d1",
        evidence_ids=["R-1234567890-C0001-P0001"],
        category_key="opening_anomaly",
        subcategory_key="first_anomaly",
        title="报失踪者曾报死亡",
        creative_material="老人来报亲属失踪，档案却显示二十年前正是他本人为对方办理了死亡登记。",
        reusable_pattern="求助行为与旧档案中的本人行为互相矛盾",
        mechanism="当前诉求撞上无法解释的历史记录",
        suspense_question="他忘了过去，还是在试探调查人员？",
        applicable_stage="开篇",
        tags=["档案", "身份矛盾"],
    )


def test_validate_drafts_keeps_cited_concrete_material():
    item = evidence()
    accepted, rejected = validate_drafts(
        SemanticExtractionBatch(materials=[draft()]),
        evidence_by_id={item.evidence_id: item},
    )
    assert [row.draft_id for row in accepted] == ["d1"]
    assert rejected == []


def test_validate_drafts_rejects_opening_with_non_opening_evidence():
    item = evidence(position="middle")
    accepted, rejected = validate_drafts(
        SemanticExtractionBatch(materials=[draft()]),
        evidence_by_id={item.evidence_id: item},
    )
    assert accepted == []
    assert rejected == ["d1:opening_evidence_out_of_scope"]


def test_validate_drafts_accepts_farming_knowledge_category():
    item = EvidenceCandidate(
        evidence_id="R-abcdef1234-C0012-P0008",
        source_title="测试种田文",
        chapter_index=12,
        chapter_title="春耕",
        paragraph_index=8,
        position="middle",
        suggested_category="crop_cultivation",
        text="稻种先在温水里浸过，等种壳露出白芽，再均匀撒进已经整平的秧田，出苗才会整齐。",
    )
    farming = SemanticMaterialDraft(
        draft_id="farm-1",
        evidence_ids=[item.evidence_id],
        category_key="crop_cultivation",
        subcategory_key="sowing",
        title="稻种催芽后下秧田",
        creative_material="稻种先浸水催芽，种壳露白后再均匀撒入整平的秧田，可以让出苗更整齐。",
        reusable_pattern="浸种催芽后均匀播入整平秧田",
        mechanism="提前催芽并控制落种均匀度",
        suspense_question="",
        applicable_stage="全书",
        tags=["稻种", "催芽", "育苗"],
    )
    accepted, rejected = validate_drafts(
        SemanticExtractionBatch(materials=[farming]),
        evidence_by_id={item.evidence_id: item},
        genre_slug="zhongtian",
    )
    assert [row.draft_id for row in accepted] == ["farm-1"]
    assert rejected == []


def test_validate_drafts_accepts_ancient_social_rule_category():
    item = EvidenceCandidate(
        evidence_id="R-fedcba9876-C0020-P0012",
        source_title="测试古言",
        chapter_index=20,
        chapter_title="移交中馈",
        paragraph_index=12,
        position="middle",
        suggested_category="household_strife",
        text="老夫人命主母把库房钥匙、各房账册和月例名册一并交出，接手的人核对无误后才可支取府中银米。",
    )
    ancient = SemanticMaterialDraft(
        draft_id="ancient-1",
        evidence_ids=[item.evidence_id],
        category_key="household_strife",
        subcategory_key="resource",
        title="钥匙账册标志中馈移交",
        creative_material="府中移交中馈时需同时交割库房钥匙、账册和月例名册，接手者核对后才能支取银米。",
        reusable_pattern="以钥匙和账册完成府中财权交割",
        mechanism="实物凭据决定资源调动权限",
        suspense_question="",
        applicable_stage="中段",
        tags=["中馈", "账册", "库房钥匙"],
    )
    accepted, rejected = validate_drafts(
        SemanticExtractionBatch(materials=[ancient]),
        evidence_by_id={item.evidence_id: item},
        genre_slug="guyan",
    )
    assert [row.draft_id for row in accepted] == ["ancient-1"]
    assert rejected == []


def test_validate_drafts_accepts_urban_professional_knowledge_category():
    item = EvidenceCandidate(
        evidence_id="R-13579abcde-C0030-P0016",
        source_title="测试都市文",
        chapter_index=30,
        chapter_title="渠道谈判",
        paragraph_index=16,
        position="middle",
        suggested_category="business_knowledge",
        text="区域经销商签合同时先付首批货款，此后按月结算；若上月货款未结清，厂家便暂停下一批发货。",
    )
    urban = SemanticMaterialDraft(
        draft_id="urban-1",
        evidence_ids=[item.evidence_id],
        category_key="business_knowledge",
        subcategory_key="transaction",
        title="月结账款约束后续发货",
        creative_material="区域经销商先付首批货款，后续改为按月结算；上月未回款时，厂家暂停下一批发货。",
        reusable_pattern="以回款状态控制经销渠道的后续供货",
        mechanism="账期与供货权相互制约",
        suspense_question="",
        applicable_stage="全书",
        tags=["经销", "回款", "供货"],
    )
    accepted, rejected = validate_drafts(
        SemanticExtractionBatch(materials=[urban]),
        evidence_by_id={item.evidence_id: item},
        genre_slug="dushi",
    )
    assert [row.draft_id for row in accepted] == ["urban-1"]
    assert rejected == []


def test_validate_drafts_accepts_scifi_rule_category():
    item = EvidenceCandidate(
        evidence_id="R-24680abcde-C0042-P0009",
        source_title="测试科幻文",
        chapter_index=42,
        chapter_title="停电",
        paragraph_index=9,
        position="middle",
        suggested_category="tech_rule",
        text="指挥机甲的护盾、卫星导航和激光枪共用主电网，供电设施瘫痪后，这三套系统同时停用，只剩机械关节还能动作。",
    )
    scifi = SemanticMaterialDraft(
        draft_id="scifi-1",
        evidence_ids=[item.evidence_id],
        category_key="tech_rule",
        subcategory_key="rule",
        title="主电网失效连锁关闭远程系统",
        creative_material="指挥机甲的护盾、卫星导航和激光武器共用主电网；供电瘫痪后三者同时停用，只剩机械动作。",
        reusable_pattern="共用供电系统使多个作战模块同步失效",
        mechanism="单点能源故障压缩机甲行动边界",
        suspense_question="",
        applicable_stage="全书",
        tags=["机甲", "供电", "系统失效"],
    )
    accepted, rejected = validate_drafts(
        SemanticExtractionBatch(materials=[scifi]),
        evidence_by_id={item.evidence_id: item},
        genre_slug="kehuan",
    )
    assert [row.draft_id for row in accepted] == ["scifi-1"]
    assert rejected == []


def test_validate_drafts_accepts_disaster_survival_category():
    item = EvidenceCandidate(
        evidence_id="R-1122334455-C0030-P0012",
        source_title="测试末世文",
        chapter_index=30,
        chapter_title="盘点库存",
        paragraph_index=12,
        position="middle",
        suggested_category="logistics",
        text="仓库每天按登记人数发放口粮，外勤队出发前领取定额，返回后要交回剩余部分，由记录员重新核对库存。",
    )
    disaster = SemanticMaterialDraft(
        draft_id="disaster-1",
        evidence_ids=[item.evidence_id],
        category_key="logistics",
        subcategory_key="rationing",
        title="外勤口粮领取与余量回库",
        creative_material="基地按登记人数配给口粮；外勤队出发前领取定额，返程后交回余量并由记录员更新库存。",
        reusable_pattern="用领取、交回和盘点闭合外勤口粮账目",
        mechanism="定额与库存记录共同限制物资消耗",
        suspense_question="",
        applicable_stage="全书",
        tags=["口粮", "配给", "库存"],
    )
    accepted, rejected = validate_drafts(
        SemanticExtractionBatch(materials=[disaster]),
        evidence_by_id={item.evidence_id: item},
        genre_slug="moshi",
    )
    assert [row.draft_id for row in accepted] == ["disaster-1"]
    assert rejected == []


def test_validate_drafts_accepts_remaining_genre_knowledge_categories():
    cases = (
        ("xuanhuan", "craft_economy", "trade", "拍卖行登记材料后先由鉴定师估价，再按场次收取保证金；流拍时退还原物。"),
        ("xianxia", "exchange_economy", "merit", "弟子交回任务凭证后登记贡献，丹药与洞府时限分别计价，贡献不足不能先行领取。"),
        ("xianyan", "era_life", "ration", "家庭按人口领取粮票和布票，供销社购买定量商品时票证与现金缺一不可。"),
        ("wuxianliu", "rule", "explicit", "入住须知规定午夜后不得开门，违反者立即失去房间保护并被判定出局。"),
    )
    for index, (genre, category, subcategory, material) in enumerate(cases, 1):
        item = EvidenceCandidate(
            evidence_id=f"R-9988776655-C00{index:02d}-P0001",
            source_title="测试小说",
            chapter_index=index,
            chapter_title="规则",
            paragraph_index=1,
            position="middle",
            suggested_category=category,
            text=material + " 这项安排由现场记录员明确说明并当场执行。",
        )
        knowledge = SemanticMaterialDraft(
            draft_id=f"knowledge-{index}",
            evidence_ids=[item.evidence_id],
            category_key=category,
            subcategory_key=subcategory,
            title=f"可核对规则{index}",
            creative_material="可复用规则要求：" + material,
            reusable_pattern="凭据、资源与后果形成可核对规则",
            mechanism="明确条件限制后续资源或行动",
            suspense_question="",
            applicable_stage="全书",
            tags=["规则"],
        )
        accepted, rejected = validate_drafts(
            SemanticExtractionBatch(materials=[knowledge]),
            evidence_by_id={item.evidence_id: item},
            genre_slug=genre,
        )
        assert [row.draft_id for row in accepted] == [f"knowledge-{index}"]
        assert rejected == []


def test_validate_review_requires_all_scores_at_least_four():
    item = evidence()
    source = draft()
    reviewed = ReviewedSemanticMaterial(
        **source.model_dump(),
        scores=QualityScores(
            concreteness=5,
            reusability=5,
            information_gap=5,
            evidence_fidelity=3,
            expression_quality=5,
        ),
    )
    accepted, rejected = validate_review(
        SemanticReviewBatch(accepted=[reviewed]),
        source_drafts=[source],
        evidence_by_id={item.evidence_id: item},
    )
    assert accepted == []
    assert rejected == ["d1:quality_below_four"]


def test_farming_domain_filter_rejects_plot_only_card():
    source = draft()
    farming_plot = ReviewedSemanticMaterial(
        **source.model_dump(exclude={
            "category_key", "subcategory_key", "title", "creative_material",
            "reusable_pattern", "mechanism", "suspense_question",
        }),
        category_key="business",
        subcategory_key="first_money",
        title="债务危机",
        creative_material="欠债无力偿还，债主威胁抓人抵债，家人只能紧急筹钱。",
        reusable_pattern="抓人抵债迫使家人筹款",
        mechanism="债务冲突推动剧情",
        suspense_question="",
        scores=QualityScores(
            concreteness=5,
            reusability=5,
            information_gap=5,
            evidence_fidelity=5,
            expression_quality=5,
        ),
    )
    accepted, rejected = filter_farming_domain_knowledge([farming_plot])
    assert accepted == []
    assert rejected == ["d1:off_topic_farming_plot"]


def test_ancient_domain_filter_rejects_favor_only_card():
    source = draft()
    favor_plot = ReviewedSemanticMaterial(
        **source.model_dump(exclude={
            "category_key", "subcategory_key", "title", "creative_material",
            "reusable_pattern", "mechanism", "suspense_question",
        }),
        category_key="palace",
        subcategory_key="intrigue",
        title="妃嫔争宠靠家族",
        creative_material="妃嫔失宠后由家族活动关系，重新争宠，但仍受皇后压制。",
        reusable_pattern="争宠依靠家族关系运作",
        mechanism="后宫人物输赢",
        suspense_question="",
        scores=QualityScores(
            concreteness=5,
            reusability=5,
            information_gap=5,
            evidence_fidelity=5,
            expression_quality=5,
        ),
    )
    accepted, rejected = filter_ancient_domain_knowledge([favor_plot])
    assert accepted == []
    assert rejected == ["d1:off_topic_ancient_plot"]


def test_urban_domain_filter_rejects_faceslap_only_card():
    source = draft()
    faceslap_plot = ReviewedSemanticMaterial(
        **source.model_dump(exclude={
            "category_key", "subcategory_key", "title", "creative_material",
            "reusable_pattern", "mechanism", "suspense_question",
        }),
        category_key="workplace_knowledge",
        subcategory_key="role_division",
        title="隐藏身份当众打脸",
        creative_material="主角公开老板身份后当众打脸上司，公司同事都震惊不已。",
        reusable_pattern="隐藏身份曝光后打脸职场对手",
        mechanism="身份反差制造爽点",
        suspense_question="",
        scores=QualityScores(
            concreteness=5,
            reusability=5,
            information_gap=5,
            evidence_fidelity=5,
            expression_quality=5,
        ),
    )
    accepted, rejected = filter_urban_domain_knowledge([faceslap_plot])
    assert accepted == []
    assert rejected == ["d1:off_topic_urban_plot"]


def test_urban_domain_filter_rejects_fictional_industry_rule():
    source = draft()
    fictional_rule = ReviewedSemanticMaterial(
        **source.model_dump(exclude={
            "category_key", "subcategory_key", "title", "creative_material",
            "reusable_pattern", "mechanism", "suspense_question",
        }),
        category_key="finance_knowledge",
        subcategory_key="investment",
        title="地下商界的投资失败公告制度",
        creative_material="地下商界要求投资失败者公开公告，并独自承担全部损失。",
        reusable_pattern="以公开认错约束投资者",
        mechanism="虚构组织规则推动人物受罚",
        suspense_question="",
        scores=QualityScores(
            concreteness=5,
            reusability=5,
            information_gap=5,
            evidence_fidelity=5,
            expression_quality=5,
        ),
    )
    accepted, rejected = filter_urban_domain_knowledge([fictional_rule])
    assert accepted == []
    assert rejected == ["d1:off_topic_urban_plot"]


def test_scifi_domain_filter_rejects_combat_only_card():
    source = draft()
    combat_plot = ReviewedSemanticMaterial(
        **source.model_dump(exclude={
            "category_key", "subcategory_key", "title", "creative_material",
            "reusable_pattern", "mechanism", "suspense_question",
        }),
        category_key="tech_rule",
        subcategory_key="device",
        title="获得机甲后实力提升",
        creative_material="主角获得机甲后实力提升，在比赛中击败了强大敌人。",
        reusable_pattern="获得机甲推动角色升级",
        mechanism="装备升级制造战斗爽点",
        suspense_question="",
        scores=QualityScores(
            concreteness=5,
            reusability=5,
            information_gap=5,
            evidence_fidelity=5,
            expression_quality=5,
        ),
    )
    accepted, rejected = filter_scifi_domain_knowledge([combat_plot])
    assert accepted == []
    assert rejected == ["d1:off_topic_scifi_plot"]


def test_scifi_domain_filter_rejects_game_broadcast_and_unverified_medicine():
    source = draft()
    cards = []
    for title, material in (
        ("违规全服播报", "系统全服通报违规行为，把一次任务冲突公开给所有玩家。"),
        ("万能果实治疗", "万生丑果可以治愈血栓和脑梗，而且没有任何副作用。"),
    ):
        cards.append(ReviewedSemanticMaterial(
            **source.model_dump(exclude={
                "category_key", "subcategory_key", "title", "creative_material",
            }),
            category_key="institution",
            subcategory_key="control",
            title=title,
            creative_material=material,
            scores=QualityScores(
                concreteness=5,
                reusability=5,
                information_gap=5,
                evidence_fidelity=5,
                expression_quality=5,
            ),
        ))

    accepted, rejected = filter_scifi_domain_knowledge(cards)
    assert accepted == []
    assert rejected == [
        "d1:off_topic_scifi_plot",
        "d1:off_topic_scifi_plot",
    ]


def test_disaster_domain_filter_rejects_kill_and_upgrade_plot():
    source = draft()
    plot = ReviewedSemanticMaterial(
        **source.model_dump(exclude={
            "category_key", "subcategory_key", "title", "creative_material",
            "reusable_pattern", "mechanism", "suspense_question",
        }),
        category_key="ability",
        subcategory_key="awaken",
        title="击杀尸群获得异能",
        creative_material="主角击杀尸群后获得异能，实力提升并成功逃脱包围。",
        reusable_pattern="击杀敌人后获得异能和系统奖励",
        mechanism="战斗升级制造爽点",
        suspense_question="",
        scores=QualityScores(
            concreteness=5,
            reusability=5,
            information_gap=5,
            evidence_fidelity=5,
            expression_quality=5,
        ),
    )
    accepted, rejected = filter_disaster_domain_knowledge([plot])
    assert accepted == []
    assert rejected == ["d1:off_topic_disaster_plot"]


def test_remaining_genre_filters_reject_plot_only_cards():
    source = draft()
    cases = (
        (filter_fantasy_domain_knowledge, "越级击败强敌并震惊全场", "off_topic_fantasy_plot"),
        (filter_xianxia_domain_knowledge, "越阶杀敌后夺得宝物", "off_topic_xianxia_plot"),
        (filter_contemporary_domain_knowledge, "霸总强吻后男主吃醋", "off_topic_contemporary_plot"),
        (filter_infinite_flow_domain_knowledge, "击杀Boss后抽到神装", "off_topic_infinite_flow_plot"),
    )
    for index, (filter_fn, material, code) in enumerate(cases, 1):
        card = ReviewedSemanticMaterial(
            **source.model_dump(exclude={"draft_id", "title", "creative_material"}),
            draft_id=f"plot-{index}",
            title=material,
            creative_material=material + "，人物因此获得下一阶段优势。",
            scores=QualityScores(
                concreteness=5,
                reusability=5,
                information_gap=5,
                evidence_fidelity=5,
                expression_quality=5,
            ),
        )
        accepted, rejected = filter_fn([card])
        assert accepted == []
        assert rejected == [f"plot-{index}:{code}"]


def test_evidence_audit_requires_exact_supporting_quote():
    item = evidence()
    source = draft()
    reviewed = ReviewedSemanticMaterial(
        **source.model_dump(),
        scores=QualityScores(
            concreteness=5,
            reusability=5,
            information_gap=5,
            evidence_fidelity=5,
            expression_quality=5,
        ),
    )
    audit = EvidenceAuditBatch(items=[EvidenceAuditItem(
        draft_id="d1",
        evidence_ids=source.evidence_ids,
        verdict="rewritten",
        creative_material=source.creative_material,
        unsupported_claims=["删除补造"],
        supporting_quotes=["原文里没有的句子"],
    )])
    accepted, rejected = apply_evidence_audit(
        audit,
        reviewed=[reviewed],
        evidence_by_id={item.evidence_id: item},
    )
    assert accepted == []
    assert rejected == ["d1:audit_quote_mismatch"]


def test_semantic_corpus_nested_evidence_is_visible_to_api():
    row = SimpleNamespace(
        source_pattern_id="corpus:semantic:abc",
        source_material_id="m1",
        source_book_title="测试小说",
        source_evidence_ids_json=json.dumps({
            "evidence": [{
                "evidence_id": "R-1234567890-C0001-P0001",
                "chapter_index": 1,
                "chapter_title": "第一章",
                "paragraph_index": 1,
                "text": "档案显示，被寻找的人早已由报案人本人办理死亡登记。",
            }]
        }, ensure_ascii=False),
        genre_slug="xuanyi",
        material_type="knowledge",
        category_key="opening_anomaly",
        category_label="开篇异常",
        subcategory_key="first_anomaly",
        subcategory_label="首个异常",
        title="死亡档案",
        concise_example="老人寻找失踪亲属，档案却显示他曾为对方办理死亡登记。",
        core_pattern="当前诉求与本人旧记录矛盾",
        mechanism="信息冲突",
        suspense_question="为何前后矛盾？",
        applicable_stage="开篇",
        applicable_scene="创作构思",
        emotion="悬疑",
        tags_json="[]",
        quality_score=92,
        confidence=0.8,
        is_primary_variant=1,
    )
    item = _legacy_material_dict(row)
    assert item["source_paragraph_ids"] == ["R-1234567890-C0001-P0001"]
    assert item["source_excerpt"].startswith("档案显示")
    assert item["verification_label"] == "本地参考小说 · 第一章 · 段落证据已核对"
