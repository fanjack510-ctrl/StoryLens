# StoryLens UI 审计界面清单（0.1.0）

> 基于路由、组件引用与对话框调用关系盘点（非仅侧边栏）。
> 截图文件输出目录：`artifacts/ui-audit-work/screenshots/`
> 压缩包：`artifacts/StoryLens_UI_Audit_0.1.0.zip`

图例：**是否截图** = `是` / `否（未实现）` / `否（覆盖受限）` / `部分`

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 00-01 | DesktopBootstrap 启动中 | （预路由） | starting | 是 | `00_global_bootstrap_starting.png` |
| 00-02 | DesktopBootstrap 启动失败 | （预路由） | failed | 是 | `00_global_bootstrap_failed.png` |
| 00-03 | AppShell 浅色 | `/library` | light | 是 | `00_shell_light.png` |
| 00-04 | AppShell 深色 | `/library` | dark | 是 | `00_shell_dark.png` |
| 00-05 | 开发者模式关闭 | `/library` | developerMode=0 | 是 | `00_devmode_off.png` |
| 00-06 | 开发者模式开启 | `/library` | developerMode=1 | 是 | `00_devmode_on.png` |
| R-01 | HomePage | `/` | 重定向书库 | 是 | `r_home_redirect.png` |
| R-02 | LibraryPage | `/library` | 默认 | 是 | `02_library_default.png` |
| R-03 | WorkspaceLandingPage | `/workspace` | 开发导航 | 是 | `r_workspace.png` |
| R-04 | BookRoutePage | `/books/:bookId` | 三栏工作台 | 是 | `04_workspace_default.png` |
| R-05 | TasksPage | `/tasks` | 任务列表 | 是 | `07_tasks_list.png` |
| R-06 | AnalysisResultsShellPage | `/analysis-runs/:runId/results` | 结果壳 | 是 | `05_analysis_results.png` |
| R-07 | CasesPage | `/cases` | 案例库 | 是 | `r_cases.png` |
| R-08 | ProvidersPage | `/providers` | 模型中心 | 是 | `08_providers_default.png` |
| R-09 | SettingsPage | `/settings` | AI Tab | 是 | `09_settings_ai_default.png` |

## 01 首次启动与引导

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 01-01 | FirstLaunchWizard | `/library` | 欢迎页 step1 | 是 | `01_onboarding_welcome.png` |
| 01-02 | FirstLaunchWizard | `/library` | AI 配置 step2 | 是 | `01_onboarding_ai_blank.png` |
| 01-03 | FirstLaunchWizard | `/library` | API Key 已输入（password 遮罩） | 是 | `01_onboarding_ai_key_masked.png` |
| 01-04 | FirstLaunchWizard | `/library` | 测试连接中 | 是 | `01_onboarding_test_pending.png` |
| 01-05 | FirstLaunchWizard | `/library` | 测试连接成功 | 是 | `01_onboarding_test_ok.png` |
| 01-06 | FirstLaunchWizard | `/library` | 测试连接失败 | 是 | `01_onboarding_test_fail.png` |
| 01-07 | FirstLaunchWizard | `/library` | 未勾选正文发送 | 是 | `01_onboarding_consent_off.png` |
| 01-08 | FirstLaunchWizard | `/library` | 已勾选正文发送 | 是 | `01_onboarding_consent_on.png` |
| 01-09 | FirstLaunchWizard | `/library` | 完成页 step3 | 是 | `01_onboarding_done.png` |
| 01-10 | FirstLaunchWizard | `/library` | 跳过（无独立确认弹窗） | 部分 | `01_onboarding_skipped_library.png` |
| 01-11 | Settings AI | `/settings?tab=ai` | 已有配置再进入 | 是 | `01_onboarding_reenter_configured.png` |
| 01-12 | Settings AI / 状态卡 | `/settings?tab=ai` | 旧配置需修复 | 是 | `01_onboarding_needs_repair.png` |
| 01-13 | QwenFirstLaunchBanner | `/library` | 空书库引导横幅 | 是 | `01_qwen_banner.png` |

