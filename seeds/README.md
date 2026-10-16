# 20 个原创功能重建种子

[返回首页](../README.md) · [JSON 目录](catalog.json)

每个种子是一个功能重建任务。输入驱动真实程序、宿主或系统服务，输出是该功能的可观察结果；公开/隐藏输入是题内检查数量。所有任务为原创小型应用，概念源自公开标准/API；真实上游应用采样数为 0。

| 种子 ID | 功能 | 必要依赖链路 | 公开/隐藏 |
|---|---|---|---:|
| apk_deeplink_history | Deep-link route history and durable navigation | Activity Intent data -> separate process Service -> Android Uri -> SharedPreferences | 4/47 |
| apk_dynamic_shortcuts | Dynamic launcher shortcut publication and durable catalog updates | Activity -> worker process -> Android ShortcutManager Binder -> OS shortcut service | 4/36 |
| apk_notification_groups | Notification channels, replacement and group cancellation | Activity -> worker process -> Android NotificationManager Binder -> OS channel/active notification store | 4/36 |
| apk_share_inbox | Shared content intake with durable MIME and content deduplication | Activity ClipData -> Service -> ContentResolver Binder -> separate ContentProvider process -> SQLite transaction | 4/36 |
| dotnet_backup_retention | 快照保留、共享内容块引用与回收计划 | 快照清单→跨程序集pin/时间策略→按主机保留→块引用计数/GC计划 | 4/48 |
| dotnet_install_plan | 可选功能与版本约束下的部署计划 | 根需求→跨程序集版本准入策略→回溯选择→依赖排序 | 4/48 |
| dotnet_print_spool | 打印队列、页面选择与双面份数排版 | 队列入口→跨程序集页选择/份数/双面策略→资源中的空白页码→输出页单 | 4/48 |
| dotnet_profiles | 配置档案继承、作用域与删除标记 | 入口→跨程序集键规范化/保留域规则→外部策略资源→多层配置解析 | 4/48 |
| native_calendar_freebusy | Calendar recurrence exceptions and free windows | native CLI -> dlopen/dlsym -> separate native dylib -> calendar file I/O | 4/48 |
| native_locale_catalog | Offline locale catalog resolution | native CLI -> dlopen/dlsym -> separate native dylib -> catalog file | 4/49 |
| native_midi_lifecycle | MIDI pedal-aware voice lifecycle | native CLI -> dlopen/dlsym -> separate native dylib -> stateful event processing | 4/47 |
| native_wav_editor | PCM WAV trim, mix and gain export | native CLI -> dlopen/dlsym -> separate native dylib -> binary file I/O | 4/45 |
| plugin_diagnostics | Diagnostic quick-fix replay | DiagnosticCollection → CodeAction provider → WorkspaceEdit → refreshed diagnostics | 4/52 |
| plugin_discovery | Workspace resource discovery | findFiles → workspace.fs → policy/hash module → selection manifest | 4/52 |
| plugin_notebook | Cell-book recovery and export | notebook provider → normalization module → NotebookEdit → serializer/file | 4/51 |
| plugin_table | Delimited table import | command → TextDocument → parser/renderer → WorkspaceEdit | 4/57 |
| wasm_atlas | 字形图集增量分配与缓存释放 | 命令工作文件→WASM缓存/shelf分配→宿主字形度量→多页坐标 | 4/48 |
| wasm_palette | 索引图瓦片提取、透明色与背景合成 | 索引图文件→WASM坐标/合成内核→宿主RGBA调色板→瓦片导出 | 4/48 |
| wasm_subtitle | 剪辑时间轴字幕切分与冲突消解 | 字幕工作文件→WASM区间映射/排序→宿主剪辑表→导出时间片 | 4/48 |
| wasm_telemetry | 串口遥测导入与损坏帧恢复 | 分块字节流→WASM持久解析状态→宿主标定表→事件记录 | 4/48 |

所有种子均保留 N/S/D 扰动和 clean/mixed 条件；这里只公布描述及覆盖统计，不包含源码、工件、隐藏输入、参考答案或测试代码。每题来源 URL、功能家族、谱系和验收计数见 JSON。

## 输入/输出的形式

| 轨道 | 输入 | 可观察输出 |
|---|---|---|
| native | MIDI 事件、语言查询、WAV 字节、日历和窗口 | 状态快照、解析文本、导出 WAV、忙闲区间 |
| apk | Intent/导航事件、快捷方式操作、通知操作、分享内容 | 持久状态、OS 服务记录、去重后的收件记录 |
| dotnet | 配置档案、版本需求、打印任务、快照清单 | 合并配置、依赖计划、页单、保留与回收计划 |
| wasm | 分块字节流、图像/调色板、字幕/剪辑表、字形命令 | 解码事件、图像瓦片、字幕片段、分配/释放结果 |
| plugin | 文档、笔记单元、工作区文件、修复操作 | 实际文档编辑、序列化文件、资源清单、诊断变化 |

每题的完整接口简报和 4 个公开示例在私有评测时提供给所有组；主分只由未向模型展示的隐藏输入计算。发布目录不等于完整任务下载集。
