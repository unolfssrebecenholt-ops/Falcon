# Falcon 项目进度

本文件是 Windows 和 M1 Mac 双机开发的接手入口。每次提交前必须更新。

## 当前状态

- 仓库已推送到 GitHub：`ssh://git@ssh.github.com:443/unolfssrebecenholt-ops/Falcon.git`
- 当前分支：`codex/yingdao-landing`
- 当前阶段：第一版本地 MVP 已建立。
- 技术形态：Python + FastAPI + Jinja + SQLite + CSV/xlsx 导入 + 结构化影刀导入 + Markdown 日报。
- 项目必须保持 Windows 和 macOS 双端可运行。

## 已完成

- 建立 Falcon Python 包。
- 实现小红书 CSV/RPA 导入适配器。
- 实现 SQLite 数据中枢。
- 实现启发式意图评分：
  - 小红书封面为主场景。
  - 活动海报、微信头像、朋友圈背景、随便画画为探针场景。
- 实现 AI 触达任务箱：
  - 评论区回复草稿。
  - 私信草稿。
  - 轻建议草稿。
  - 人工处理状态。
- 实现 GPT-5.5 OpenAI 兼容中转站客户端。
- 实现 Markdown 日报。
- 补充 RPA CSV 字段说明。
- 实现影刀两列 xlsx 导出导入适配器：
  - A 列映射为 `title/content`。
  - B 列映射为 `url`。
  - `keyword` 由导入命令参数传入，不在流程或代码里写死。
- 实现新版影刀结构化 xlsx 导入适配器：
  - 支持 `platform,keyword,source_type,title,content,url,parent_url,author,commenter,like_count,comment_rank,collected_at` 表头。
  - 支持 `post/comment` 一行一条记录。
  - 保留旧版 A/B 两列 xlsx 兼容。
- 实现 RPA 关键词池：
  - `write-keyword-pool` 生成本地 `data/rpa_keywords.csv`。
  - 字段为 `theme,keyword,scene,weight,daily_limit`。
  - 根据程序名生成求推荐、替代工具、不好用吐槽、教程需求和场景需求关键词。
- 实现影刀日常工作流命令：
  - `run-yingdao-daily` 一次完成导入、分析和日报输出。
- 实现人工复核闭环：
  - 日报 Top 样本显示 `raw_id`。
  - `review-raw-item` 可记录 `优秀/有用/一般/无用/噪音`。
- 实现本地 Web 控制台：
  - 总览页展示样本、分析、高意图和待处理任务。
  - 采集运行页一键执行影刀 xlsx 导入、分析和日报。
  - 关键词池页生成和查看本地关键词池。
  - 复核页记录 Top 20 样本反馈。
  - 触达任务页更新任务状态。
- 补充 `docs/yingdao-runbook.md` 作为影刀日常运行手册。
- 补充示例 CSV。
- 补充双机开发规则和 start-work protocol。

## 最近一次提交准备

- 本次变更目标：把 Falcon × 影刀从标题+链接 demo 升级为支持正文、评论、热评 Top 15 契约和更可读日报的采集质量版本。
- 本次文档更新：
  - `docs/yingdao-runbook.md`：新增影刀参数化、搜索流式加载、详情页正文采集、评论 Top 15 采集和 Windows 分段调度 SOP。
  - `docs/progress.md`：记录本次采集质量升级进展和验证结果。
- 本次验证：
  - `py -3 -m unittest discover -s tests`
  - Windows 真实影刀旧版 A/B xlsx `run-yingdao-daily` smoke workflow

## 当前问题解决进度

