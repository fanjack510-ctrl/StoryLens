# License selection notes（等待操作者）

**Agent 不得自动创建根目录 `LICENSE` 文件，也不得替 Community 发行版选定开源许可证。**

## 当前状态

- 仓库根目录：**无** `LICENSE`  
- 第三方依赖许可证汇总：见 `audits/v1.0/v1.0-dependency-license-report.json`  
- SBOM（直接依赖）：见 `audits/v1.0/v1.0-sbom.json`  

## 操作者需要决定

1. Community 发行版许可证（例如 MIT / Apache-2.0 / GPL 等——**由操作者明确选择**）。  
2. 与依赖许可证兼容性（Python / npm / crates）。  
3. 字体、图标、截图、示例文本是否允许再分发。  

选定后，再由操作者（或操作者明确指令）放置 `LICENSE` 并更新 README 徽章/声明。

在此之前，任何 GitHub 公开发布都应视为 **未完成法务门禁**。
