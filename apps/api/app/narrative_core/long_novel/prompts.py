"""L1 prompt contract (03 §2.6, §8).

The prompt is part of the frozen contract, not decoration: its content hash enters
``semantic_compat_key``, so changing the wording invalidates reuse rather than silently
altering what "the same extraction" means.

Two instructions here are doing the real work:

**Every fact must cite a paragraph anchor.** A fact with no anchor cannot be traced, cannot
be keyed (``fact_key`` is derived partly from its primary evidence), and cannot be shown to
a reader with a quote. Making this structural rather than optional is what separates this
engine from one that produces confident unsourced summaries.

**Do not interpret.** Normalised pacing scores, act structure and canonical character
identity all require whole-book knowledge that a single block does not have. Asking for them
here would get plausible numbers invented from a fragment, which is worse than not asking.
"""

from __future__ import annotations

import hashlib

from app.narrative_core.long_novel.contracts.density import DensityProfile

__all__ = [
    "SYSTEM_PROMPT",
    "ASSESSMENT_VOCABULARY",
    "STAGE_INSTRUCTION",
    "TOPIC_INSTRUCTION",
    "FINAL_INSTRUCTION",
    "build_assessment_instruction",
    "build_user_prompt",
    "prompt_template_hash",
    "PROFILE_SAMPLE_SYSTEM_PROMPT",
    "PROFILE_SAMPLE_INSTRUCTION",
    "build_profile_sample_prompt",
    "REVERSAL_INSTRUCTION",
    "build_reversal_prompt",
    "SUSPENSE_PAIRING_INSTRUCTION",
    "build_suspense_pairing_prompt",
]

#: Stated to the model because the contract's enums are closed. Without them a model returns
#: reasonable-sounding names like "story" or "characters" that cannot be rendered, and the
#: engine has to drop a judgement that was already paid for.
ASSESSMENT_VOCABULARY = """dimension 只能取：story_structure, protagonist_growth, character_relationships, suspense_payoff, pacing, chapter_efficiency
rating 只能取：A, A-, B+, B, B-, C, D
每个 dimension 必须同时给出 dimension、rating、conclusion。给不出评级就不要输出该维度。
strengths 每条需要：title, why_good, chapter_start, chapter_end
issues 每条需要：issue_id, priority(P0/P1/P2), category, symptom, root_cause, reader_impact, possible_direction, chapter_start, chapter_end"""


SYSTEM_PROMPT = """你是小说文本的事实抽取器。你的唯一任务是从给定正文中抽取**可核对的事实**，并以严格 JSON 返回。

绝对规则：

1. 只输出 JSON，不要代码块围栏，不要任何解释文字。
2. 正文按 `=== 第 K 章 ===` 分章，每个自然段前有 `[p:N]` 标记。所有 `chapter_ref` 必须填该章的 K。**每一条事实都必须在 `evidence` 里引用至少一个 `paragraph_ref`**，且该 N 必须真实出现在正文中。禁止引用不存在的 N。
3. 只抽取正文中**写明或可直接指认**的内容。不要推断全书层面的信息：不要给 0–100 的节奏评分，不要判断幕结构，不要断定两个称呼是不是同一个人（除非正文明说）。
4. `mentions` 里的 `surface_norm` 必须是正文中**原样出现的字符串**。不要写成规范化后的名字，不要写代词指代的对象。
5. 严格遵守下面给出的数量上限。宁可少给，不要超限。超限的响应会被整体拒绝。
6. `chapter_signals` **每章恰好一条，一条不能多一条不能少**。正文里出现了几个 `=== 第 K 章 ===`，就必须返回几条，`chapter_ref` 分别为各章的 K。
7. `chapter_signals` 里的数字是**清点结果**，必须逐章真实统计。一章正文里有对话就一定有 `dialogue_paragraphs > 0`。整块的计数全是 0 的响应会被拒绝。

字段含义：
- `chapter_signals`：**逐章清点段落数量**，不是打分。`dialogue_paragraphs` 数该章有对话的段落数；
  `action_paragraphs` 数以动作推进为主的段落数；`interiority_paragraphs` 数写心理活动的段落数；
  `scene_breaks` 数场景切换次数；`new_information_beats` 数该章给出新信息的次数；
  `hook_present` 表示章末是否留了钩子。这几个数字决定全书节奏曲线，**必须真实清点**。
- `events`：发生了什么，`summary` ≤50 字。
- `character_state_changes`：某人状态从 A 变成 B。
- `causal_links`：哪件事导致哪件事。
- `suspense_threads` / `suspense_actions`：抛出的疑问，以及后续对它做的动作。
  `action_kind` 必须从这些里选，**按这一处实际起的作用选，不要一律填 advance**：
  `open`(第一次抛出) `advance`(推进但不揭示) `foreshadow`(埋伏笔)
  `misdirect`(把读者往错的方向引) `partial`(只揭示一部分) `reveal`(揭示关键信息)
  `twist`(推翻先前的认知) `resolve`(给出答案) `close`(收束)。
- `relationship_changes` / `goal_changes` / `choices`：关系、目标、抉择的变化。
- `mentions`：人物称呼在某段的出现。`provisional_entities` 把你认为指同一人的 mention 下标归为一组。
- `identity_assertions`：正文**明确**说明两个称呼是/不是同一人时才写。
"""


