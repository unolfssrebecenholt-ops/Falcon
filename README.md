# Falcon 需求雷达

Falcon 第一版是给 `AI出图助手` 用的本地 MVP：小红书优先的社媒需求雷达 + AI 触达任务箱。

它不自动发送评论或私信。系统只做低频公开样本导入、意图评分、选题日报和待处理草稿；最终发送由人工确认。

## 当前能力

- 小红书 RPA/表格 CSV 导入，支持影刀两列 xlsx 导出。
- SQLite 本地数据中枢。
- 小红书封面主推，活动海报、微信头像、朋友圈背景、随便画画作为探针场景。
- 启发式意图评分，可在未配置 GPT 时独立运行。
- GPT-5.5 中转站草稿生成，配置后用于评论区回复、私信和轻建议草稿。
- Markdown 日报输出。
- 触达任务箱状态流转：`pending`、`copied`、`handled`、`skipped`、`invalid`。

## 快速开始

macOS:

```bash
python3 -m falcon --db data/falcon.sqlite3 init-db
python3 -m falcon --db data/falcon.sqlite3 import-csv examples/xiaohongshu_samples.csv
python3 -m falcon --db data/falcon.sqlite3 analyze --drafts template
python3 -m falcon --db data/falcon.sqlite3 report --output reports/daily-report.md
```

Windows PowerShell:

```powershell
py -3 -m falcon --db data\falcon.sqlite3 init-db
py -3 -m falcon --db data\falcon.sqlite3 import-csv examples\xiaohongshu_samples.csv
py -3 -m falcon --db data\falcon.sqlite3 analyze --drafts template
py -3 -m falcon --db data\falcon.sqlite3 report --output reports\daily-report.md
```

查看日报：

```bash
sed -n '1,220p' reports/daily-report.md
```

运行测试：

```bash
python3 -m unittest discover -s tests
```

Windows:

```powershell
py -3 -m unittest discover -s tests
```

## 双机开发

本项目支持 Windows 和 M1 Mac 双机开发。每次开始工作先 `git pull`，然后阅读：

1. `AGENTS.md`
2. `docs/progress.md`
3. `docs/development-guide.md`
4. `README.md`
5. `project.md`

用户后续可以只说“开始工作”，Codex 应按 `AGENTS.md` 里的 start-work protocol 自动接手。每次提交前必须更新 `docs/progress.md`，写清项目进度、当前问题解决进度、方案进度、验证结果和下一步。

## GPT-5.5 中转站配置

复制 `.env.example` 到本地环境变量来源，或在 shell 中设置：

```bash
export FALCON_GPT_BASE_URL="https://your-gpt55-relay.example.com"
export FALCON_GPT_ENDPOINT="/v1/chat/completions"
export FALCON_GPT_API_KEY="..."
export FALCON_GPT_MODEL="gpt-5.5"
```

然后使用：

```bash
python3 -m falcon --db data/falcon.sqlite3 analyze --drafts gpt
```

日报也可以追加 GPT-5.5 总结：

```bash
python3 -m falcon --db data/falcon.sqlite3 report --summary gpt --output reports/daily-report.md
```

不要把真实 API Key 写入仓库、截图或日志。

## RPA 接入方式

第一版不内置直接抓取网站的代码。影刀或其他 RPA 只需要低频采集公开可见内容，并导出 CSV 或影刀两列 xlsx，字段和命令见 [docs/rpa-xiaohongshu.md](docs/rpa-xiaohongshu.md)。

## 目录

- `falcon/`：核心 Python 包。
- `tests/`：行为测试。
- `examples/`：RPA CSV 示例。
- `docs/`：操作说明和设计边界。
- `project.md`：当前项目方案。