## 02 首页与书库

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 02-01 | LibraryPage | `/library` | 空书库 | 是 | `02_library_empty.png` |
| 02-02 | LibraryPage | `/library` | 1 本书 | 是 | `02_library_one_book.png` |
| 02-03 | LibraryPage | `/library` | 多本书 | 是 | `02_library_multi.png` |
| 02-04 | LibraryPage | `/library` | 网格视图 | 否（未实现） | — |
| 02-05 | LibraryPage | `/library` | 列表视图（当前唯一布局） | 是 | `02_library_list.png` |
| 02-06 | LibraryPage | `/library` | 搜索有结果 | 是 | `02_library_search_hit.png` |
| 02-07 | LibraryPage | `/library` | 搜索无结果 | 是 | `02_library_search_miss.png` |
| 02-08 | LibraryPage | `/library` | 排序下拉展开 | 是 | `02_library_sort_open.png` |
| 02-09 | 书籍卡片悬停 | `/library` | hover | 是 | `02_library_book_hover.png` |
| 02-10 | 书籍操作菜单 | — | 独立菜单 | 否（未实现） | — |
| 02-11 | 删除确认弹窗 | — | — | 否（未实现） | — |
| 02-12 | 导入入口 | `/library` | 导入按钮可见 | 是 | `02_library_import_entry.png` |

## 03 导入流程

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 03-01 | 导入预览 | `/library` | TXT 识别成功 | 是 | `03_import_txt_ok.png` |
| 03-02 | 导入预览 | `/library` | DOCX（同预览面板） | 是 | `03_import_docx_ok.png` |
| 03-03 | 导入预览 | `/library` | EPUB（同预览面板） | 是 | `03_import_epub_ok.png` |
| 03-04 | 拖拽提示 | `/library` | drop-hint | 是 | `03_import_drop_hint.png` |
| 03-05 | 解析中 | `/library` | preview pending | 是 | `03_import_parsing.png` |
| 03-06 | 章节识别成功 | `/library` | preview data | 是 | `03_import_chapters_ok.png` |
| 03-07 | 无法识别章节 | `/library` | CHAPTER_DETECTION_SUSPECT | 是 | `03_import_chapters_suspect.png` |
| 03-08 | 格式错误 | `/library` | preview error | 是 | `03_import_format_error.png` |
| 03-09 | 文件过大 | `/library` | preview error | 是 | `03_import_too_large.png` |
| 03-10 | 编码错误 | `/library` | preview error | 是 | `03_import_encoding_error.png` |
| 03-11 | 重复书籍 | `/library` | upload error | 是 | `03_import_duplicate.png` |
| 03-12 | ReparseDialog | `/books/:id` | 章节重新解析 | 是 | `03_reparse_dialog.png` |
| 03-13 | ReparseDialog | `/books/:id` | replace_in_place | 是 | `03_reparse_replace.png` |
| 03-14 | ReparseDialog | `/books/:id` | create_revision | 是 | `03_reparse_revision.png` |
| 03-15 | 导入完成 | `/library` | 书库出现新书 | 是 | `03_import_done.png` |

## 04 书籍工作台

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 04-01 | BookRoutePage | `/books/1` | 默认三栏 | 是 | `04_workspace_default.png` |
| 04-02 | 章节目录抽屉 | `/books/1` | 展开 | 是 | `04_catalog_open.png` |
| 04-03 | 章节目录 | `/books/1` | 折叠/关闭 | 是 | `04_catalog_closed.png` |
| 04-04 | 中央正文 | `/books/1` | reading | 是 | `04_reading_body.png` |
| 04-05 | 右侧分析区 | `/books/1` | 工具栏/开始分析 | 是 | `04_analysis_rail.png` |
| 04-06 | 未选章节 | `/books/1` | 无 chapter 参数 | 是 | `04_no_chapter.png` |
| 04-07 | 章节加载中 | `/books/1` | paragraphs loading | 是 | `04_chapter_loading.png` |
| 04-08 | 长章节滚动 | `/books/1` | fullPage | 是 | `04_long_chapter.png` |
| 04-09 | 短章节 | `/books/1` | 少段落 | 是 | `04_short_chapter.png` |
| 04-10 | 无正文 | `/books/1` | 空段落 | 是 | `04_empty_body.png` |
| 04-11 | 章节/书籍更多菜单 | `/books/1` | OverflowMenu | 是 | `04_more_menu.png` |
| 04-12 | 窄宽度 | `/books/1` | 1024×768 | 是 | `04_narrow_1024.png` |
| 04-13 | 阅读设置 Popover | `/books/1` | 展开 | 是 | `04_reading_settings.png` |
| 04-14 | 右侧面板关闭 | Journey 布局 | inspector collapsed | 是 | `04_inspector_collapsed.png` |

