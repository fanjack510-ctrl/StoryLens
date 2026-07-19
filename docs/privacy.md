# 隐私

## 本地优先

- 书稿与分析结果默认在本机 SQLite。  
- 只有在你开启云端并给出 `cloud_consent` 后，所选章节正文才会发送到阿里云百炼。  

## API Key

- 保存在操作系统凭据库。  
- 不进入 Git、导出文件、审计 JSON、截图约定与示例配置中的真实值。  

## 日志

默认 `STORYLENS_CLOUD_RAW_LOGGING=false`：Invocation 审计保存段落 ID、哈希、Token 等，不保存完整云端正文。

开源仓库不得包含：真实 Key、用户书稿、Human UAT / Canary 数据库、凭据备份。
