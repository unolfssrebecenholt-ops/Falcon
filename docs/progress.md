# Falcon 项目进度

本文件是 Windows 和 M1 Mac 双机开发的接手入口。每次提交前必须更新。

## 当前状态

- 仓库已推送到 GitHub：`ssh://git@ssh.github.com:443/unolfssrebecenholt-ops/Falcon.git`
- 当前分支：`main`
- 当前阶段：第一版本地 MVP 已建立。
- 技术形态：Python 标准库 + SQLite + CSV 导入 + Markdown 日报。
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
- 补充示例 CSV。
- 补充双机开发规则和 start-work protocol。

## 最近一次提交准备

- 本次变更目标：沉淀影刀 RPA 小红书公开样本采集教程、指令截图归档、当前主流程状态和排错记录，方便 Windows 机器继续搭建真实影刀流程。
- 本次文档更新：
  - `docs/rpa-elements/yingdao-command-catalog.md` / `.json`：按用户截图归档影刀指令分组、一层指令、二/三层关键指令。
  - `docs/rpa-elements/xiaohongshu-workflow-draft.md` / `.json`：记录小红书公开样本采集的准流程和待补网页元素。
  - `docs/rpa-elements/current-yingdao-mainflow.md` / `.json`：记录当前影刀主流程截图中已经配置的步骤、变量和元素。
  - `docs/rpa-elements/xiaohongshu-elements.md` / `.json`：记录待归档的小红书网页元素和命名约定。
  - `prototype/xiaohongshu-rpa-sop.html`：新增可直接打开的影刀采集 SOP 教学原型。
  - `ShadowBladeElement/`：保存用户提供的影刀指令分组截图和关键二/三层截图，作为后续编排流程的证据源。
  - 为 Windows 兼容性，截图文件名中的 `:` 已改为 `-`，例如 `Excel-WPS表格.png`、`流程-应用.png`。
  - `docs/progress.md`：更新本次 RPA 交接状态、当前错误和 Windows 接手提示。
- 本次验证：
  - `python3 -m unittest discover -s tests`
  - `python3 -m json.tool` 校验 `docs/rpa-elements/*.json`

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
- 待确认：真实 GPT-5.5 中转站环境变量尚未在本仓库验证，当前测试使用 fake client 和模板模式。
- 待确认：Windows 机器尚未实际运行 smoke workflow，需要下次 Windows 接手时验证。
- 待继续：小红书真实网页元素仍需继续归档，尤其是详情页 `detail_title`、`detail_content`、评论文本元素，以及最终 CSV 写入动作的成功验证。

## 方案进度

- 需求雷达：MVP 已完成。
- AI 触达任务箱：MVP 已完成，当前只生成草稿，不自动发送。
- RPA 接入：CSV 契约已定义；影刀指令目录、教学 SOP、当前主流程和关键排错已归档；真实影刀流程已进入手工搭建/调试阶段，尚未完成可稳定导出的真实 CSV。
- 多平台扩展：架构已预留 adapter，当前只实现小红书 CSV。
- 小程序转化归因：尚未接入，等待 `Image-sp` 上线或埋点方案确定。

## 验证记录

最近一次验证：

```bash
python3 -m unittest discover -s tests
```

结果：

- 10 tests passed.

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

- 初始化临时 SQLite。
- 导入 `examples/xiaohongshu_samples.csv`。
- 分析 5 条样本。
- 创建 4 个触达任务。
- 生成 Markdown 日报。

## 下一步建议

1. 在 Windows 上 `git pull` 后先读 `docs/rpa-elements/current-yingdao-mainflow.md`，从当前影刀主流程继续。
2. 在影刀中继续调试链接流程：
   - `获取相似元素列表(web)` 得到 `post_link_list`。
   - `ForEach列表循环` 或 `For次数循环` 处理链接。
   - 跳转前先保存 `href_raw` 和完整 `post_url`。
   - 如用下标循环，结束值使用 `list_len - 1`。
3. 优先打开详情页提取 `detail_title` 和 `detail_content`，先只写 `source_type=post` 的 7 列 CSV。
4. CSV 每行字段固定为：
   - `platform` = `xiaohongshu`
   - `keyword` = `current_keyword`
   - `source_type` = `post`
   - `title` = 详情页标题
   - `content` = 详情页正文/摘要
   - `url` = `post_url`
   - `published_at` = 空字符串
5. 导出或写入一份小样本 CSV 后，使用 `python3 -m falcon --db data/falcon.sqlite3 import-csv <CSV路径>` / Windows `py -3 -m falcon ...` 验证。
6. 评论采集放到第二阶段：一篇笔记可对应一条 `post` 行和多条 `comment` 行，评论内容写入同一个 `content` 字段，用 `source_type=comment` 区分。

## Windows 接手提示

```powershell
git pull
py -3 -m unittest discover -s tests
```

然后：

1. 打开 `docs\rpa-elements\current-yingdao-mainflow.md` 看当前影刀流程状态。
2. 打开 `docs\rpa-elements\xiaohongshu-workflow-draft.md` 看下一步链条。
3. 在影刀中继续修正当前报错：
   - 循环下标不要到 `list_len`，要到 `list_len - 1`。
   - 跳转详情页前先保存完整 `post_url`。
   - 跳转后不要再访问 `link_item` 这种旧页面元素对象。
4. 跑通真实 CSV 后再按 `docs/development-guide.md` 运行 Windows smoke workflow。

## Mac 接手提示

```bash
git pull
python3 -m unittest discover -s tests
```

然后按 `docs/development-guide.md` 运行 macOS smoke workflow。