## 05 场景边界与分析

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 05-01 | 未分析 | `/books/1` | 无 run | 是 | `05_unanalyzed.png` |
| 05-02 | StartAnalysisDialog | `/books/1` | 打开 | 是 | `05_start_dialog.png` |
| 05-03 | StartAnalysisDialog | `/books/1` | 唯一 Provider | 是 | `05_provider_single.png` |
| 05-04 | StartAnalysisDialog | `/books/1` | 多 Provider（开发者模式） | 是 | `05_provider_multi.png` |
| 05-05 | StartAnalysisDialog | `/books/1` | 无可用 Provider | 是 | `05_provider_none.png` |
| 05-06 | StartAnalysisDialog | `/books/1` | 云端未开启 | 是 | `05_cloud_off.png` |
| 05-07 | StartAnalysisDialog | `/books/1` | API Key 未配置 | 是 | `05_key_missing.png` |
| 05-08 | StartAnalysisDialog | `/books/1` | Provider 停用 | 是 | `05_provider_disabled.png` |
| 05-09 | StartAnalysisDialog | `/books/1` | 凭据无效 | 是 | `05_credential_invalid.png` |
| 05-10 | StartAnalysisDialog | `/books/1` | 去配置 AI | 是 | `05_goto_ai_settings.png` |
| 05-11 | 分析模式 | `/books/1` / Settings | FAST | 是 | `05_mode_fast.png` |
| 05-12 | 分析模式 | | BALANCED | 是 | `05_mode_balanced.png` |
| 05-13 | 分析模式 | | QUALITY | 是 | `05_mode_quality.png` |
| 05-14 | 分析模式 | | CUSTOM（高级） | 是 | `05_mode_custom.png` |
| 05-15 | StartAnalysisDialog | | 确认/预算预览 | 是 | `05_confirm_budget.png` |
| 05-16 | 进度视图 | `?view=progress` | 正在分析 | 是 | `05_analyzing.png` |
| 05-17 | 进度视图 | `?view=progress` | 进度条 | 是 | `05_progress.png` |
| 05-18 | 失败卡 | `/books/1` | 分析失败 | 是 | `05_failed.png` |
| 05-19 | 失败卡 | `/books/1` | 重试 | 是 | `05_retry.png` |
| 05-20 | 结果 | `?view=result` | 完成 | 是 | `05_done.png` |
| 05-21 | BoundaryReviewPanel | `/books/1` | 边界列表 | 是 | `05_boundary_list.png` |
| 05-22 | BoundaryReviewPanel | `/books/1` | 人工确认 | 是 | `05_boundary_confirm.png` |
| 05-23 | BoundaryReviewPanel | `/books/1` | 编辑/合并/拆分（若存在控件） | 部分 | `05_boundary_edit.png` |
| 05-24 | 保存审核 | `/books/1` | 审阅保存 | 是 | `05_boundary_save.png` |
| 05-25 | Scene Analysis 结果 | `/analysis-runs/55/results` | structure | 是 | `05_scene_analysis_result.png` |

## 06 Reader Journey

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 06-01 | Journey 未生成 | `tab=reader-journey` | empty CTA | 是 | `06_rj_not_generated.png` |
| 06-02 | Journey 生成中 | | progress card | 是 | `06_rj_generating.png` |
| 06-03 | Journey 成功 | | workspace | 是 | `06_rj_success.png` |
| 06-04 | Journey 空结果 | | empty detail | 是 | `06_rj_empty_detail.png` |
| 06-05 | Journey 失败 | | error | 是 | `06_rj_failed.png` |
| 06-06 | CanonicalJourneyChart | | 曲线 | 是 | `06_rj_chart.png` |
| 06-07 | 节点悬停 | | hover | 是 | `06_rj_node_hover.png` |
| 06-08 | Tooltip / 信息 | | info popover | 是 | `06_rj_tooltip.png` |
| 06-09 | 情绪曲线 | | valence metric | 是 | `06_rj_emotion.png` |
| 06-10 | 钩子 | | hook metric | 是 | `06_rj_hooks.png` |
| 06-11 | 节奏 | | engagement | 是 | `06_rj_pace.png` |
| 06-12 | 长页完整截图 | | fullPage | 是 | `06_rj_fullpage.png` |
| 06-13 | 单场景详情 | | inspector | 是 | `06_rj_scene_one.png` |
| 06-14 | 多场景 | | phase | 是 | `06_rj_multi_scene.png` |
| 06-15 | 无详情 | | empty inspector | 是 | `06_rj_no_detail.png` |
| 06-16 | 导出入口 | | PNG/JSON | 是 | `06_rj_export.png` |
| 06-17 | SceneStructureDrawer | | 打开 | 是 | `06_rj_structure_drawer.png` |

