# Falcon 开发指南

本文记录 Windows 和 macOS 都可执行的开发方式。新增工具或依赖时，必须同步更新本文。

## 环境要求

- Python 3.9 或更高版本。
- Git。
- 可选：GPT-5.5 OpenAI 兼容中转站环境变量。

当前项目使用 Python + FastAPI + Jinja + SQLite。新增依赖必须同步写入 `pyproject.toml`，并保持 Windows 和 macOS 可安装。

## 获取代码

macOS:

```bash
git clone ssh://git@ssh.github.com:443/unolfssrebecenholt-ops/Falcon.git
cd Falcon
```

Windows PowerShell:

```powershell
git clone ssh://git@ssh.github.com:443/unolfssrebecenholt-ops/Falcon.git
cd Falcon
```

如果本机 GitHub SSH 没有配置，也可以使用 HTTPS，但需要提前配置 GitHub 凭据。

## 安装依赖

macOS:

```bash
python3 -m pip install -e .
```

Windows PowerShell:

```powershell
py -3 -m pip install -e .
```

## 基线验证

macOS:

```bash
python3 -m unittest discover -s tests
```

Windows PowerShell:

```powershell
py -3 -m unittest discover -s tests
```

## 本地 smoke workflow

macOS:

```bash
rm -rf /tmp/falcon-smoke
mkdir -p /tmp/falcon-smoke
python3 -m falcon --db /tmp/falcon-smoke/falcon.sqlite3 init-db
python3 -m falcon --db /tmp/falcon-smoke/falcon.sqlite3 import-csv examples/xiaohongshu_samples.csv
python3 -m falcon --db /tmp/falcon-smoke/falcon.sqlite3 analyze --drafts template
python3 -m falcon --db /tmp/falcon-smoke/falcon.sqlite3 report --output /tmp/falcon-smoke/daily-report.md
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force $env:TEMP\falcon-smoke -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $env:TEMP\falcon-smoke | Out-Null
py -3 -m falcon --db $env:TEMP\falcon-smoke\falcon.sqlite3 init-db
py -3 -m falcon --db $env:TEMP\falcon-smoke\falcon.sqlite3 import-csv examples\xiaohongshu_samples.csv
py -3 -m falcon --db $env:TEMP\falcon-smoke\falcon.sqlite3 analyze --drafts template
py -3 -m falcon --db $env:TEMP\falcon-smoke\falcon.sqlite3 report --output $env:TEMP\falcon-smoke\daily-report.md
```

