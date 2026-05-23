# Falcon 项目进度

本文件是 Windows 和 M1 Mac 双机开发的接手入口。每次提交前必须更新。

## 2026-05-23 Collector task lifecycle and local sample preview

- 本次优化采集任务生命周期展示：
  - `/collector` 任务队列新增开启时间、运行时长、资源占用和操作列。
  - `manual_action_required` 在页面上显示为“需人工处理”，阶段显示“已暂停”，资源占用显示“无占用”，避免误解为仍在运行或占用浏览器资源。
  - 新增任务操作：重新运行、标记失败、归档。重新运行会基于原任务创建新的 queued run 并准备 request；标记失败和归档会写回状态并追加事件链记录。
  - `/collector/runs/{run_id}` 详情页同步显示阶段、开启时间、运行时长、资源占用和同样的任务操作。
- 本次优化时间和样本查看：
  - 任务详情事件链时间改为可读上海时间，例如 `2026-05-23 16:14:07`。
  - 采集样本标题不再直接链接小红书 URL，改为进入 Falcon 本地样本预览页 `/collector/runs/{run_id}/posts/{post_id}`。
  - 本地预览页展示标题、作者、正文、互动数、原始平台地址文本、热评和媒体资产；原始小红书 URL 只作为文本展示，避免点击外链触发平台风控。
- 验证结果：
  - `py -3 -m unittest discover -s tests`：79 tests passed。
  - `py -3 -m compileall falcon`：passed。
  - 旧关键词扫描无命中。
  - 浏览器检查 `http://127.0.0.1:8765/collector` 和任务详情/样本预览：无横向溢出；本地样本链接正常；详情页不包含小红书外链锚点。
- 已知问题：
  - 归档当前复用内部状态 `cancelled` 存储，Web 显示为“已归档”。后续如果需要更细的审计状态，可以在 schema 中新增独立 archived 状态。
- 下一步：
  - 为“需人工处理”任务增加更明确的恢复流程，例如扫码后点击“继续采集”而不是只能“重新运行”。

## 2026-05-23 Xiaohongshu adapter hardening and Chinese collector UI

- 本次加固小红书采集 adapter：
  - 新增 `sidecar/collector/xiaohongshu-normalize.mjs`，统一处理小红书笔记 URL 归一、`/explore/<id>` 与 `/search_result/<id>` 去重、标题/作者/日期/点赞字段清洗。
  - 真实模式不再只保存图片 URL 占位 JSON；详情页可浏览时会下载真实图片文件，保存 `mime_type`、`sha256` 和本地路径。
  - 采集流程从搜索页进入详情页，尝试读取详情正文、作者、互动数和热评；遇到登录、风控、验证码或“小红书 App 扫码查看”时写入 `manual_action_required` 并停止自动操作。
  - 搜索页和详情页都会保存截图与字段快照，方便排查 DOM 变化和平台限制。
- 本次清理 Web 展示：
  - `/collector`、`/collector/runs/{run_id}` 不再直出 `completed`、`run_completed`、`info`、`sidecar completed` 等内部词汇，统一映射为中文状态、事件、级别和步骤。
  - 创建任务页移除示例式关键词 placeholder，避免把设计阶段示例误看成真实数据。
  - 多平台入口保留，但状态改为“当前开发 / 待接入”，避免“占位”语义像假数据。
- 验证结果：
  - `py -3 -m unittest discover -s tests`：75 tests passed。
  - `py -3 -m compileall falcon`：passed。
  - `node --check sidecar\collector\index.mjs; node --check sidecar\collector\xiaohongshu.mjs; node --check sidecar\collector\xiaohongshu-normalize.mjs`：passed。
  - 浏览器检查 `http://127.0.0.1:8765/collector`：无横向溢出；总览和详情页中文状态/事件展示正常；未发现 demo/mock/Dry-run sample 展示内容。
  - 真实 smoke：`collector-run --platform xiaohongshu --profile default --keyword "小红书封面" --max-posts 1 --max-comments-per-post 1` 能进入搜索页并识别笔记，但详情页被小红书提示“当前笔记暂时无法浏览，请打开小红书 App 扫码查看”，任务正确进入“等待人工”状态并保存截图证据。
