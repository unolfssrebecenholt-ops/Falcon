# Falcon 开发指南

本文记录 Windows 和 macOS 都可执行的开发方式。新增工具或依赖时，必须同步更新本文。

## 环境要求

- Python 3.9 或更高版本。
- Git。
- 可选：GPT-5.5 OpenAI 兼容中转站环境变量。

当前项目不依赖第三方 Python 包，优先使用标准库，便于 Windows 和 macOS 同时运行。

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

## GPT-5.5 中转站

环境变量名：

- `FALCON_GPT_BASE_URL`
- `FALCON_GPT_ENDPOINT`
- `FALCON_GPT_API_KEY`
- `FALCON_GPT_MODEL`
- `FALCON_GPT_TIMEOUT`

不要提交真实 key。仓库只保留 `.env.example`。

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
