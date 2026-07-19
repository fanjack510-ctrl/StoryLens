# Reader Journey（读者旅程）

在 Scene Analysis 完成后，StoryLens 生成章节级读者旅程：

- Phase 导航  
- Journey Chart（确定性 SVG，不因切换指标而重算模型）  
- Context Inspector（Scene / Phase / Question / Hook / Payoff / Risk）  
- Evidence 引用真实段落 ID  
- PNG / JSON / Markdown 导出  

V1.0 工作台以 **v4.2** 为统一阅读基线（Metric Selector 为页内面板，不得遮挡曲线）。

刷新页面或重启后，应能回到同一 Run 的旅程结果；若 Scene 已完成但旅程未生成，使用统一恢复入口，而不是新建重复任务。
