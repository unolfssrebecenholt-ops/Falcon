# Falcon 项目进度

本文件是 Windows 和 M1 Mac 双机开发的接手入口。每次提交前必须更新。

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
