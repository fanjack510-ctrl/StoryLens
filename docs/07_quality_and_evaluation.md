# 07｜质量控制与评测

## 1. 第一原则

分析结果必须可回到原文；没有证据的文学判断只能标记为“推测”。

## 2. 评测集

初期选择 3 本不同类型小说，每本人工精拆 10—20 章，覆盖：

- 开篇；
- 普通过渡章；
- 高冲突章；
- 反转章；
- 高人物塑造章。

## 3. 指标

### 场景切分

- Boundary Precision
- Boundary Recall
- 过碎率
- 过粗率

### 证据

- 段落 ID 有效率
- 最小证据范围准确率
- 越界引用率

### 钩子

- 候选识别准确率
- 普通悬念误报率
- 章尾钩子漏报率

### 人物与场景描写

- 类型分类准确率
- 性格结论有证据率
- 过度解读率

## 4. 版本追踪

每次结果保存：

- provider
- model
- prompt_version
- schema_version
- input_hash
- temperature
- raw_output
- validated_output
- user_correction
