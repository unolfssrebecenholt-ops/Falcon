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

- 本次变更目标：新增双机开发项目规则，确保 Windows 和 M1 Mac 都能从 GitHub 接手。
- 本次文档更新：
  - `AGENTS.md`：新增双机开发规则、start-work protocol、提交交接 checklist。
  - `README.md`：新增 Windows/macOS 快速开始和测试命令。
  - `docs/development-guide.md`：新增跨平台开发、验证和提交流程。
  - `docs/progress.md`：新增本接手入口。
  - `project.md`：补充双机开发规则。
- 本次验证：
  - `python3 -m unittest discover -s tests`
  - macOS smoke workflow

## 当前问题解决进度

- 已解决：项目从非 git 目录初始化为 git 仓库并推送到 GitHub。
- 已解决：HTTPS 推送缺少凭据的问题，通过 GitHub SSH over 443 推送。
- 已解决：默认模板草稿对探针场景话术不匹配的问题，已按场景区分模板。
- 待确认：真实 GPT-5.5 中转站环境变量尚未在本仓库验证，当前测试使用 fake client 和模板模式。
- 待确认：Windows 机器尚未实际运行 smoke workflow，需要下次 Windows 接手时验证。

## 方案进度

- 需求雷达：MVP 已完成。
- AI 触达任务箱：MVP 已完成，当前只生成草稿，不自动发送。
- RPA 接入：已定义 CSV 契约，尚未接入真实影刀流程。
- 多平台扩展：架构已预留 adapter，当前只实现小红书 CSV。
- 小程序转化归因：尚未接入，等待 `Image-sp` 上线或埋点方案确定。

## 验证记录

最近一次验证：

```bash
python3 -m unittest discover -s tests
```

结果：

- 10 tests passed.

最近一次 smoke workflow：

- 初始化临时 SQLite。
- 导入 `examples/xiaohongshu_samples.csv`。
- 分析 5 条样本。
- 创建 4 个触达任务。
- 生成 Markdown 日报。

## 下一步建议

1. 在 Windows 上执行 `docs/development-guide.md` 的基线验证和 smoke workflow。
2. 用影刀导出一份真实小红书 CSV，按 `docs/rpa-xiaohongshu.md` 字段导入。
3. 运行 `analyze --drafts template` 先做无 key 验证。
4. 配置 GPT-5.5 中转站环境变量后，运行 `analyze --drafts gpt`。
5. 根据真实样本复核结果调整 `falcon/analysis.py` 的关键词和阈值。

## Windows 接手提示

```powershell
git pull
py -3 -m unittest discover -s tests
```

然后按 `docs/development-guide.md` 运行 Windows smoke workflow。

## Mac 接手提示

```bash
git pull
python3 -m unittest discover -s tests
```

然后按 `docs/development-guide.md` 运行 macOS smoke workflow。
