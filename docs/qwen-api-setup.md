# Qwen API 配置（BYOK）

V1.0 普通模式只正式支持 **阿里云百炼 · Qwen**。

| 项 | 值 |
|----|----|
| 界面名称 | 阿里云百炼 · Qwen |
| Provider | `aliyun_qwen_plus`（仅技术详情可见） |
| 默认模型 | `qwen3.7-plus` |
| 地域 | 北京（cn-beijing） |
| auto_route | false |
| Flash fallback | false |

## 普通向导只填

1. API Key  
2. 模型档位：Qwen Plus（默认推荐）  
3. 每日费用上限  
4. 云端正文发送确认  

不要填写 Provider ID、Base URL、Workspace、路由等工程字段（开发者模式才可见）。

## 入口

- 首次启动欢迎条  
- 设置 → AI 服务  
- 开始分析弹窗（未配置时）  
- 分析恢复中心（凭据缺失时）  
- 空书库引导  

## 安全

- Key 保存在 **操作系统凭据管理器**  
- 界面只显示「已配置 / 未配置」  
- 不会写入浏览器 LocalStorage 明文、SQLite 明文、日志或导出文件  
- **测试连接必须由你点击**；页面加载不会自动产生费用  

开发环境也可把 Key 放在本机 `.env` 的 `STORYLENS_ALIYUN_API_KEY`（该文件已 gitignore，勿提交）。