_SCHEMA_SKELETON = """{
  "chapter_signals": [{"chapter_ref": 1, "dialogue_paragraphs": 12, "action_paragraphs": 7,
                       "interiority_paragraphs": 3, "scene_breaks": 1, "new_information_beats": 4,
                       "hook_present": true, "evidence": [{"paragraph_ref": 1}]}],
  "events": [{"summary": "", "actors": [""], "chapter_ref": 1, "evidence": [{"paragraph_ref": 1}]}],
  "character_state_changes": [{"entity_ref": "", "from_state": "", "to_state": "", "chapter_ref": 1,
                               "evidence": [{"paragraph_ref": 1}]}],
  "causal_links": [{"cause_fact_ref": "", "effect_fact_ref": "", "evidence": [{"paragraph_ref": 1}]}],
  "suspense_threads": [{"question": "", "opened_chapter_ref": 1, "evidence": [{"paragraph_ref": 1}]}],
  "suspense_actions": [{"thread_ref": "", "action_kind": "foreshadow|misdirect|partial|reveal|twist|resolve|advance",
                        "information_added": "", "chapter_ref": 1, "evidence": [{"paragraph_ref": 1}]}],
  "relationship_changes": [{"from_entity_ref": "", "to_entity_ref": "", "relation": "",
                            "evidence": [{"paragraph_ref": 1}]}],
  "goal_changes": [{"entity_ref": "", "goal_text": "", "change_kind": "formed",
                    "evidence": [{"paragraph_ref": 1}]}],
  "choices": [{"entity_ref": "", "decision": "", "costs": [], "gains": [],
               "evidence": [{"paragraph_ref": 1}]}],
  "identity_assertions": [{"left_entity_ref": "", "right_entity_ref": "", "assertion": "uncertain",
                           "evidence": [{"paragraph_ref": 1}]}],
  "mentions": [{"surface_norm": "", "paragraph_ref": 1, "evidence": [{"paragraph_ref": 1}]}],
  "provisional_entities": [{"member_mention_indexes": [0], "display_surface_norm": "", "role_hint": ""}],
  "carry_forward_out": {"open_thread_refs": [], "active_goal_refs": [],
                        "active_continuity_refs": [], "unresolved_note": ""}
}"""


def build_user_prompt(
    *,
    rendered_text: str,
    profile: DensityProfile,
    carry_in_summary: str = "",
    delta_instructions: str = "",
) -> str:
    """Assemble the user frame: caps, schema, carry-in slate, then the text.

    The text goes **last** so the caps and schema are not pushed out of the model's
    attention by a long block — the instruction the model is most likely to drop is the one
    furthest from the end.
    """
    p = profile
    caps = f"""数量上限（每章）：事件 {p.events_per_chapter}，状态变化 {p.state_changes_per_chapter}，因果 {p.causal_per_chapter}，悬念动作 {p.suspense_actions_per_chapter}，人物称呼 {p.mentions_per_chapter}
数量上限（整块）：关系变化 {p.relationships_per_block}，目标变化 {p.goals_per_block}，抉择 {p.choices_per_block}，新悬念 {p.threads_per_block}，身份断言 {p.identities_per_block}，人物聚类 {p.max_provisional_entities}
每条事实的 evidence 最多 {p.evidence_refs_per_fact} 个"""

    # Placed before the schema and the text, and already written as instructions by
    # ``render_carry_in`` — this is the only thing that lets a thread opened four hundred
    # chapters ago be recognised here.
    carry = f"\n{carry_in_summary}\n" if carry_in_summary else ""
    # Empty unless the confirmed profile switched a delta on, so a book with no active delta
    # gets a byte-identical prompt — and therefore the same hash, and therefore reuse.
    extra = f"\n档案附加字段：\n{delta_instructions}\n" if delta_instructions else ""

    return f"""{caps}
{carry}{extra}
按此结构返回（空数组合法，不要省略键）：
{_SCHEMA_SKELETON}

正文：
{rendered_text}"""


