# Falcon 项目进度

本文件是 Windows 和 M1 Mac 双机开发的接手入口。每次提交前必须更新。

## 当前状态

- 仓库已推送到 GitHub：`ssh://git@ssh.github.com:443/unolfssrebecenholt-ops/Falcon.git`
- 当前分支：`main`
- 当前阶段：第一版本地 MVP 已建立，影刀 RPA 资料交接、组件手册、Falcon 侧采集质量升级和 dashboard 方案原型已合并准备交接。
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
- 补充影刀 RPA 交接资料：
  - `ShadowBladeElement/` 保存用户提供的影刀指令分组截图和关键二/三层截图。
  - `docs/rpa-elements/` 保存影刀指令目录、当前主流程、元素命名约定和工作流草稿。
  - `docs/rpa-elements/yingdao-hybrid-architecture-guide.md` 保存影刀“可视化 + Python”混合架构、SPA 弹窗、JS 点击、容错、动态选择器和反风控路径等避坑知识。
  - `docs/rpa-elements/yingdao-component-handbook.md` 按组件对象记录影刀组件用途、输入输出、操作手册、已知坑和验证方式。
  - `docs/rpa-elements/yingdao-assistant-rules.md` 固化后续 Codex 辅助影刀时的 DOM 取证要求、伪工作流回答格式和排查顺序。
  - `prototype/xiaohongshu-rpa-sop.html` 保存可直接打开的影刀采集 SOP 教学原型。
- 补充 `prototype/falcon-dashboard.html` 作为 Falcon 进度和方案 dashboard 高保真原型：
  - 用于讨论后续正式 Web 控制台的信息架构、交接视图和方案进度展示。
  - 当前是静态 HTML 原型，不接真实数据库，不替代已实现的 FastAPI Web 控制台。
- 补充示例 CSV。
- 补充双机开发规则和 start-work protocol。

## 最近一次提交准备

- 本次变更目标：完成 2026-05-14 Mac 端拉代码、合并远端进度、验证项目状态，并把 Falcon dashboard 方案原型和交接进度推送到 GitHub，方便晚些时候 Windows 继续开发。
- 本次整理内容：
  - 已执行 `git pull`，本地 `main` 从 `edb325f` 快进到远端 `c0780dc`，无冲突。
  - 远端已带入 `docs/rpa-elements/yingdao-component-handbook.md`、`docs/rpa-elements/yingdao-assistant-rules.md` 和最新 `AGENTS.md` 影刀规则。
  - 新增 `prototype/falcon-dashboard.html`，保存 Falcon 方案进度和交接状态 dashboard 静态原型。
  - 更新 `docs/progress.md`，记录 Mac 端拉取、合并、依赖验证、测试结果和 Windows 接手提示。
- 本次验证：
  - `python3 -m unittest discover -s tests`

## 当前问题解决进度

- 已解决：项目从非 git 目录初始化为 git 仓库并推送到 GitHub。
- 已解决：HTTPS 推送缺少凭据的问题，通过 GitHub SSH over 443 推送。
- 已解决：默认模板草稿对探针场景话术不匹配的问题，已按场景区分模板。
- 已解决：Falcon CSV 表头和字段契约已确认，实际适配器支持英文/中文表头，推荐英文表头 `platform,keyword,source_type,title,content,url,published_at`。
- 已解决：影刀指令目录已按截图归档，当前可使用真实截图中确认的 `新建列表`、`列表插入一项`、`ForEach列表循环`、`获取相似元素列表(web)`、`获取元素信息(web)`、`获取关联元素(web)`、`数据写入CSV` 等指令。
- 已解决：当前影刀主流程已记录到 `docs/rpa-elements/current-yingdao-mainflow.md`，包括关键词列表、搜索循环、打开小红书、搜索框输入、点击搜索按钮和低频滚动加载。
- 已解决：CSV 创建错误排查：
  - Windows 文件名中不能包含 `:`，不要直接使用 `2026-05-12 16:37:24.102578` 作为文件名。
  - 影刀“创建 CSV”文件名不要手写 `.csv`，否则可能生成 `.csv.csv`。
  - 动态文件名建议先单独生成安全变量，例如 `xiaohongshu_falcon_20260512_163724`。
