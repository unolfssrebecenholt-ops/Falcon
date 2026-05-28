# Falcon 当前交接快照

本文件只保留当前可继续开发所需的信息。历史实现流水账、已执行计划和过时原型已经从仓库清理；需要追溯细节时使用 Git history。

## 2026-05-28 Falcon layout redesign v3 production application

- 已把用户确认的 v3 no-purple 视觉方向应用到生产 Web 工作台：
  - `falcon/web/templates/base.html` 改为 v3 shell：sticky topbar、深青左侧导航、分组层级、`prototype-shell` / `workspace-frame` / `page family-*` 内容框架。
  - `falcon/web/templates/dashboard.html` 改为原型同款 compact status header：H1 为 `仪表盘`，eyebrow 为 `workspace entry`，主操作为 `初始化数据库` 和 `整理采集计划`。
  - `falcon/web/static/app.css` 切到浅青灰玻璃主题、青蓝主色和少量琥珀状态色，并保留生产页面的表格、队列、账号、分析等业务组件规则。
  - `falcon/web/static/app.css` 追加 collector scoped v3 浅玻璃覆盖，修复旧后置业务样式把采集首页状态卡、焦点卡、平台卡、健康指标和最近任务刷回深灰的问题。
  - `tests/test_web_app.py` 更新为 v3 视觉契约：无紫粉禁用色、v3 cache bust、sticky shell、compact H1、仪表盘新文案。
- 视觉验证：
  - 桌面 `1280x720`：真实 `http://127.0.0.1:8765/` 无横向溢出，H1 17px，topbar/sidebar 为 sticky。
  - 移动 `390x844`：修复初版横向导航撑宽页面的问题；文档宽度回到视口内，导航作为横向滚动轨道保留。
- 设计资产清理：
  - 已删除过时的 `docs/design/falcon-layout-redesign-v1/`、`docs/design/falcon-layout-redesign-v2/`、本地未跟踪 `docs/design/falcon-layout-redesign-v3-no-purple/` 和一次性色彩预览图。
  - 当前生产应用只依赖 `falcon/` 下模板和 CSS；旧原型需要追溯时使用 Git history。

## 2026-05-29 Prototype cleanup and GitHub handoff

- 删除过时设计原型和截图资产：
  - 已从 Git 移除 `docs/design/falcon-layout-redesign-v1/` 和 `docs/design/falcon-layout-redesign-v2/`。
  - 已清理本机未跟踪的 `docs/design/falcon-layout-redesign-v3-no-purple/` 和旧色彩预览图，避免把原型截图批次继续带入仓库。
  - `docs/design/README.md` 改为说明当前视觉以生产 Web 模板和 CSS 为准，旧视觉方向通过 Git history 追溯。
- 同步文档引用：
  - `README.md` 和 `docs/development-guide.md` 不再指向已删除的原型目录。
  - 本次提交后另一台机器拉取即可直接使用生产 Web 工作台，不需要本地原型目录。

## 2026-05-28 Repository cleanup and stable handoff

- 本次目标是把仓库整理成更干净、可稳定继续开发的状态：
  - 删除已执行的历史计划文档目录。
  - 删除过时设计原型和截图批次，当前视觉以生产模板和 CSS 为准。
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
- `docs/design/README.md`：说明历史原型已清理，当前视觉以生产 Web 模板和 CSS 为准。

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
- 2026-05-28 Windows production v3 application:
  - `py -3 -m unittest tests.test_web_app`：91 tests passed。
  - `py -3 -m unittest discover -s tests`：209 tests passed。
  - `py -3 -m compileall falcon`：passed。
  - `git diff --check`：passed。
  - Browser check `http://127.0.0.1:8765/` desktop `1280x720`：无横向溢出，H1 `17px`，topbar/sidebar sticky。
  - Browser check mobile `390x844`：document width equals viewport width，导航横向滚动不撑破页面。
  - Collector browser style check `http://127.0.0.1:8765/collector`：`.status-cell`、`.focus-item`、`.platform-card`、`.health-metrics div`、`.health-action`、`.recent-run-item` computed backgrounds 已回到浅色 v3 glass palette。
- 2026-05-29 Windows prototype cleanup and GitHub handoff:
  - `py -3 -m unittest discover -s tests`：210 tests passed。
  - `py -3 -m compileall falcon`：passed。
  - `git diff --check`：passed（仅 Windows CRLF 提示）。
  - `rg` secret scan：仅命中代码中的环境变量读取名，未发现真实 API key。

## Windows/Mac 接手说明

- 开始工作：
  - macOS: `git pull && python3 -m unittest discover -s tests`
  - Windows: `git pull; py -3 -m unittest discover -s tests`
- 启动工作台：
  - macOS: `./scripts/start.sh --skip-install`
  - Windows: `.\scripts\start.ps1 --skip-install`
- 如果是全新机器，去掉 `--skip-install` 让启动脚本安装 Python package、Node sidecar 依赖和 Playwright Chromium。