## 07 任务中心

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 07-01 | TasksPage | `/tasks` | 空列表 | 是 | `07_tasks_empty.png` |
| 07-02 | TasksPage | `/tasks` | 单任务运行中 | 是 | `07_tasks_one_running.png` |
| 07-03 | TasksPage | `/tasks` | 多状态任务 | 是 | `07_tasks_multi.png` |
| 07-04 | 等待中 | | queued | 是 | `07_status_queued.png` |
| 07-05 | 运行中 | | running | 是 | `07_status_running.png` |
| 07-06 | 已完成 | | succeeded | 是 | `07_status_done.png` |
| 07-07 | 已失败 | | failed | 是 | `07_status_failed.png` |
| 07-08 | 已取消 | | cancelled（若 API 支持） | 部分 | `07_status_cancelled.png` |
| 07-09 | 重试按钮 | | failed row | 是 | `07_retry_button.png` |
| 07-10 | 任务详情弹窗 | | detail modal | 是 | `07_task_detail.png` |
| 07-11 | 错误详情 | | detail 内错误 | 是 | `07_task_error_detail.png` |
| 07-12 | 筛选菜单 | — | — | 否（未实现） | — |
| 07-13 | 批量操作 | — | — | 否（未实现） | — |
| 07-14 | 长列表 | `/tasks` | 多条 | 是 | `07_tasks_long.png` |

## 08 模型与 Provider

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 08-01 | ProvidersPage | `/providers` | 默认 | 是 | `08_providers_default.png` |
| 08-02 | 阿里云已配置 | `/providers` | configured | 是 | `08_aliyun_configured.png` |
| 08-03 | 未配置 | `/providers` | missing | 是 | `08_aliyun_unconfigured.png` |
| 08-04 | 已启用 | `/providers` | enabled | 是 | `08_aliyun_enabled.png` |
| 08-05 | 已停用 | `/providers` | disabled | 是 | `08_aliyun_disabled.png` |
| 08-06 | 凭据正常 | `/providers` | credential ok | 是 | `08_cred_ok.png` |
| 08-07 | 凭据 unknown | `/providers` | unknown | 是 | `08_cred_unknown.png` |
| 08-08 | 连接成功 | `/providers` | transport/real test ok | 是 | `08_conn_ok.png` |
| 08-09 | 连接失败 | `/providers` | test fail | 是 | `08_conn_fail.png` |
| 08-10 | Provider 编辑 | `/providers` | AliyunForm | 是 | `08_provider_edit.png` |
| 08-11 | 模型映射 | `/providers` | 模型字段 | 是 | `08_model_map.png` |
| 08-12 | 高级参数 | Settings advanced | | 是 | `08_advanced_params.png` |
| 08-13 | 自动路由 | `/providers` | routing preview | 是 | `08_auto_route.png` |
| 08-14 | 云端总开关 | Settings/Providers | cloud master | 是 | `08_cloud_switch.png` |
| 08-15 | 删除确认 | — | 独立删除确认 | 否（未实现） | — |
| 08-16 | 连接测试确认弹窗 | `/providers` | awaiting_confirmation | 是 | `08_conn_confirm.png` |

## 09 设置

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 09-ai-01 | AI 服务 | `/settings?tab=ai` | 默认未配置 | 是 | `09_ai_default.png` |
| 09-ai-02 | AI 服务 | | 已配置 | 是 | `09_ai_configured.png` |
| 09-ai-03 | AI 服务 | | 错误 | 是 | `09_ai_error.png` |
| 09-ai-04 | AI 服务 | | 保存中 | 是 | `09_ai_saving.png` |
| 09-ai-05 | AI 服务 | | 保存成功 | 是 | `09_ai_saved.png` |
| 09-cost-01 | 使用费用 | `/settings?tab=cost` | 默认 | 是 | `09_cost_default.png` |
| 09-cost-02 | 使用费用 | | 已配置限额 | 是 | `09_cost_configured.png` |
| 09-cost-03 | 使用费用 | | 保存 | 是 | `09_cost_saved.png` |
| 09-data-01 | 数据与存储 | `/settings?tab=data` | 默认 | 是 | `09_data_default.png` |
| 09-data-02 | 数据与存储 | | 禁用按钮 | 是 | `09_data_disabled_actions.png` |
| 09-privacy-01 | 隐私与更新 | `/settings?tab=privacy` | 默认 | 是 | `09_privacy_default.png` |
| 09-privacy-02 | 更新可用弹窗 | | UpdateAvailableDialog | 是 | `09_update_dialog.png` |
| 09-license-01 | 授权与会员 | `/settings?tab=license` | FREE | 是 | `09_vip_free.png` |
| 09-license-02 | | | VIP Active | 是 | `09_vip_active.png` |
| 09-license-03 | | | VIP Expired | 是 | `09_vip_expired.png` |
| 09-license-04 | | | Offline Grace | 是 | `09_vip_offline_grace.png` |
| 09-license-05 | | | Invalid | 是 | `09_vip_invalid.png` |
| 09-license-06 | | | 激活码输入 | 是 | `09_vip_code_input.png` |
| 09-license-07 | | | 激活成功 | 是 | `09_vip_activate_ok.png` |
| 09-license-08 | | | 激活失败 | 是 | `09_vip_activate_fail.png` |
| 09-appearance-01 | 外观 | `/settings?tab=appearance` | 默认 | 是 | `09_appearance_default.png` |
| 09-advanced-01 | 高级设置 | `/settings?tab=advanced` | 开启后 | 是 | `09_advanced_default.png` |
| 09-tel-01 | 匿名统计 | privacy | UNKNOWN | 是 | `09_telemetry_unknown.png` |
| 09-tel-02 | 匿名统计 | privacy | ENABLED | 是 | `09_telemetry_enabled.png` |
| 09-tel-03 | 匿名统计 | privacy | DISABLED | 是 | `09_telemetry_disabled.png` |