def prompt_template_hash(profile: DensityProfile, delta_instructions: str = "") -> str:
    """Content hash of the prompt as sent, minus the novel text.

    Enters ``semantic_compat_key``: reword the prompt and stored assets stop being
    considered the same extraction, which is the honest outcome — they were produced under
    different instructions.

    The active deltas are part of that material. Without them an extraction made for a
    single-lead book would be reused for an ensemble one, and the viewpoint field would be
    missing from a run that reported success.
    """
    material = SYSTEM_PROMPT + _SCHEMA_SKELETON + profile.name + delta_instructions
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# =====================================================================  L2 / L3 / L4 prompts
#
# These four lived in the run harness while only the L1 prompt lived here, which meant the
# engine could extract facts and had no instructions for turning them into the document a
# reader sees — every one of them had to be re-supplied by whatever called it. They are part
# of the contract for the same reason the L1 prompt is: their wording decides what the paid
# calls produce, so it belongs with the code that spends the money.
#
# Each names its fields explicitly. A model asked to "summarise the stage" returns prose that
# has to be parsed; a model given the field list returns the object the section needs.

STAGE_INSTRUCTION = """下面是这一叙事阶段内实际发生的事件、悬念、人物与状态变化。
**只依据这些内容**写解读，不要引入输入中没有的设定。用中文。
字段：title, summary, stage_goal, core_conflict, major_choice, protagonist_state,
key_events(数组), turning_point, ending_state, next_question。"""

TOPIC_INSTRUCTION = """针对 {topic} 主题给出结论，字段：summary, claims。"""

FINAL_INSTRUCTION = """给出全书总览，字段：one_sentence_story, full_summary, protagonist,
initial_state, final_state, core_goal, core_conflict, core_question,
major_storylines(数组), major_suspense(数组), final_climax,
ending_resolution(数组), ending_open_questions(数组), story_skeleton(数组),
primary_genre(主类型), secondary_genres(数组),
narrative_drivers(数组，推动这本书往前走的力量), narrative_traits(数组，叙事特征),
analysis_focus(数组), genre_expectations(数组，这个类型的读者期待什么)。"""

#: The assessment asks for revision priorities *with chapter ranges*, and is given the
#: measured slow stretches to point at. Asked without them, a model returns 1–806 for every
#: priority — technically a range, and useless to someone deciding what to rewrite.
ASSESSMENT_INSTRUCTION = """给出整体评估，字段：overall_summary, dimensions, strengths, issues,
revision_priorities(数组，最多3条，按重要性从高到低排序，每条
{{chapter_ranges:[[起始章,结束章]], direction:改法, preserve:[改动时必须保住的东西]}}),
preserve_list(数组，这本书已经做对、不该动的地方)。
**revision_priorities 的 chapter_ranges 必须指向具体区间，不要写成全书范围。**
{measured_regions}
""" + ASSESSMENT_VOCABULARY


def build_assessment_instruction(regions: object = ()) -> str:
    """The assessment instruction, carrying whatever slow or dense stretches were measured.

    The regions come from the engine's own curve, so this hands the model a finding rather
    than asking it to guess where the book sags.
    """
    lines = []
    for region in regions or ():
        try:
            start = region["chapter_start"]
            end = region["chapter_end"]
            kind = "节奏偏缓" if region.get("type") == "fatigue" else "高强度"
            lines.append(f"- 第 {start}–{end} 章：{kind}")
        except (TypeError, KeyError):
            continue
    measured = ("引擎已测出以下区间，可直接引用：\n" + "\n".join(lines)) if lines else ""
    return ASSESSMENT_INSTRUCTION.format(measured_regions=measured)