- 已解决：跳转详情页 URL 错误排查：
  - 小红书搜索结果链接可能是相对路径，例如 `/search_result/...`。
  - 跳转前要拼成完整 URL：`https://www.xiaohongshu.com` + `href_raw`。
- 已解决：页面跳转后旧元素对象失效排查：
  - `link_item` 是搜索结果页元素对象，跳转/刷新后不能再访问。
  - 跳转前必须先把 `href` 保存成普通文本变量 `post_url`，写 CSV 时也用 `post_url`。
- 已解决：列表下标越界排查：
  - 列表长度为 `list_len` 时，最大合法下标是 `list_len - 1`。
  - `For次数循环` 如果从 `0` 开始，结束值必须是 `list_len - 1`，不能直接到 `list_len`。
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
- 已解决：影刀混合架构避坑知识已归档，后续回答影刀搭建问题时以“可视化交互 + Python 数据处理”为默认高价值方案。
- 已归档：2026-05-14 影刀调试经验已按组件对象分类沉淀，包括多关键词状态重置、瀑布流 DOM 快照、`current_card.get_attribute("href")` 取链接、`should_click_card` 整数旗标、禁用节点保留行号、一行一写 CSV、点击误入图片放大层、小红书禁用 JS 点击、运行时不要移动鼠标或切换窗口等规则。
- 已归档：项目规则已新增“任何影刀相关回答、设计、排查或修改前必须先读完本项目影刀资料”的要求，并同步到 `docs/rpa-elements/yingdao-assistant-rules.md`。
- 已完成：2026-05-14 Mac 端已拉取并合并远端 `main` 最新影刀组件手册和辅助规则，无冲突。
- 已完成：`prototype/falcon-dashboard.html` 已作为方案进度和交接 dashboard 静态原型纳入仓库，供后续正式 Web 控制台改造参考。
- 已确认：Mac 系统自带 `pip 21.2.4` 对当前 `pyproject.toml` editable 安装支持不足，`python3 -m pip install -e .` 会失败；本机已改用直接安装依赖 `fastapi httpx jinja2 python-multipart uvicorn` 后完成测试。Windows 仍按 `py -3 -m pip install -e .`。
- 待确认：真实 GPT-5.5 中转站环境变量尚未在本仓库验证，当前测试使用 fake client 和模板模式。
- 待继续：小红书真实网页元素仍需继续归档，尤其是详情页 `detail_title`、`detail_content`、评论文本元素，以及最终 CSV/xlsx 写入动作的成功验证。

## 方案进度

- 需求雷达：MVP 已完成。
- AI 触达任务箱：MVP 已完成，当前只生成草稿，不自动发送。
- RPA 接入：CSV 契约已定义；已接入影刀旧版 A/B xlsx 和新版结构化 xlsx 导出格式；影刀指令目录、教学 SOP、当前主流程、关键排错和混合架构指南已归档；已用真实旧版导出文件导入 25 条样本。
- 日常运行：已具备关键词池生成、影刀每日一键分析命令、人工复核记录和运行手册。
- 采集质量：Falcon 侧已支持影刀导出正文和评论；影刀侧下一步按 runbook 改造流程参数和详情页/评论区采集节点。
- 可视化：已接入本地 Web 控制台第一版；第一版不控制影刀客户端；已补充 dashboard 高保真静态原型，后续可按原型抽取真实控制台页面。
- 多平台扩展：架构已预留 adapter，当前只实现小红书 CSV。
- 小程序转化归因：尚未接入，等待 `Image-sp` 上线或埋点方案确定。

## 验证记录

最近一次验证：

```powershell
py -3 -m unittest discover -s tests
```

结果：

- 30 tests passed.
- 2026-05-13 Windows PowerShell 复跑通过：30 tests passed.
- 2026-05-14 Windows PowerShell 复跑通过：30 tests passed.
- 2026-05-14 macOS `python3` 复跑通过：30 tests passed.

