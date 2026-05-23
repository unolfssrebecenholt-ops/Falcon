# Falcon 项目进度

本文件是 Windows 和 M1 Mac 双机开发的接手入口。每次提交前必须更新。

## 2026-05-23 Cross-platform startup and environment doctor

- 本次完成跨平台启动与环境自检第一版：
  - 新增 `falcon doctor`，统一检查 Python、Node.js、npm、collector sidecar package、Node Playwright package、Playwright Chromium、本地 `data/`、`runtime/collector/`、`browser-profiles/` 目录，以及 GPT-5.5/Image2 relay 配置。
  - 新增 `scripts/falcon_bootstrap.py` 作为 Windows/macOS 共用启动核心。
  - 新增 `scripts/start.ps1` 与 `scripts/start.sh`，用户启动项目时只需要运行平台对应脚本。
  - 启动流程会安装 Python editable package、安装 sidecar npm 依赖、安装 Playwright Chromium、创建本地目录、初始化 SQLite、运行 doctor、打开并启动 Web 工作台；若 `8765` 被占用，会自动尝试下一个可用端口。
  - `/collector` 总览新增 Environment doctor 面板，能在可视化页面看到依赖和本地目录状态。
  - Windows 下 `npm.cmd`/`npx.cmd` 解析已处理，避免 subprocess 找不到 `.cmd` launcher。
  - 新增 `sidecar/collector/package-lock.json` 锁定 Node sidecar 依赖，新增 `node_modules/` Git 忽略规则。
- 验证结果：
  - `py -3 -m unittest discover -s tests`：68 tests passed。
  - `py -3 -m compileall falcon`：passed。
  - 旧路径关键词扫描无命中。
  - `py -3 scripts\falcon_bootstrap.py --dry-run`：启动命令链可正确输出。
  - `py -3 scripts\falcon_bootstrap.py --dry-run --skip-install --port 8765`：当 `8765` 已被占用时，自动切换到 `8766`。
  - `py -3 -m falcon doctor --project-root . --ensure-dirs`：Required checks OK；当前 Windows 机器 Node.js、npm、sidecar Node Playwright package、Playwright Chromium、本地目录均就绪。
- 已知问题：
  - 如果上一轮 Web 服务仍在运行，新的 `start.ps1` 会自动换端口；已打开的旧页面仍可继续使用。
  - Web 环境面板是同步检查，若某台机器 Node/Playwright 状态异常，打开 `/collector` 时可能比普通页面稍慢。
- 下一步：
  - 用户在 Windows 运行 `.\scripts\start.ps1`，在 macOS 运行 `./scripts/start.sh`，确认首次安装和 Web 自动打开体验。
  - sidecar 依赖安装完成后，再进入小红书真实 profile 登录与 `collector-run` 人工 smoke。
- Windows/Mac 接手说明：
  - Windows：`git pull` 后运行 `.\scripts\start.ps1`；若依赖已装好，可运行 `.\scripts\start.ps1 --skip-install`。
  - macOS：`git pull` 后运行 `chmod +x scripts/start.sh`，再运行 `./scripts/start.sh`；若依赖已装好，可运行 `./scripts/start.sh --skip-install`。

## 2026-05-23 Falcon collector foundation

- 本次完成第一阶段采集层基础闭环：
  - 新增采集公共合同：`runtime/collector/<run_id>/`、`browser-profiles/<platform>/<profile>/`、`request.json`、`events.jsonl`、`records.jsonl`、`assets/`。
  - 新增 SQLite 采集模型与 repository：collection run、event、post、comment、media asset、evidence，支持旧库增量初始化、事件排序、样本去重和看板统计。
  - 新增 `CollectorService`：创建 run、写 sidecar request、启动 Node sidecar、读取 events/records、入库、状态同步、重复 ingest 幂等保护、路径逃逸防护。
  - 新增 CLI：`collector-dry-run`、`collector-run`、`collector-ingest`。
  - 新增 Node Playwright sidecar：dry-run 可写出合法事件和记录；真实模式提供小红书 adapter skeleton，支持持久 profile、搜索页、可见卡片快照、截图证据、人工处理事件、缺少 Playwright 的清晰失败。
  - 新增 sidecar package 描述与安装说明，真实模式依赖 `playwright`，dry-run 不需要登录。
  - Web 工作台落地当前 v3 信息架构：`/collector`、`/collector/create`、`/collector/runs/{run_id}`、`/analysis`、`/execution`，左侧按采集、分析、执行分组。
  - Web 创建采集任务会入库并准备 sidecar request；任务详情展示事件链、样本、资产和证据；分析页可把采集样本送入现有分析队列；执行页只展示待人工确认草稿队列。
  - `.gitignore` 新增 `runtime/`，继续忽略 browser profiles、报告、本地数据库和密钥。