# =====================================================================  L0-B 画像采样判读
#
# Read before anything expensive: the type judgement used to arrive with the final synthesis
# call, after every extraction decision had already been made (10_ADAPTIVE_PROFILE_LAYER §1).
#
# The closed vocabularies are spelled out in full because they dispatch behaviour downstream.
# A model that answers "都市异能" instead of one of the listed values has produced something
# no delta can act on — and a value outside the set is dropped, not coerced, so an unlisted
# answer silently costs the axis. Naming the whole set is what prevents that.
#
# The evidence rule is the same one L1 lives by: a judgement with no paragraph anchor cannot
# be checked, and the confirmation screen has to show the user *why* each value was guessed
# before asking them to confirm it.

PROFILE_SAMPLE_SYSTEM_PROMPT = """你是网络小说的类型判读器。你读到的是一本长篇小说的抽样章节：
开头几章的全文，加上全书均匀抽取的若干章。你的任务是判断这本书的基本类型，并以严格 JSON 返回。

只判断，不复述剧情。每一项判断都必须给出依据（引用你读到的段落编号 `[p:N]`）。
判断不出来的项，`value` 留空字符串，不要猜。"""

PROFILE_SAMPLE_INSTRUCTION = """按下面的**封闭取值**填写。取值必须原样使用，不得自创：

- `monetization` 变现与获客模式：
  `fast_food_free` 免费广告流（番茄/七猫/书旗：单章约 1500–2500 字，强冲突前置，章章有钩子）
  `paid_subscription` 付费订阅流（起点/晋江：单章 3000 字以上，容许铺垫，有卷结构）
- `audience` 读者与情感主轴：
  `male_gratification` 男频爽文向（升级、打脸、势力扩张是主要快感来源）
  `female_romance` 女频情感向（感情线是主轴，关系张力与人物互动是主要驱动）
  `neutral` 中性 / 双向（悬疑、科幻、群像权谋等不以上述任一为主轴）
- `engine` 驱动读者往下读的引擎：
  `progression` 升级流 · `mystery` 悬疑推理 · `romance` 情感关系
  `ensemble_politics` 权谋群像 · `slice_of_life` 日常种田
  `episodic_transmigration` 无限流/快穿（单元式结构，一个副本或世界一个单元）
- `pov_hint` 视角结构（仅供参考，最终以全书统计为准）：
  `single_lead` 单主角 · `dual_lead` 双主角/CP 双线 · `ensemble` 群像多线

另外给出：
- `candidate_names`：你在样本里看到的**人物称呼**，原样照抄，最多 20 个。
  这些名字会被拿去在全书正文里逐一计数，所以必须是正文中真实出现的字符串，不要写描述性的词
  （不要写"主角""众人""主要人物"）。
- `opening_notes`：只看第 1 章，`conflict_paragraph` 填冲突首次出现在第几段，
  `hook_paragraph` 填章末钩子在第几段；没有就填 0。

只输出 JSON，结构如下（`evidence` 填段落编号数组）：
{"monetization": {"value": "", "confidence": 0.0, "evidence": [1]},
 "audience": {"value": "", "confidence": 0.0, "evidence": [1]},
 "engine": {"value": "", "confidence": 0.0, "evidence": [1]},
 "pov_hint": {"value": "", "confidence": 0.0, "evidence": [1]},
 "candidate_names": [],
 "opening_notes": {"conflict_paragraph": 0, "hook_paragraph": 0}}"""


def build_profile_sample_prompt(sample: "list[tuple[int, str]]") -> str:
    """Render the sampled chapters with the same anchors L1 uses.

    Chapter and paragraph markers are identical to the extraction prompt on purpose: the
    model is being asked to cite paragraphs, and a second anchor syntax would be a second
    thing to get wrong. The renderer that omitted chapter boundaries once had the model
    inventing per-chapter signals from undifferentiated text.
    """
    parts = []
    for chapter_order, body in sample:
        lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
        rendered = "\n".join(f"[p:{index}] {line}" for index, line in enumerate(lines, start=1))
        parts.append(f"=== 第 {chapter_order} 章 ===\n{rendered}")
    return PROFILE_SAMPLE_INSTRUCTION + "\n\n正文抽样：\n\n" + "\n\n".join(parts)