## 10 全局状态

| 编号 | 页面/组件 | 路由 | 状态 | 是否截图 | 文件名 |
|---|---|---|---|---|---|
| 10-01 | 全局加载 | States.Loading | | 是 | `10_loading.png` |
| 10-02 | API/Sidecar 失败 | bootstrap failed | | 是 | `10_api_failed.png` |
| 10-03 | 404 路由 | `/no-such-page` | Router 兜底 | 部分 | `10_not_found.png` |
| 10-04 | API 500 | 页面 ErrorState | | 是 | `10_api_500.png` |
| 10-05 | 网络超时 | ErrorState | | 是 | `10_timeout.png` |
| 10-06 | Toast 成功/警告/错误 | — | 产品无 Toast 组件 | 否（未实现） | — |
| 10-07 | Confirm Dialog | window.confirm / 业务确认 | 部分 | `10_confirm_dialog.png` |
| 10-08 | 表单验证 | onboarding/settings | | 是 | `10_form_validation.png` |
| 10-09 | 禁用按钮 | data tab | | 是 | `10_disabled_button.png` |
| 10-10 | Tooltip | title 属性 | | 是 | `10_tooltip.png` |
| 10-11 | Dropdown | library sort | | 是 | `10_dropdown.png` |
| 10-12 | Popover | reading settings | | 是 | `10_popover.png` |
| 10-13 | 空表格/空列表 | tasks empty | | 是 | `10_empty_table.png` |
| 10-14 | 长文本溢出 | 超长书名 | | 是 | `10_long_book_title.png` |
| 10-15 | 超长章节名 | workspace | | 是 | `10_long_chapter_title.png` |

## 组件来源索引

| 类别 | 主要文件 |
|---|---|
| 路由 | `apps/desktop/src/app/router.tsx` |
| Shell / 导航 | `components/layout/AppShell.tsx`, `DevelopmentNavigationGroup.tsx` |
| 向导 | `components/onboarding/FirstLaunchWizard.tsx` |
| 书库/导入 | `pages/LibraryPage.tsx` |
| 工作台 | `pages/BookRoutePage.tsx`, `BookWorkspacePage.tsx` |
| 分析弹窗 | `components/analysis/StartAnalysisDialog.tsx` |
| 边界审阅 | `components/analysis/BoundaryReviewPanel.tsx` |
| 重解析 | `components/books/ReparseDialog.tsx` |
| 任务 | `pages/TasksPage.tsx` |
| 模型 | `pages/ProvidersPage.tsx`, `components/providers/AliyunForm.tsx` |
| 设置 Tabs | `pages/SettingsPage.tsx` + `components/settings/*` |
| Journey | `components/readerJourney/*` |
| VIP | `components/settings/LicenseSettingsCard.tsx` |
| 遥测 | `components/settings/TelemetrySettingsCard.tsx` |

## 审计约束

1. 所有截图使用确定性 Mock API，不连接真实阿里云。
2. API Key 仅出现在 `type=password` 输入框视觉遮罩中；打包前扫描明文密钥模式。
3. 导入样本为自动生成的虚构文本（`e2e/ui-audit/fixtures/fiction_*`）。
4. 产品未实现的界面在覆盖报告中记为 `not_implemented`，不伪造产品截图冒充已有功能。
