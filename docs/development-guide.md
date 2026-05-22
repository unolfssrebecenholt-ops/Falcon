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
python3 -m falcon write-keyword-pool /tmp/falcon-smoke/collection_keywords.csv --theme "生图小程序"
python3 -m falcon --db /tmp/falcon-smoke/falcon.sqlite3 report --output /tmp/falcon-smoke/daily-report.md
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force $env:TEMP\falcon-smoke -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $env:TEMP\falcon-smoke | Out-Null
py -3 -m falcon --db $env:TEMP\falcon-smoke\falcon.sqlite3 init-db
py -3 -m falcon write-keyword-pool $env:TEMP\falcon-smoke\collection_keywords.csv --theme "生图小程序"
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

当前 Web 控制台保留为 Agent 工作台外壳。采集执行器将在后续重构中接入。

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
