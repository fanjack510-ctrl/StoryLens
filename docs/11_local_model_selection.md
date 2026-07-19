# 11｜本地开发模型选择

## 冻结结论

Qwen3.6-27B-Q3_K_S 在 8192 context、999 GPU layers 下发生过非正常关机；安全档位虽能完成最小 JSON，但复杂场景边界没有产生可提取 JSON，生成约 2.26 tokens/s。因此它退出默认自动分析路径，只保留为 `manual_only` 短任务模型。

## 14B 候选

- 官方仓库：`Qwen/Qwen3-14B-GGUF`
- 目标文件：`Qwen3-14B-Q4_K_M.gguf`
- 本机路径：`D:\AI\StoryLens\models\Qwen3-14B-Q4_K_M\Qwen3-14B-Q4_K_M.gguf`
- 文件大小：9,001,752,960 bytes
- SHA256：`500A8806E85EE9C83F3AE08420295592451379B4F8CF2D0F41C15DFFEB6B81F0`
- GGUF：qwen3，14,768,307,200 parameters，Q4_K_M，训练 context 40960
- 默认状态：`false`，通过全部 Phase 1C 门槛前不得切换
- thinking：启动层 `--reasoning off`，请求层 `chat_template_kwargs.enable_thinking=false`
- Prompt：`scene_boundary/v2`、`scene_analysis/v2`
- 结构约束：四种模式真实探测均返回纯 JSON；按优先级选择 `response_format=json_schema`

## 实测

llama.cpp b9982，最终测试档位为 context 4096、32 GPU layers、parallel 1、batch 128、ubatch 64。16 层 Stage A 健康，静态峰值约 5661 MiB、67°C。24 层最小 JSON 2.26 秒，峰值 7255 MiB、68°C。32 层最小 JSON 1.70 秒，峰值 8870 MiB、68°C。服务均可停止并释放显存，无 CUDA 或驱动错误。

32 层 `no_boundary` 返回合法 JSON，Schema 和段落 ID 均合法，但错误地在 `P0008` 后报告边界；耗时 13.76 秒，峰值 8894 MiB、74°C。该能力门槛失败后未继续 clear-location、Scene Analysis、完整 Run 或八组校准。

结论为 B：可作为本地辅助模型，但当前边界质量不足以成为默认自动分析模型。`default=false` 保持不变，暂不进入 Phase 1C。

未完成项目的 tokens/s、八组校准和质量指标保持未测，不以推断值填充。

Phase 1B.4 后，本地模型不再是进入 Phase 1C 的唯一候选；云端 Provider 的独立验收记录见 `docs/12_aliyun_qwen_provider.md`。本地14B和27B的冻结定位不变。