本次 macOS 验证过程：

```bash
python3 -m unittest discover -s tests
```

第一次结果：

- 22 tests started, `tests/test_web_app.py` 导入失败。
- 根因：当前 Mac Python 环境缺少 `fastapi`。

依赖补齐：

```bash
python3 -m pip install fastapi httpx jinja2 python-multipart uvicorn
```

补齐后再次运行：

```bash
python3 -m unittest discover -s tests
```

结果：

- 30 tests passed.

本次 editable 安装验证：

```powershell
python -m pip install -e .
```

结果：

- 安装成功。

本次 JSON 文档验证：

```bash
python3 -m json.tool docs/rpa-elements/yingdao-command-catalog.json >/dev/null
python3 -m json.tool docs/rpa-elements/xiaohongshu-elements.json >/dev/null
python3 -m json.tool docs/rpa-elements/xiaohongshu-workflow-draft.json >/dev/null
python3 -m json.tool docs/rpa-elements/current-yingdao-mainflow.json >/dev/null
```

结果：

- JSON validation passed.

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
2. 先读 `docs/rpa-elements/yingdao-hybrid-architecture-guide.md`，再结合 `docs/rpa-elements/current-yingdao-mainflow.md` 继续改造影刀流程：搜索页获取相似卡片列表，循环变量使用 `current_card`，点击卡片进入 SPA 弹窗，读取当前地址栏 URL。
3. 详情页字段采集使用容错：非必需的标题、正文、作者、评论文本开启错误处理，失败后继续并赋空值；遇到遮挡点击优先试 JS 点击。
4. 导出新版结构化 xlsx 后，用 Falcon 导入验证 `post/comment` 两类数据。
5. 每天复核日报中的“高价值笔记正文”和“评论痛点与求推荐信号”，记录 `优秀/有用/一般/无用/噪音`。
6. 稳定后再配置 Windows 任务计划，形成影刀采集和 Falcon 分析的分段调度。

## Windows 接手提示

```powershell
git pull
py -3 -m unittest discover -s tests
```

然后：

1. 打开 `docs\rpa-elements\current-yingdao-mainflow.md` 看当前影刀流程状态。
2. 打开 `docs\rpa-elements\xiaohongshu-workflow-draft.md` 和 `docs\yingdao-runbook.md` 看下一步链条。
3. 打开 `prototype\falcon-dashboard.html` 查看 Falcon 方案进度 dashboard 静态原型，后续如要做正式页面，应接入现有 FastAPI Web 控制台而不是另起应用。
4. 如需复核完整链路，再按 `docs/development-guide.md` 运行 Windows smoke workflow。

## Mac 接手提示

```bash
git pull
python3 -m unittest discover -s tests
```

然后：

1. 影刀相关问题先按 `AGENTS.md` 要求读完 `docs/rpa-elements/yingdao-assistant-rules.md`、`docs/rpa-elements/yingdao-component-handbook.md`、`docs/rpa-elements/yingdao-hybrid-architecture-guide.md`、`docs/yingdao-runbook.md`、`docs/rpa-elements/current-yingdao-mainflow.md` 和 `docs/rpa-elements/xiaohongshu-workflow-draft.md`。
2. 继续排查当前小红书点击链路：XPath 获取 `post_link_list` 已能读到 `href_raw`，`should_click_card` 整数旗标可进入点击；当前风险是点击 `a.cover` 后可能误入图片放大层，需要结合详情弹窗 DOM 和交互截图调整点击目标或点击位置。
3. 调试时保留用户影刀流程行号，改节点优先禁用而不是删除；回答用户时用伪工作流格式。
4. 如果 `python3 -m pip install -e .` 因系统 pip 过旧失败，先安装运行依赖 `python3 -m pip install fastapi httpx jinja2 python-multipart uvicorn`，再运行测试。
5. 导出 CSV/xlsx 后，按 `docs/development-guide.md` 运行 macOS smoke workflow 或 Falcon `run-yingdao-daily` 验证导入、分析和日报。