## 影刀 smoke workflow

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force $env:TEMP\falcon-yingdao-smoke -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $env:TEMP\falcon-yingdao-smoke | Out-Null
py -3 -m falcon --db $env:TEMP\falcon-yingdao-smoke\falcon.sqlite3 run-yingdao-daily data\xhs_raw_export.xlsx --keyword "生图小程序" --report-output $env:TEMP\falcon-yingdao-smoke\daily-report.md
```

macOS:

```bash
rm -rf /tmp/falcon-yingdao-smoke
mkdir -p /tmp/falcon-yingdao-smoke
python3 -m falcon --db /tmp/falcon-yingdao-smoke/falcon.sqlite3 run-yingdao-daily data/xhs_raw_export.xlsx --keyword "生图小程序" --report-output /tmp/falcon-yingdao-smoke/daily-report.md
```

`data/xhs_raw_export.xlsx` 是本机影刀导出的运行数据，不提交到仓库。

## 本地 Web 控制台

macOS:

```bash
python3 -m falcon --db data/falcon.sqlite3 web --host 127.0.0.1 --port 8765
```

Windows PowerShell:

```powershell
py -3 -m falcon --db data\falcon.sqlite3 web --host 127.0.0.1 --port 8765
```

也支持：

```powershell
py -3 -m falcon web --host 127.0.0.1 --port 8765 --db data\falcon.sqlite3
```

浏览器打开：

```text
http://127.0.0.1:8765
```

第一版 Web 控制台只管理 Falcon 侧流程，不控制影刀客户端。

## GPT-5.5 中转站

环境变量名：

- `FALCON_GPT_BASE_URL`
- `FALCON_GPT_ENDPOINT`
- `FALCON_GPT_API_KEY`
- `FALCON_GPT_MODEL`
- `FALCON_GPT_TIMEOUT`

不要提交真实 key。仓库只保留 `.env.example`。

## Image2 生图中转站

Image2 使用 OpenAI 兼容图片接口，真实 key 只放本地 `.env` 或环境变量，不提交到仓库。

环境变量名：

- `FALCON_IMAGE2_PRIMARY_BASE_URL`
- `FALCON_IMAGE2_PRIMARY_API_KEY`
- `FALCON_IMAGE2_FALLBACK_BASE_URL`
- `FALCON_IMAGE2_FALLBACK_API_KEY`
- `FALCON_IMAGE2_ENDPOINT`
- `FALCON_IMAGE2_MODEL`
- `FALCON_IMAGE2_TIMEOUT`
- `FALCON_IMAGE2_SIZE`

生成 Falcon Agent 架构图：

macOS:

```bash
python3 -m falcon generate-architecture-image --output reports/falcon-agent-architecture.png
```

Windows PowerShell:

```powershell
py -3 -m falcon generate-architecture-image --output reports\falcon-agent-architecture.png
```

如果主中转站失败或超时，客户端会尝试备用中转站。日志和命令输出不得打印完整 API key。

## 提交流程

1. `git pull`
2. 修改代码或文档。
3. 运行基线验证，必要时运行 smoke workflow。
4. 更新 `docs/progress.md`，写清：
   - 本次完成内容。
   - 当前问题解决进度。
   - 方案进度。
   - 验证结果。
   - 下一台机器接手建议。
5. `git status -sb`
6. `git add` 指定文件。
7. `git commit -m "..."`
8. `git push`

## 跨平台约束

- 文件路径用 `pathlib` 或 CLI 参数传入，不在代码里写死 `/tmp`、盘符或用户目录。
- 文档命令同时给出 macOS 和 Windows PowerShell 版本。
- 不依赖 shell-only 行为实现核心功能。
- 不把生成的 SQLite、日报、缓存或 `.env` 提交到仓库。

## Codex collection module

V1 collection is triggered from a Codex conversation and uses the Codex in-app browser/manual browser session. It is not a standalone CLI or Web feature yet.

Entry phrase:

```text
开始采集：平台=小红书；关键词=ai头像,小红书封面；每个关键词=30条
```

Before running a collection task, read:

- `docs/codex-collection-guide.md`
- `docs/collection-platforms/{platform}.md`

The reusable helper modules live in:

```text
scripts/collection/core/
scripts/collection/platforms/
```

No new npm dependency is required. Validate JavaScript syntax with:

macOS:

```bash
find scripts/collection -name '*.mjs' -print0 | xargs -0 -n1 node --check
```

Windows PowerShell:

```powershell
Get-ChildItem scripts\collection -Recurse -Filter *.mjs | ForEach-Object { node --check $_.FullName }
```

Runtime output is local-only and ignored by Git:

```text
datas/{platform_slug}/{keyword}_{yyyyMMddHHmm}/
  {keyword}_{yyyyMMddHHmm}.csv
  assets/
  collection_steps.md
  extra.jsonl
datas/{platform_slug}/run_summary_{yyyyMMddHHmm}.json
```

Security notes:

- Use real browser interaction: simulated click, keyboard input, and human-like scrolling.
- Do not use JavaScript click to open content cards.
- Do not navigate directly to transient detail links.
- Do not save platform links.
- Verification codes are transient conversation input only and must never be written to files.
- Yingdao remains legacy/fallback for now and should not be deleted.
