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
- 实现影刀两列 xlsx 导出导入适配器：
  - A 列映射为 `title/content`。
  - B 列映射为 `url`。
  - `keyword` 由导入命令参数传入，不在流程或代码里写死。
- 补充示例 CSV。
- 补充双机开发规则和 start-work protocol。

## 最近一次提交准备

- 本次变更目标：接入真实影刀网页采集导出的 xlsx，让 Falcon 可直接导入影刀批量数据抓取结果。
- 本次文档更新：
  - `README.md`：说明 RPA 可导入 CSV 或影刀两列 xlsx。
  - `docs/rpa-xiaohongshu.md`：新增影刀 xlsx 两列映射和 Windows/macOS 导入命令。
  - `docs/progress.md`：记录本次影刀接入进展和验证结果。
- 本次验证：
  - `py -3 -m unittest discover -s tests`
  - Windows 真实影刀 xlsx smoke workflow

## 当前问题解决进度

- 已解决：项目从非 git 目录初始化为 git 仓库并推送到 GitHub。
- 已解决：HTTPS 推送缺少凭据的问题，通过 GitHub SSH over 443 推送。
- 已解决：默认模板草稿对探针场景话术不匹配的问题，已按场景区分模板。
- 待确认：真实 GPT-5.5 中转站环境变量尚未在本仓库验证，当前测试使用 fake client 和模板模式。
- 已解决：Windows 基线测试曾因 SQLite 连接未关闭导致临时库文件被占用，已让仓储连接在提交/回滚后显式关闭。
- 已验证：Windows 机器已实际运行基线测试和 smoke workflow。
- 已解决：影刀当前版本未找到本地导出流程入口，改用“批量数据抓取 + 数据表格导出”生成 xlsx。
- 已解决：Falcon 可直接导入影刀 A/B 两列 xlsx，关键词通过 `--keyword` 显式传入。

## 方案进度

- 需求雷达：MVP 已完成。
- AI 触达任务箱：MVP 已完成，当前只生成草稿，不自动发送。
- RPA 接入：已定义 CSV 契约，并接入影刀网页批量数据抓取 xlsx 导出格式；已用真实导出文件导入 25 条样本。
- 多平台扩展：架构已预留 adapter，当前只实现小红书 CSV。
- 小程序转化归因：尚未接入，等待 `Image-sp` 上线或埋点方案确定。

## 验证记录

最近一次验证：

```powershell
py -3 -m unittest discover -s tests
```

结果：

- 12 tests passed.

最近一次 smoke workflow：

- Windows PowerShell，临时目录：`$env:TEMP\falcon-yingdao-smoke`。
- 初始化临时 SQLite。
- 导入真实影刀导出 `data\xhs_raw_export.xlsx`，命令使用 `--keyword "生图小程序"`。
- 分析 25 条样本。
- 创建 9 个触达任务。
- 生成 Markdown 日报。

## 下一步建议

1. 在影刀流程中把导出目录和文件名抽成流程参数，便于 Windows 本机和 PD 虚拟 Windows 切换。
2. 设计 `data/rpa_keywords.csv` 或等价参数，让 Falcon 维护主题/关键词池，影刀按关键词循环采样。
3. 运行 `analyze --drafts template` 复核真实影刀样本的 Top 20 质量。
4. 配置 GPT-5.5 中转站环境变量后，运行 `analyze --drafts gpt`。
5. 根据真实样本复核结果调整 `falcon/analysis.py` 的关键词和阈值。

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
