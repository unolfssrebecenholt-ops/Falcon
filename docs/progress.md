# Falcon 当前交接快照

本文件只保留当前可继续开发所需的信息。历史实现流水账、已执行计划和过时原型已经从仓库清理；需要追溯细节时使用 Git history。

## 2026-05-28 Repository cleanup and stable handoff

- 本次目标是把仓库整理成更干净、可稳定继续开发的状态：
  - 删除已执行的历史计划文档目录。
  - 删除过时设计原型和截图批次，只保留最新整站原型 `docs/design/falcon-layout-redesign-v1/`。
  - 删除未被当前 README / 开发指南引用的历史架构图资产，只保留 `docs/assets/falcon-agent-architecture.png`。
  - 将本文件从历史流水账压缩为当前交接快照。
- 同步保留并收口本地已有启动链改动：
  - `scripts/falcon_bootstrap.py` 首次安装前升级 `pip`、`setuptools`、`wheel`，降低干净机器安装失败概率。
  - `docs/development-guide.md` 已同步启动步骤。
  - `falcon/doctor.py` 和 `falcon/image2.py` 使用 `Optional[...]`，保持项目声明的 Python 3.9 兼容性。

## 2026-05-28 macOS startup script smoke

- 本次验证 `./scripts/start.sh --skip-install --no-open` 的真实启动路径：
  - 首次运行发现 `scripts/start.sh` 缺少可执行位，按 README / development guide 中的 `./scripts/start.sh` 会 `permission denied`。
  - 已修复 `scripts/start.sh` 文件模式，macOS 可直接执行。
  - 启动脚本成功初始化 `data/falcon.sqlite3`，运行 `falcon doctor`，并自动避开忙碌的 `8765`，改用 `http://127.0.0.1:8766`。
  - HTTP smoke 确认 `/`、`/collector`、`/analysis?platform=xiaohongshu`、`/collector/environment` 均返回 200。
  - 临时 Uvicorn 进程已停止，没有留下占用 `8766` 的服务。

## 当前产品状态

- Falcon 是本地优先的内容运营采集、分析和人工确认执行工作台。
- 当前主线优先支持小红书浏览器采集：
  - profile 登录、队列创建、启动、继续、重跑、归档、人工处理窗口和 profile 风控/占用提示已落地。
  - 采集 sidecar 采用低频真实浏览器路径，保存规范化帖子、评论、媒体截图资产、事件和证据链。
  - 运行数据保存在 ignored 的 `data/`、`runtime/collector/`、`browser-profiles/`，不得进入 Git。
- 分析层已有意向分析 v1：
  - 可从同平台 completed runs 创建临时数据包。
  - GPT-5.5 生成和执行语义探针，保存帖子级/评论级证据。
  - GPT 未配置时任务会失败并显示原因，不做本地假 fallback。
- 相关性策略当前为默认优质：
  - 采集样本默认写入 `100 / excellent / primary`。
  - 人工校准仍可降级为参考或跳过。

## 当前保留文档

- `AGENTS.md`：项目规则、双机协作和安全边界。
- `README.md`：项目入口、定位、快速启动和常用命令。
- `docs/development-guide.md`：开发、测试、采集、配置和提交流程。
- `project.md`：Falcon Agent 重构方案与模块边界。
- `docs/design/falcon-layout-redesign-v1/`：当前唯一保留的最新整站设计参考。

## 下一步建议

1. 把意向分析 v1 继续接到生成草稿、人工审阅和执行预览闭环，让 completed collection runs 能稳定产出可确认的选题和内容动作。
2. 在真实 GPT-5.5 配置机器上跑一次分析任务 smoke，验证探针生成、探针编辑、执行分析和证据展示完整链路。
3. 继续收紧小红书采集人工处理体验：处理窗口、继续采集、证据回放和失败恢复都应保持可解释。

## 验证记录

- 2026-05-28 macOS:
  - `python3 -m unittest discover -s tests`：208 tests passed。
  - `python3 -m compileall falcon scripts/falcon_bootstrap.py`：passed。
  - `node --check sidecar/collector/index.mjs`：passed。
  - `node --check sidecar/collector/xiaohongshu.mjs`：passed。
  - `node --check sidecar/collector/xiaohongshu-normalize.mjs`：passed。
  - `node --check sidecar/collector/profile-login.mjs`：passed。
  - `git diff --check`：passed。
- 2026-05-28 macOS startup smoke:
  - `./scripts/start.sh --skip-install --no-open`：passed after executable-bit fix。
  - `curl http://127.0.0.1:8766/`：200。
  - `curl http://127.0.0.1:8766/collector`：200。
  - `curl 'http://127.0.0.1:8766/analysis?platform=xiaohongshu'`：200。
  - `curl http://127.0.0.1:8766/collector/environment`：200。

## Windows/Mac 接手说明

- 开始工作：
  - macOS: `git pull && python3 -m unittest discover -s tests`
  - Windows: `git pull; py -3 -m unittest discover -s tests`
- 启动工作台：
  - macOS: `./scripts/start.sh --skip-install`
  - Windows: `.\scripts\start.ps1 --skip-install`
- 如果是全新机器，去掉 `--skip-install` 让启动脚本安装 Python package、Node sidecar 依赖和 Playwright Chromium。