- 已解决：项目从非 git 目录初始化为 git 仓库并推送到 GitHub。
- 已解决：HTTPS 推送缺少凭据的问题，通过 GitHub SSH over 443 推送。
- 已解决：默认模板草稿对探针场景话术不匹配的问题，已按场景区分模板。
- 待确认：真实 GPT-5.5 中转站环境变量尚未在本仓库验证，当前测试使用 fake client 和模板模式。
- 已解决：Windows 基线测试曾因 SQLite 连接未关闭导致临时库文件被占用，已让仓储连接在提交/回滚后显式关闭。
- 已验证：Windows 机器已实际运行基线测试和 smoke workflow。
- 已解决：影刀当前版本未找到本地导出流程入口，改用“批量数据抓取 + 数据表格导出”生成 xlsx。
- 已解决：Falcon 可直接导入影刀 A/B 两列 xlsx，关键词通过 `--keyword` 显式传入。
- 已解决：Falcon 可直接导入新版影刀结构化 xlsx，包含笔记正文、评论、父链接、作者、评论者、点赞数和评论排名字段。
- 已解决：Falcon 可根据程序名生成本地 RPA 关键词池，不再只靠固定场景词。
- 已解决：Falcon 可用一条命令运行影刀日常导入、分析和日报。
- 已解决：日报 Top 样本可按 `raw_id` 做人工复核记录。
- 已解决：日报新增高价值笔记正文、评论痛点与求推荐信号区块。
- 已解决：CLI 业务逻辑抽为共享 workflow，Web 和 CLI 共用导入、分析、日报逻辑。
- 已解决：本地 Web 控制台可访问总览、采集运行、关键词池、人工复核和触达任务页面。

## 方案进度

- 需求雷达：MVP 已完成。
- AI 触达任务箱：MVP 已完成，当前只生成草稿，不自动发送。
- RPA 接入：已定义 CSV 契约，并接入影刀旧版 A/B xlsx 和新版结构化 xlsx 导出格式；已用真实旧版导出文件导入 25 条样本。
- 日常运行：已具备关键词池生成、影刀每日一键分析命令、人工复核记录和运行手册。
- 采集质量：Falcon 侧已支持影刀导出正文和评论；影刀侧下一步按 runbook 改造流程参数和详情页/评论区采集节点。
- 可视化：已接入本地 Web 控制台第一版；第一版不控制影刀客户端。
- 多平台扩展：架构已预留 adapter，当前只实现小红书 CSV。
- 小程序转化归因：尚未接入，等待 `Image-sp` 上线或埋点方案确定。

## 验证记录

最近一次验证：

```powershell
py -3 -m unittest discover -s tests
```

结果：

- 30 tests passed.

最近一次 smoke workflow：

- Windows PowerShell，临时目录：`$env:TEMP\falcon-quality-smoke`。
- 初始化临时 SQLite。
- 执行 `run-yingdao-daily data\xhs_raw_export.xlsx --keyword "生图小程序"`。
- 导入真实影刀旧版 A/B 导出 25 条样本。
- 分析 25 条样本。
- 创建 9 个触达任务。
- 生成 Markdown 日报，包含“高价值笔记正文”和“评论痛点与求推荐信号”区块。

## 下一步建议

1. 在影刀界面按 `docs/yingdao-runbook.md` 把 `output_dir/output_filename/keyword/max_search_items/search_scroll_times/detail_open_limit/comment_top_limit/comment_scroll_times` 设置为流程参数。
2. 改造影刀流程：搜索页滚动去重链接，打开详情页采集标题/正文/作者，评论区采集默认热度 Top 15。
3. 导出新版结构化 xlsx 后，用 Falcon 导入验证 `post/comment` 两类数据。
4. 每天复核日报中的“高价值笔记正文”和“评论痛点与求推荐信号”，记录 `优秀/有用/一般/无用/噪音`。
5. 稳定后再配置 Windows 任务计划，形成影刀采集和 Falcon 分析的分段调度。

## Windows 接手提示

```powershell
git pull
py -3 -m unittest discover -s tests
```

如需复核完整链路，再按 `docs/development-guide.md` 运行 Windows smoke workflow。

## Mac 接手提示

```bash
git pull
python3 -m unittest discover -s tests
```

然后按 `docs/development-guide.md` 运行 macOS smoke workflow。