# =====================================================================  L2 悬念配对
#
# The judgement a single block structurally cannot make. A thread is opened in chapter 25 and
# answered in chapter 400; the block holding chapter 400 sees eight chapters and cannot know
# whether what it just read closes a question asked four hundred chapters earlier. Carrying
# the open slate forward got the *thread* recognised across blocks — measured, 27 of 40
# threads are now revisited across block boundaries, one spanning 791 chapters — but the
# model still marked only 1 of 40 as resolved, because "is this the answer" is a whole-book
# question and it was being asked block by block.
#
# So it is asked once, at L2, over the whole book's threads and reveals at the same time.
# One call. The instruction to leave a thread unpaired rather than guess is the load-bearing
# part: an invented resolution is worse than an open thread, because an author reading
# 「已回收」 stops looking for the hole.

SUSPENSE_PAIRING_INSTRUCTION = """下面是一本长篇小说里**所有被抛出的疑问**，以及**所有揭示性的情节点**。

你的任务只有一件：判断哪些揭示**真正回答了**哪个疑问。

规则：
1. 只有当这个揭示**确实给出了那个疑问的答案**时才配对。推进、铺垫、部分透露、
   只是再次提到——**都不算回答**。
2. **宁可不配，也不要硬配。** 没有把握就不要写进结果。一个被错误标成「已回收」的疑问，
   会让作者以为这条线收好了，从而不去补它——这比留着不收更糟。
3. 一个疑问最多配一个揭示：配那个**真正给出答案**的，不是最后提到它的。
4. `answer` 用一句话写出**答案是什么**，不要复述揭示的原文。

只输出 JSON：
{"pairs": [{"thread_id": "", "reveal_id": "", "answer": ""}]}

配不上的疑问不要出现在结果里。"""


REVERSAL_INSTRUCTION = """下面是一本长篇小说里**所有揭示性的情节点**，按章节顺序排列。

你的任务只有一件：找出哪些情节点**推翻了此前已经成立的说法**。

什么算推翻：后文让前文里已经被当成事实的东西不再成立——身份是假的、死掉的人还活着、
盟友原来是对手、之前给出的解释被证明是错的。判断标准是**读到这里，前面读过的内容要重新理解一遍**。

什么不算：给出新信息（那只是揭示）、把已知的事说得更细、换个角度重述、
悬念被正常回答。**信息变多不等于认知被推翻。**

规则：
1. `overturns` 必须指向列表里**更早**的那一条 id；`id` 是推翻它的那一条。
2. **宁可不报，也不要凑数。** 一条被错标成反转的情节点，会让作者以为这里有个转折，
   从而不去补真正缺的那个——这比漏报更糟。
3. 一本书里有三五处反转是常见的，有几十处不是。**不确定就不要写。**
4. `why` 用一句话写清楚：此前成立的是什么，现在变成了什么。

只输出 JSON：
{"reversals": [{"id": "", "overturns": "", "why": ""}]}

没有找到就返回 {"reversals": []}。"""


def build_reversal_prompt(reveals: "list[dict[str, object]]") -> str:
    """Ask once, over the whole book, which beats overturned an earlier one.

    Block-level extraction cannot answer this and two measured attempts confirmed it: across
    806 chapters the ``twist`` kind was chosen once, and rewriting the field description made
    it worse — ``advance`` rose from 58% to 77% because a longer instruction pushed the model
    toward the default. The judgement is structurally out of a block's reach, since a reversal
    overturns something established hundreds of chapters earlier and the block never saw it.

    Shaped exactly like the thread pairing call, which had the same problem and the same fix:
    resolved threads went from 0 to 24 for about one cent.
    """
    import json as _json

    return (
        REVERSAL_INSTRUCTION
        + "\n\n揭示（按章节顺序）：\n"
        + _json.dumps(reveals, ensure_ascii=False, indent=None)
    )


def build_suspense_pairing_prompt(
    threads: "list[dict[str, object]]", reveals: "list[dict[str, object]]"
) -> str:
    """Render the whole book's open questions and its revealing beats, side by side."""
    import json as _json

    return (
        SUSPENSE_PAIRING_INSTRUCTION
        + "\n\n疑问：\n"
        + _json.dumps(threads, ensure_ascii=False, indent=None)
        + "\n\n揭示：\n"
        + _json.dumps(reveals, ensure_ascii=False, indent=None)
    )