- 已知问题：
  - 当前账号在 Web 详情页被小红书要求 App 扫码查看，因此详情正文、热评和真实图片下载的完整落库路径还需要扫码解除后再跑一次 smoke 验证。
  - 旧 run 中已经落库的早期 MVP 记录不会被自动重写；新 run 会走新的清洗和去重逻辑。
- 下一步：
  - 用户在弹出的详情页扫码通过后，重新运行 `collector-run --max-posts 5 --max-comments-per-post 3`，验证详情正文、热评和真实图片下载。
  - 加一个 Web 入口用于从任务详情页继续/重试等待人工的任务，减少命令行操作。
- Windows/Mac 接手说明：
  - Windows：`git pull` 后运行 `.\scripts\start.ps1 --skip-install`，打开 `/collector`。
  - macOS：`git pull` 后运行 `./scripts/start.sh --skip-install`，再用同名 profile 重新登录小红书。

## 2026-05-23 Profile login workspace

- 本次新增采集层 Profile 登录工作区：
  - `/collector` 增加 `平台账号 / Profile` 面板，按 `platform/profile` 展示账号键、本地目录、状态、任务锁和操作入口。
  - 支持从 Web 直接打开小红书 profile 登录窗口，登录态保存到 `browser-profiles/xiaohongshu/<profile>/`，不进入 Git。
  - Profile 管理按多账号、多平台、多任务设计：同一 `platform/profile` 后续作为串行任务锁粒度，不同 profile 可作为未来并行调度粒度。
  - 其他平台保留入口但暂不允许启动登录窗口，避免把未实现 adapter 误认为可运行。
  - 新增 `sidecar/collector/profile-login.mjs`，只负责打开持久化 Playwright profile 浏览器窗口，不采集、不读取验证码、不保存账号密码。
- 验证结果：
  - 新增 Web 单测覆盖 Profile 面板展示、支持平台启动、未接入平台和非法 profile 拒绝。
  - `py -3 -m unittest discover -s tests`：72 tests passed。
  - `py -3 -m compileall falcon`：passed。
  - `node --check sidecar\collector\profile-login.mjs`：passed。
  - 浏览器检查 `/collector` 窄窗口无横向溢出，Profile 表格已转为字段式展示。
- 下一步：
  - 用户在 `/collector` 里点击 `打开登录窗口`，完成 `xiaohongshu/default` 登录后，跑一次 `collector-run --max-posts 5` 人工 smoke。

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

### 2026-05-23 Environment doctor UI refinement

- 本次继续优化 `/collector` 环境自检区：
  - 环境自检面板改为可收纳结构，点击标题区可展开或收起完整依赖明细。
  - 必要依赖全部就绪时默认收起，保留 READY、就绪数量、必要异常、可选提醒和本机状态摘要。
  - 如果出现必要异常，面板默认展开，方便第一时间看到处理命令和路径 / 版本信息。
  - 已用 Web 单测覆盖默认展开 / 默认收起两种状态，并用浏览器点击验证展开收起交互。
- 根据采集总览页面反馈，重设计 `/collector` 的环境自检区域：
  - 从卡片墙改为运维清单布局，明确展示状态、组件、作用、路径 / 版本、处理命令。
  - 每个 doctor 检查项补充用途说明，便于判断该依赖影响采集链路的哪一段。
  - 顶部增加 READY / ACTION 状态、就绪计数、必要异常、可选提醒和本机状态。
  - 桌面端保持高密度表格，移动端改为纵向字段，避免路径和命令横向撑破页面。
- 验证结果：
  - Web 单测覆盖环境自检新文案与 Node Playwright sidecar 作用说明。
  - Playwright 截图检查桌面端无页面横向溢出；移动端 `bodyScrollWidth == bodyClientWidth`。

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
