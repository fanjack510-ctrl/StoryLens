# 分析恢复

当任务可恢复地暂停时，主界面显示 **分析已暂停**，并通过统一 **Analysis Recovery Plan** 聚合阻塞原因，而不是修完一个又冒出另一个。

典型原因包括：

- Provider 未连接 / 凭据缺失  
- 请求、Token 或费用额度不足  
- 等待边界审阅 / 等待 Reader Journey  
- Scene 部分完成 / Journey 失败  

主按钮：**修复并继续**。系统应复用已完成 Artifact，保持幂等，避免重复创建 AnalysisRun 或 ReaderJourneyRun。

章节页是主要恢复入口；任务中心提供全局摘要。技术错误码只出现在「查看详情」中。
