# Falcon 开发指南

本文记录 Windows 和 macOS 都可执行的开发方式。新增工具或依赖时，必须同步更新本文。

## 环境要求

- Python 3.9 或更高版本。
- Git。
- 可选：GPT-5.5 OpenAI 兼容中转站环境变量。
- 可选：Image2 OpenAI 兼容图片中转站环境变量。

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

## 安装依赖

Recommended one-command startup:

macOS:

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

Windows PowerShell:

```powershell
.\scripts\start.ps1
```

The startup script runs these steps in order:

1. `python -m pip install --upgrade pip setuptools wheel`
2. `python -m pip install -e .`
3. `npm install` in `sidecar/collector`
4. `npx playwright install chromium` in `sidecar/collector`
5. create local `data/`, `runtime/collector/`, and `browser-profiles/`
6. initialize `data/falcon.sqlite3`
7. run `falcon doctor`
8. open and start the local Web workbench at `http://127.0.0.1:8765`

If port `8765` is already in use, the script automatically tries the next available port and prints the final URL.

For fast restarts after dependencies are already installed:

macOS:

```bash
./scripts/start.sh --skip-install
```

Windows PowerShell:

```powershell
.\scripts\start.ps1 --skip-install
```

Doctor-only checks:

macOS:

```bash
python3 -m falcon doctor --ensure-dirs
```

Windows PowerShell:

```powershell
py -3 -m falcon doctor --ensure-dirs
```

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

## Node collector sidecar

Install real-mode browser dependency:

macOS:

```bash
cd sidecar/collector
npm install
npx playwright install chromium
```

Windows PowerShell:

```powershell
Set-Location sidecar\collector
npm install
npx playwright install chromium
Set-Location ..\..
```

Dry-run sidecar contract test:

macOS:

```bash
python3 -m unittest tests.test_sidecar_contract
```

Windows PowerShell:

```powershell
py -3 -m unittest tests.test_sidecar_contract
```

Command shape:

```text
node sidecar/collector/index.mjs --request runtime/collector/<run_id>/request.json --events runtime/collector/<run_id>/events.jsonl --output runtime/collector/<run_id>/records.jsonl --assets runtime/collector/<run_id>/assets --profile browser-profiles/<platform>/<profile>
```

Python CLI dry-run:

```powershell
py -3 -m falcon --db data\falcon.sqlite3 collector-dry-run --platform xiaohongshu --profile default --keyword "内容运营" --max-posts 5
```

Python CLI real browser run:

```powershell
py -3 -m falcon --db data\falcon.sqlite3 collector-run --platform xiaohongshu --profile default --keyword "内容运营" --max-posts 5
```

Profile login from the Web workbench:

1. Open `/collector`.
2. In `平台账号 / Profile`, choose platform and profile name.
3. Click `打开登录窗口`.
4. Finish login in the opened browser window, then close that window.

The profile is stored under `browser-profiles/<platform>/<profile>/` and is ignored by Git. Use a different profile name for each account, for example `default`, `creator`, or `backup`. Same-platform same-profile tasks should be treated as serial work; different profiles can be scheduled independently later.

Manual sidecar profile login:

macOS:

```bash
cd sidecar/collector
npm run profile-login
```

Windows PowerShell:

```powershell
Set-Location sidecar\collector
npm run profile-login
Set-Location ..\..
```

## 本地 smoke workflow

macOS:

```bash
rm -rf /tmp/falcon-smoke
mkdir -p /tmp/falcon-smoke
python3 -m falcon --db /tmp/falcon-smoke/falcon.sqlite3 init-db
python3 -m falcon write-keyword-pool /tmp/falcon-smoke/collection_keywords.csv --theme "内容运营"
python3 -m falcon --db /tmp/falcon-smoke/falcon.sqlite3 report --output /tmp/falcon-smoke/daily-report.md
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force $env:TEMP\falcon-smoke -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $env:TEMP\falcon-smoke | Out-Null
py -3 -m falcon --db $env:TEMP\falcon-smoke\falcon.sqlite3 init-db
py -3 -m falcon write-keyword-pool $env:TEMP\falcon-smoke\collection_keywords.csv --theme "内容运营"
py -3 -m falcon --db $env:TEMP\falcon-smoke\falcon.sqlite3 report --output $env:TEMP\falcon-smoke\daily-report.md
```

## 本地 Web 控制台

macOS:

```bash
python3 -m falcon web --host 127.0.0.1 --port 8765 --db data/falcon.sqlite3
```

Windows PowerShell:

```powershell
py -3 -m falcon web --host 127.0.0.1 --port 8765 --db data\falcon.sqlite3
```

浏览器打开：

```text
http://127.0.0.1:8765
```

当前 Web 工作台已经接入采集队列、账号 profile、任务详情、样本预览和分析入口。真实采集仍以本地人工可控为边界，运行数据只保存在 ignored 目录。

## 设计参考

当前最新整站原型：

```text
docs/design/falcon-layout-redesign-v2/
```

`docs/design/falcon-layout-redesign-v1/` 暂时保留用于视觉对照。旧的一次性原型、截图批次和已执行计划不再保留在工作树中；需要追溯时使用 Git history。

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
4. 更新 `docs/progress.md`，写清本次完成内容、当前问题、方案进度、验证结果和下一台机器接手建议。
5. `git status -sb`
6. `git add` 指定文件。
7. `git commit -m "..."`
8. `git push`

## 跨平台约束

- 文件路径用 `pathlib` 或 CLI 参数传入，不在代码里写死 `/tmp`、盘符或用户目录。
- 文档命令同时给出 macOS 和 Windows PowerShell 版本。
- 不依赖 shell-only 行为实现核心功能。
- 不把生成的 SQLite、日报、缓存、浏览器 profile 或 `.env` 提交到仓库。