- 已解决的问题：
  - Web/CLI 的采集路径参数已限制为安全标识，避免 run、platform、profile 写出预期 runtime/profile 根目录。
  - `collector-ingest` 重复执行不会重复写入相同事件、评论、资产和证据。
  - 自动生成 run id 已加入短随机后缀，避免同秒任务冲突。
  - sidecar 人工处理事件不会再追加误导性的 completed 事件。
- 验证结果：
  - Windows PowerShell：`py -3 -m unittest discover -s tests`，55 tests passed。
  - Windows PowerShell：`py -3 -m compileall falcon`，passed。
  - 旧采集路径关键词静态扫描无匹配。
- 已知问题：
  - 真实小红书人工 smoke 未在本次无人值守收口中执行；需要先在 `sidecar/collector` 安装 npm 依赖和 Chromium，并准备本地 profile 登录态后再跑 `collector-run`。
  - 小红书真实 adapter 仍是 MVP skeleton，首次 live evidence 回来后需要按页面 DOM 调整卡片、详情、评论和媒体字段提取。
  - 当前 Web 创建任务只准备 request，不自动启动 sidecar；下一步需要加 worker 调度或手动启动入口。
- 下一步：
  - 在 Windows 或 Mac 安装 sidecar 依赖后执行：`py -3 -m falcon --db data/falcon.sqlite3 collector-run --platform xiaohongshu --profile default --keyword "小红书封面" --max-posts 5`。
  - 用任务详情页核对事件链、截图证据和样本字段，再从 `/analysis` 手动送入分析队列。
  - 根据 live evidence 补强详情页、热评、图片下载和失败截图的字段覆盖。
  - 为 worker/profile 管理补后台调度与取消能力，但保持最终发布、评论、私信为人工确认。
- Windows/Mac 接手提示：
  - `git pull`
  - Windows：`py -3 -m unittest discover -s tests`
  - macOS：`python3 -m unittest discover -s tests`
  - 如需真实采集，先按 `docs/development-guide.md` 安装 `sidecar/collector` 的 Node 依赖。

## 2026-05-23 Falcon Agent reboot branch

- 新建分支：`codex/falcon-agent-reboot`。
- 当前目标：清空旧采集路线，把仓库收束到 Falcon Agent 自有浏览器采集、AI 分析、内容生成和人工确认执行的未来架构。
- 已删除旧外部采集路线：
  - 外部工作流构建器资料、截图、工作流记录和运行手册。
  - 旧 XLSX/CSV adapter、日常运行命令和测试。
  - Codex 会话采集指南、平台草稿和 JavaScript helper。
  - 旧采集原型和旧 dashboard 原型。
- 已更新项目叙事：
  - `README.md` 改为 Falcon Agent reboot 说明。
  - `AGENTS.md` 明确 Codex 只是开发助手，不是产品运行时采集机制。
  - `project.md` 改为 Agent 重构方案。
  - `docs/development-guide.md` 移除旧采集命令，保留跨平台基线验证和当前 smoke workflow。
- 已更新代码入口：
  - 移除旧导入和日常运行 CLI。
  - 保留数据库、分析、日报、GPT-5.5、Image2、关键词计划、Web 工作台外壳、复核和任务队列。
  - Web 工作台移除旧执行入口。

## 当前状态

