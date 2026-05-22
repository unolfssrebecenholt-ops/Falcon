# Falcon Agent

Falcon 是给 `AI出图助手` 准备的本地内容运营 Agent。当前版本已经具备“小红书需求雷达 + AI 触达任务箱”的 MVP 能力；长期目标是升级为由 **GPT-5.5 + Image2** 驱动的多平台内容运营工作台。

Falcon 的核心原则是：**系统负责采集、分析、生成和预览，最终执行默认由人确认**。它不会默认自动批量评论、私信或发布。

![Falcon Agent 架构图](docs/assets/falcon-agent-architecture.png)

## 最终架构

Falcon 的目标形态是一套工作流 Agent：

```text
多平台采集
  ↓
数据与资产库
  ↓
GPT-5.5 分析
  ↓
爆款/意向/评论洞察
  ↓
GPT-5.5 文案 + Image2 配图
  ↓
推荐执行队列
  ↓
半自动预览
  ↓
人工修改或一键发布
```

### 采集基座层

- 小红书优先，后续扩展抖音、闲鱼、微博等平台。
- 采集图片、视频、标题、正文、发布时间、点赞、收藏、评论数和评论内容。
- 默认使用真实浏览器交互、复用正常浏览器会话、控制频率和节奏。
- 登录、验证码、风控和关键确认可通过飞书通知与人工回传。

### 数据分析层

- 竞品爆款分析：拆解高表现内容的标题、结构、视觉和互动信号。
- 帖子意向分析：识别推荐、抱怨竞品、求助、需求、购买意向等类型。
- 评论意向分析：从评论中发现可触达用户、痛点、咨询和产品机会。
- 人工评分反哺：用户可标注“优秀 / 有用 / 一般 / 无用 / 噪音”，后续用于校准规则权重和排序。

### 数据报表层

- 目标 UI 为 Next.js 工作台。
- 展示竞品爆款内容、高意向帖子、高意向评论、选题池和执行队列。
- 当前 MVP 已提供 FastAPI + Jinja 本地 Web 控制台。

### 推荐执行层

- GPT-5.5 生成评论、私信、发帖文案和话题建议。
- Image2 生成发帖封面图和配图。
- 执行器默认进入半自动预览：打开页面、填充内容、上传素材，等待用户修改或一键发布。
- 小红书执行器可吸收 `XiaohongshuSkills` 的 preview/CDP 思路，也可把 `xiaohongshu-mcp` 作为可插拔执行器，但必须受安全边界约束。

## 当前能力

- 小红书 CSV 导入。
- 影刀 XLSX 导入，支持旧版 A/B 两列和新版结构化表头。
- Codex 浏览器采集规范与多平台采集辅助脚本草案。
- SQLite 本地数据中枢。
- 启发式意图评分，可在未配置 GPT 时独立运行。
- GPT-5.5 OpenAI 兼容中转站草稿生成。
- Image2 OpenAI 兼容生图客户端，支持主备中转站 fallback。
- Markdown 日报。
- 本地 Web 控制台：关键词池、采集运行、人工复核、触达任务箱。
- 触达任务状态：`pending`、`copied`、`handled`、`skipped`、`invalid`。

## 快速开始

安装依赖：

```bash
python3 -m pip install -e .
```

Windows:

```powershell
py -3 -m pip install -e .
```

初始化并运行一次示例分析：

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

启动本地 Web 控制台：

```bash
python3 -m falcon --db data/falcon.sqlite3 web --host 127.0.0.1 --port 8765
```

Windows:

```powershell
py -3 -m falcon web --host 127.0.0.1 --port 8765 --db data\falcon.sqlite3
```

打开：

```text
http://127.0.0.1:8765
```

## GPT-5.5 与 Image2

复制 `.env.example` 到本地 `.env`，填入自己的中转站配置。`.env` 已被 `.gitignore` 忽略，不要提交真实 key。

GPT-5.5 配置：

```text
FALCON_GPT_BASE_URL=
FALCON_GPT_ENDPOINT=/v1/chat/completions
FALCON_GPT_API_KEY=
FALCON_GPT_MODEL=gpt-5.5
FALCON_GPT_TIMEOUT=60
```

Image2 配置：

```text
FALCON_IMAGE2_PRIMARY_BASE_URL=
FALCON_IMAGE2_PRIMARY_API_KEY=
FALCON_IMAGE2_FALLBACK_BASE_URL=
FALCON_IMAGE2_FALLBACK_API_KEY=
FALCON_IMAGE2_ENDPOINT=/v1/images/generations
FALCON_IMAGE2_MODEL=gpt-image-2
FALCON_IMAGE2_TIMEOUT=90
FALCON_IMAGE2_SIZE=1536x1024
```

生成架构图：

```bash
python3 -m falcon generate-architecture-image --output reports/falcon-agent-architecture.png
```

## 采集接入

Falcon 当前支持三种采集入口：

- CSV/XLSX 导入：适合影刀、人工整理或第三方工具导出。
- Codex 浏览器采集规范：见 `docs/codex-collection-guide.md` 和 `docs/collection-platforms/`。
- 未来程序化采集 Agent：计划使用真实浏览器 Playwright，把当前 Codex 采集经验沉淀为 Falcon 自己可运行的采集执行器。

运行边界：

- 不直接访问平台临时详情链接作为常规采集路径。
- 不用 JavaScript click 打开内容卡片。
- 不保存验证码、Cookie、token 或真实 API key。
- 遇到验证码、滑块、设备验证、风控提示时暂停并通知人工。

## 项目结构

- `falcon/`：核心 Python 包、CLI、分析、草稿、Image2/GPT 客户端和 Web 控制台。
- `falcon/adapters/`：CSV/XLSX 导入适配器。
- `scripts/collection/`：Codex/浏览器采集辅助脚本草案。
- `tests/`：行为测试。
- `examples/`：示例采集数据。
- `docs/`：开发指南、进度、RPA 和采集资料。
- `docs/assets/`：README 和文档使用的静态资产。

## 开发与验证

基线测试：

```bash
python3 -m unittest discover -s tests
```

Windows:

```powershell
py -3 -m unittest discover -s tests
```

JavaScript 采集辅助脚本语法检查：

```powershell
Get-ChildItem scripts\collection -Recurse -Filter *.mjs | ForEach-Object { node --check $_.FullName }
```

双机开发规则见 `AGENTS.md` 和 `docs/development-guide.md`。每次提交前更新 `docs/progress.md`，并确保本地运行数据、报告、`.env` 和真实密钥不进入仓库。
