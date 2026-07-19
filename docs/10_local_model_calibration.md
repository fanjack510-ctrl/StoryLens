# 10｜本地模型校准报告

> 说明：早期探测记录保留用于审计；本页末尾 2026-07-16 的异常关机恢复与安全降载
> 结果为当前有效结论。

## 运行配置

- 模型文件：`Qwen3.6-27B-Q3_K_S.gguf`（仅检测到项目外候选文件）
- 量化等级：Q3_K_S
- llama.cpp 版本：未取得；本机未找到 `llama-server` 可执行文件
- Context size：计划 16384，可由环境变量覆盖
- GPU layers：计划 999，可由环境变量覆盖
- Prompt 版本：scene_boundary/v1、scene_analysis/v1
- 测试样本：4 个原创样本

## 人工预期

| 样本 | 人工预期 |
|---|---|
| no_boundary | 无内部边界 |
| clear_location_change | 办公室到旧仓库时切分 |
| goal_change | 目标从还书转为救人时切分 |
| prompt_injection_text | 忽略正文指令，在进入保管室时切分 |

## 实际结果

本轮探测到模型文件候选 `D:\AI\Qwen36Novel\models\Qwen3.6-27B-Q3_K_S.gguf`，但未找到 `llama-server.exe`，也没有运行中的 llama-server。因此未执行真实 `/chat/completions`，以下指标暂记为未测：

- 首次 JSON 成功率：未测
- 修复后成功率：未测
- 平均调用次数：未测
- 非法证据次数：未测
- 场景边界准确情况：未测
- 平均耗时：未测
- 显存与资源占用：未测

## 结论

当前不能基于真实结果判断是否继续使用 Q3_K_S，也不能判断 Q4_K_M 的收益。建议安装匹配版本的 llama.cpp，完成本报告四个原创样本的三级冒烟后，再决定是否继续使用 Q3_K_S，并以同一 Prompt 和样本对比 Q4_K_M。本阶段不训练 LoRA。

## 异常关机事件与安全降载验证（2026-07-16）

原始运行参数为 context 8192、GPU layers 999、parallel 1。真实 CUDA 推理期间观测到
约 15.2 GB 显存和约 96% GPU 利用率，随后在冒烟尚未完成时发生整机异常关机；该次运行
判定为失败，不能作为压力测试通过。Windows Kernel-Power 41、EventLog 6008 与启动状态
只能证明关机异常，未发现足以把根因确定为温度、驱动或供电的直接事件证据。

恢复后确认生产 SQLite `PRAGMA integrity_check` 为 `ok`，无遗留 queued/running Run，端口
和 StoryLens 进程均已清理。失败证据保存在被打包规则排除的
`data/runtime/local_llama/incidents/incident-20260716-110947/`。

安全档位固定为 context 4096、GPU layers 16、parallel 1、batch 128、ubatch 64；停止阈值
为 80°C、14336 MiB、单请求 300 秒以及连续三次无法读取 nvidia-smi。Stage A 使用官方
llama.cpp b9982（commit 99f3dc322）成功加载 27B Q3_K_S，`/v1/models` 健康，部分 GPU
offload 成立；空闲观测约 88 秒，末次观测 68°C、4876 MiB，无 CUDA 分配失败，随后按
记录 PID 正常停止，显存回落至约 1.1 GiB。

| 阶段 | GPU layers | 峰值显存 | 峰值温度 | 耗时 | 完成 | 安全停止 | 驱动错误 |
|---|---:|---:|---:|---:|---|---|---|
| A 静态健康 | 16 | 4876 MiB | 69°C | 约 88 秒 | 是 | 否 | 未发现 |
| B 最小 JSON | 16 | 5070 MiB | 70°C | 18.5 秒 | 是 | 否 | 未发现 |
| C 单 fixture | 16 | 5183 MiB | 74°C | 约 80 秒 | 否：无可提取 JSON | 否 | 未发现 |

Stage C 的 `no_boundary` 初始请求未产生可提取 JSON，Pydantic 前置的 JSON 提取按设计拒绝
结果。该请求未越过温度或显存阈值，但未达到准确性门槛；按分级门禁不重试、不执行 D/E。
当前适配结论为 B：仅适合短任务或手工单次测试，暂不进入 Phase 1C。

后续 Phase 1B.3 不再提高 27B 负载。该模型已退出自动分析候选并固定为 manual-only；
14B Q4_K_M 的真实结果独立记录于 `docs/11_local_model_selection.md`。
