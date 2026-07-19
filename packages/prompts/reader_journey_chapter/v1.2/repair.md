修复章节合成JSON。只针对具体错误码修复，不得为凑数量编造虚假阶段，不得拆分 Scene，不得复制同一 Scene 到多个 Phase。

硬合同提醒：1 <= phase_count <= min(6, scene_count)；完整覆盖、无重叠、无空缺、顺序与 Scene 一致。

按错误码处理：
- JOURNEY_PHASE_COUNT_INVALID：仅当数量超出自适应范围时调整。偏多则合并无真实结构依据的 Phase；为 0 则至少 1 个覆盖全部 Scene。数量已在范围内时不得扩展。
- JOURNEY_PHASE_SCENE_GAP：补回遗漏 Scene 归属，不得改 Scene 内容。
- JOURNEY_PHASE_SCENE_OVERLAP / JOURNEY_PHASE_DUPLICATE_SCENE：重分边界，每个 Scene 只属一个 Phase。
- JOURNEY_PHASE_ORDER_INVALID：按 Scene 顺序重排 Phase（ordinal 与 start 递增一致）。
- JOURNEY_PHASE_RANGE_NONCONTIGUOUS：修正为连续闭区间（start <= end）。

不得把短章节合法的 1—2 个 Phase 强行扩成 3 个。

错误：{error_message}
无效JSON：{invalid_json}
契约：{response_contract}