- 仓库远端：`ssh://git@ssh.github.com:443/unolfssrebecenholt-ops/Falcon.git`
- 当前分支：`codex/falcon-agent-reboot`
- 当前阶段：Agent 重构起点。旧采集路线已从当前分支清理，下一步开始设计并实现 Falcon 自有 Browser Collector。
- 技术形态：Python + FastAPI + Jinja + SQLite + GPT-5.5 relay + Image2 relay。
- 项目必须保持 Windows 和 macOS 双端可运行。
- 采集层设计原型已新增到 `docs/design/`：
  - `falcon-collector-workbench.html`：第一版采集工作台方向稿。
  - `falcon-collector-workbench-v2.html`：更细的采集中心原型，包含多平台入口、小红书任务配置、Node Playwright sidecar 运行链路、任务进度、当前步骤、步骤链路、完整日志链、证据包、账号锁和人工恢复点。
  - `falcon-collector-workbench-v3.html`：拆分采集总览、任务创建、任务详情、分析总览、执行总览五个独立视图。采集总览负责多任务队列、平台入口、Worker/Profile 状态和三层流转；创建页只负责配置平台、账号、关键词、范围、节奏和产物预估；详情页只负责单个 run 的进度、步骤链、日志链、证据和恢复点；分析层承接采集样本生成需求、痛点、内容结构、评论意向和草稿 briefing；执行层展示发布/评论/私信/素材预览队列，并强调最终动作必须人工确认。左侧导航已按采集、分析、执行三个业务责任域分组，并收敛为真实页面入口，避免同一页面出现多个子目录。

## 保留能力

- SQLite 数据中枢。
- 启发式意图评分。
- GPT-5.5 OpenAI 兼容中转站客户端。
- Image2 OpenAI 兼容生图客户端和架构图生成命令。
- Markdown 日报。
- 本地 Web 工作台外壳。
- 关键词计划工具。
- 人工复核记录。
- 触达任务队列和状态更新。

## 已清理能力

- 外部工作流构建器记录和资料。
- 旧导入 adapter。
- 旧 daily run workflow。
- Codex 会话采集指南和 helper。
- 旧示例 CSV 和旧导入命令。
- 旧原型中关于外部采集流程的页面。

## 下一步建议

1. 写 Falcon Browser Collector 设计文档，明确运行时、平台 adapter、数据模型、资产目录、暂停/恢复、失败状态和测试边界。
2. 基于 `docs/design/falcon-collector-workbench-v3.html` 确认采集中心页面信息架构，然后把设计沉淀为小红书 collector 技术设计。
3. 第一阶段只做小红书 collector，不先扩多平台；抖音、微博、闲鱼只保留入口和配置占位。
4. 新增 normalized collection models：collection run、post、comment、media asset、metric、author、evidence。
5. 实现本地 asset store，产物放入 ignored runtime 目录。
6. 实现去重模块：点击前弱过滤，详情后强指纹。
7. 接入 Web 工作台：采集任务状态、采集结果、人工复核和分析入口。
8. 稳定后再做执行预览：打开页面、填内容、上传素材、等待人工确认。

## 验证记录

最近一次验证：

```powershell
py -3 -m unittest discover -s tests
```

结果：

- 2026-05-23 Windows PowerShell：29 tests passed.
- `python -m compileall falcon` passed.
- `docs/design/falcon-collector-workbench-v2.html` 静态结构检查通过：主要 HTML 标签数量成对；旧采集/外部工作流关键词扫描未发现回流。
- `docs/design/falcon-collector-workbench-v3.html` 静态结构检查通过：主要 HTML 标签数量成对；未发现旧采集/外部工作流关键词回流；已加入采集层、分析层、执行层整体入口，并把左侧导航调整为采集/分析/执行分组目录。最新版本已收敛重复子目录，采集页上半区放任务规模、平台入口和三层流转，下半区放任务队列、Worker/Profile 和操作入口。
- Codex in-app Browser 对本地 `file://` 原型导航触发 URL policy 阻止；本机 Edge headless 已生成 `docs/design/falcon-collector-workbench-v3-sidebar.png` 作为左侧导航和采集总览预览，可手动在浏览器刷新 `file:///F:/projects/Falcon/docs/design/falcon-collector-workbench-v3.html` 查看最新拆分版。

## Windows 接手提示

```powershell
git pull
git switch codex/falcon-agent-reboot
py -3 -m unittest discover -s tests
```

然后：

1. 读 `README.md`、`project.md` 和本文件。
2. 不要恢复已删除的旧外部采集资料。
3. 继续从 Falcon Browser Collector 设计开始。

## Mac 接手提示

```bash
git pull
git switch codex/falcon-agent-reboot
python3 -m unittest discover -s tests
```

然后：

1. 读 `README.md`、`project.md` 和本文件。
2. 不要恢复已删除的旧外部采集资料。
3. 继续从 Falcon Browser Collector 设计开始。
