# 单章分析 × 画像层：审计与接入（CHG-20260815-092）

> 依据 `10_ADAPTIVE_PROFILE_LAYER.md §4`（2026-08-13 定稿，rev.2）。该节确立：画像是**书级前置产物**，
> 全书引擎与单章管线共同读取；单章侧重与全书 delta **共用同一套档案取值**，不得各写一套。
> 本文档是 §4 末尾要求的"单章管线自身的展开"，含现状审计与本次接入的实现记录。

## 1. 单章管线现状（1.2.0）

```
章节正文
  ↓ scene_boundary (v2)            场景切分
  ↓ scene_analysis (v3.2)          每场景 8 个结构字段（entry_state/goal/obstacle/…）
  ↓ reader_journey_scene (v2.0)    每场景 21 个阅读机制评分（0–5 level + 证据）
  ↓ reader_journey_chapter (v2.0)  章级合成：问题生命周期、主曲线
```

提示词位于 `packages/prompts/`，由 `prompt_service.load_prompt` 装载，
`content_hash = sha256(system+user+repair)` 记录进调用溯源。

## 2. 审计：不合理之处

**A1（本次修复）类型盲评。** 四段提示词没有一个字节因书而变：修仙升级文与都市情感文
用同一套 21 维、同样中性的指令打分。设计文档已把它和全书引擎"类型判断发生在最后一次
付费调用之后"判为**同一缺陷的两个实例**——分析在不知道对象是什么的前提下进行。
证据：`reader_journey_scene/v2.0/system.md` 全文无任何类型条件；管线代码在
`load_prompt` 后直接使用，没有任何按书注入点。

**A2（本次缓解，词表本身未动）scene_role 词表偏冲突叙事。**
`setup|escalation|investigation|reveal|climax|aftermath|transition|open_end|closed_end`
九选一里五个是冲突/揭示词。日常种田文的一个"做饭—邻里闲谈"场景没有诚实的选项，
最后多半被塞进 `transition`，下游又按"过渡场景 hook 理应低"的区间去解读——
类型特征被折算成了结构缺陷。词表是冻结契约的一部分，改动=新提示词版本+重标定，
本次只以 SLICE_RHYTHM 侧重块要求评分者"低 tension 是常态而非缺陷"，不动词表。

**A3（本次缓解）key_actions 规则偏身体动作。** scene_analysis v3.2 要求动作必须是
"身体动作、物件操作、空间移动"，对话/心理推进的场景 key_actions 为空。规则本身是对的
（防编造），但下游把空动作读成低 agency，对话驱动的书系统性吃亏——糙汉重生的画像
特征就是「对话驱动」。ROMANCE_ENGINE/ROMANCE_BEATS 侧重块把"关系目标的进退"
纳入 goal_progress/state_change 的解读，缓解但未根治。

**A4（记录，未修）确认门未覆盖单章入口。** 设计 §4.3 要求确认门发生在**首次分析**之前，
"否则只做单章分析的用户永远走不到它"。现状：确认门只挂在全书分析入口；单章分析对
未确认的书静默走中性提示词（本次实现选择的容错行为），但没有任何 UI 提示用户
"确认画像可以让单章分析更准"。需要产品决定：单章入口是软提示还是硬门。

**A5（记录，未修）两条管线互不喂养。** 单章管线花钱抽出的场景结构、问题生命周期，
全书 V2 引擎完全不读；反向亦然。同一本书付两次认知成本。这是架构级议题，
属于长篇引擎 L2+ 的范围，不在本次动。

## 3. 本次接入的实现

`apps/api/app/narrative_core/long_novel/chapter_focus.py` —— 与 `deltas.py` 平行的
单章侧重注册表，触发词表就是 `contracts/profile.py` 的闭集五轴（dataclass 在 import 时
校验，写错轴值直接失败构建）：

| key | 触发（AND） | 侧重 |
|---|---|---|
| fast_food_hooks | monetization=fast_food_free | 钩子位置、冲突段号、信息密度、断章质量 |
| gratification_beats | audience=male_gratification ∧ engine=progression | 爽点类型与兑现位置 |
| romance_beats | audience=female_romance | 感情节拍、糖刀强度 |
| mystery_clues | engine=mystery | 线索抛出/推进/回收、对读者是否公平 |
| romance_engine | engine=romance | 目标按关系目标理解、关系温度进退 |
| ensemble_pov | pov=ensemble | 本章视角人物、与主线关系 |
| episodic_unit | engine=episodic_transmigration | 单元内位置、跨单元主线信息 |
| slice_rhythm | engine=slice_of_life | 低冲突不折价、情绪回报来源 |

注入点四处，均在 `load_prompt` 之后包一层 `apply_chapter_focus(prompt, session, book_id)`：
`scene_pipeline`（scene_analysis）、`reader_journey_pipeline`（scene 与 chapter 两级）、
`reader_journey_v2_execution`（scene）。

**不变量（与全书 delta 同源）：**
- INV-P1 只加不减：侧重块整体附加在 system 尾部，标题写明"只增加观察点，不修改上文规则"。
- INV-P2 确认优先：草稿画像不生效；无画像/画像表不存在（旧库）→ 提示词**逐字节不变**、
  同一对象返回（缓存哈希不动）。读画像失败时回滚会话后降级，不把增强变成失败原因。
- 溯源如实：注入后按 `load_prompt` 同一公式重算 `content_hash`，记录的是真正跑过的文本。

## 4. 验证

- `apps/api/tests/test_chapter_profile_focus.py` 9 项：字节不变性（无画像/草稿）、
  附加性（原文完整前缀）、AND 触发（男频×升级）、多轴叠加顺序、非法触发拒绝、
  全注册表可触发。
- 受影响管线回归：journey e2e / persistence / boundary review / canary replay 等
  66 项全部通过（其中曾暴露一个真问题：旧测试库无 book_profiles 表时污染会话，
  已按"不可读=无画像+回滚"修复）。
- 零真实供应商调用。
