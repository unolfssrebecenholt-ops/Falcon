/*
Assumptions:
- This prototype is a design review artifact only. It does not call Falcon routes,
  mutate production templates, or depend on runtime data.
- Content mirrors the current Falcon business components: collector runs, profiles,
  evidence, samples, analysis, review, execution drafts, keyword pool, and report.
- The main design question is layout proportion and page grouping, not a new theme.
*/

const pages = [
  { id: "dashboard", file: "01-dashboard.html", label: "仪表盘", group: "工作台", badge: "HOME", width: "" },
  { id: "collector-home", file: "02-collector-home.html", label: "采集首页", group: "采集", badge: "TODAY", width: "" },
  { id: "collector-runs", file: "03-collector-runs.html", label: "任务队列", group: "采集", badge: "RUNS", width: "wide" },
  { id: "collector-create", file: "04-collector-create.html", label: "任务创建", group: "采集", badge: "NEW", width: "" },
  { id: "collector-accounts", file: "05-collector-accounts.html", label: "账号管理", group: "采集", badge: "PROFILE", width: "wide" },
  { id: "collector-environment", file: "06-collector-environment.html", label: "环境自检", group: "采集", badge: "CHECK", width: "wide" },
  { id: "collector-run-detail", file: "07-collector-run-detail.html", label: "任务详情", group: "采集", badge: "DETAIL", width: "wide" },
  { id: "collector-sample-preview", file: "08-collector-sample-preview.html", label: "样本预览", group: "采集", badge: "MEDIA", width: "wide" },
  { id: "keywords", file: "09-keywords.html", label: "关键词池", group: "基础", badge: "PLAN", width: "" },
  { id: "report", file: "10-report.html", label: "日报", group: "基础", badge: "DOC", width: "doc" },
  { id: "analysis-home", file: "11-analysis-home.html", label: "分析首页", group: "分析", badge: "INSIGHT", width: "" },
  { id: "analysis-samples", file: "12-analysis-samples.html", label: "分析样本", group: "分析", badge: "SAMPLES", width: "wide" },
  { id: "review", file: "13-review.html", label: "人工复核", group: "分析", badge: "REVIEW", width: "wide" },
  { id: "execution-home", file: "14-execution-home.html", label: "执行首页", group: "执行", badge: "DRAFT", width: "" },
  { id: "tasks", file: "15-tasks.html", label: "触达任务", group: "执行", badge: "TASKS", width: "wide" },
];

const byId = Object.fromEntries(pages.map((page) => [page.id, page]));

const runs = [
  ["xiaohongshu-20260524-090257", "小红书 / default", "AI头像", "completed", "已完成", "2026-05-24 09:02", "5 / 23 / 34", "查看"],
  ["xiaohongshu-20260524-101840", "小红书 / creator", "小红书封面", "manual", "需人工", "2026-05-24 10:18", "8 / 18 / 12", "继续采集"],
  ["xiaohongshu-20260524-103312", "小红书 / backup", "AI写真提示词", "running", "运行中", "2026-05-24 10:33", "3 / 9 / 8", "运行中"],
  ["xiaohongshu-20260524-104500", "小红书 / default", "头像小程序", "queued", "待启动", "2026-05-24 10:45", "0 / 0 / 0", "启动采集"],
  ["xiaohongshu-20260524-082044", "小红书 / default", "生图头像", "failed", "失败", "2026-05-24 08:20", "2 / 4 / 6", "重新运行"],
  ["xiaohongshu-20260523-224112", "小红书 / creator", "AI证件照", "completed", "已完成", "2026-05-23 22:41", "12 / 40 / 56", "查看"],
  ["xiaohongshu-20260523-214120", "小红书 / default", "封面设计", "completed", "已完成", "2026-05-23 21:41", "10 / 34 / 42", "查看"],
  ["xiaohongshu-20260523-180010", "小红书 / creator", "爆款标题", "queued", "待启动", "2026-05-23 18:00", "0 / 0 / 0", "启动采集"],
];

const profiles = [
  ["小红书", "default", "已登录", "ready", "空闲", "14", "登录", "检查", "退出"],
  ["小红书", "creator", "需人工", "manual", "等待扫码", "6", "登录", "检查", "退出"],
  ["小红书", "backup", "运行中", "running", "xiaohongshu-103312", "3", "登录", "检查", "退出"],
  ["抖音", "default", "待接入", "idle", "未启用", "0", "登录", "检查", "退出"],
  ["微博", "default", "待接入", "idle", "未启用", "0", "登录", "检查", "退出"],
  ["闲鱼", "shop-a", "待接入", "idle", "未启用", "0", "登录", "检查", "退出"],
];

const samples = [
  ["65", "AI头像怎么做才不像模板？", "AI头像", "小鹿同学", "0.91", "头像真实感 / 可复用提示词", "预览"],
  ["66", "封面字太乱，怎么一眼高级", "小红书封面", "麦麦", "0.84", "封面层级 / 标题留白", "预览"],
  ["67", "证件照风格一直崩", "AI证件照", "花园计划", "0.81", "身份照可信度", "预览"],
  ["68", "头像小程序是不是都长一样", "头像小程序", "Rita", "0.78", "差异化模板", "预览"],
  ["69", "评论区求提示词集合", "AI写真提示词", "海盐", "0.76", "提示词包需求", "预览"],
  ["70", "为什么生成封面不适合小红书", "封面设计", "风铃", "0.73", "平台尺寸和裁切", "预览"],
  ["71", "AI头像商用会不会侵权", "AI头像", "K先生", "0.70", "版权与肖像", "预览"],
];

const envChecks = [
  ["OK", "Python", "FastAPI/Jinja 工作台和 CLI", "Python 3.12.4", "-"],
  ["OK", "Node.js", "collector sidecar", "v22.11.0", "-"],
  ["OK", "Playwright package", "真实浏览器采集", "sidecar/collector/node_modules", "npm install"],
  ["OK", "Chromium", "持久化 profile 登录窗口", "已安装", "npx playwright install chromium"],
  ["OK", "runtime/collector", "事件、记录、资产目录", "F:/projects/Falcon/runtime/collector", "-"],
  ["WARN", "GPT-5.5 relay", "分析和草稿生成", "可选环境变量未配置", "设置 FALCON_GPT_*"],
  ["WARN", "Image2 relay", "封面和配图生成", "可选环境变量未配置", "设置 FALCON_IMAGE2_*"],
];

function cls(value) {
  return value ? ` ${value}` : "";
}

function button(text, kind = "ghost") {
  return `<a class="button${cls(kind)}" href="#">${text}</a>`;
}

function status(text, kind = "idle") {
  return `<span class="status ${kind}">${text}</span>`;
}

function metric(label, value, note = "") {
  return `<div class="metric"><span>${label}</span><strong>${value}</strong>${note ? `<small>${note}</small>` : ""}</div>`;
}

function metricRow(items) {
  return `<section class="metric-row">${items.map((item) => metric(...item)).join("")}</section>`;
}

function panel(title, subtitle, body, side = "") {
  return `<section class="panel">
    <div class="section-head"><div><h2>${title}</h2>${subtitle ? `<p>${subtitle}</p>` : ""}</div>${side}</div>
    ${body}
  </section>`;
}

function facts(items, columns = 2) {
  return `<div class="facts columns-${columns}">${items.map(([label, value]) => `<div class="fact"><span>${label}</span><strong>${value}</strong></div>`).join("")}</div>`;
}

function table(headers, rows, opts = "") {
  const body = Array.isArray(rows) ? rows.join("") : rows;
  return `<div class="table-wrap${cls(opts)}"><table><thead><tr>${headers.map((head) => `<th>${head}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function runRows(source = runs) {
  return source.map((run) => `<tr>
    <td><div class="cell-main"><strong>${run[0]}</strong><small>${run[1]}</small></div></td>
    <td><div class="cell-main"><strong>${run[2]}</strong><small>帖子 / 评论 / 资产：${run[6]}</small></div></td>
    <td>${status(run[4], run[3])}</td>
    <td>${run[5]}</td>
    <td><div class="inline-actions">${button(run[7], run[7] === "继续采集" || run[7] === "启动采集" ? "primary" : "ghost")}${button("归档")}</div></td>
  </tr>`).join("");
}

function bars(items) {
  return `<div class="mini-bars">${items.map(([label, value, width, color = "var(--accent)"]) => `<div class="bar"><span>${label}</span><div class="bar-track"><span style="width:${width}%;background:${color}"></span></div><strong>${value}</strong></div>`).join("")}</div>`;
}

function ledgerRows(rows) {
  return rows.map((row) => `<article class="ledger-row"><span class="tag">${row[0]}</span><div><strong>${row[1]}</strong><p>${row[2]}</p></div><small>${row[3]}</small><small>${row[4]}</small></article>`).join("");
}

function renderLedger(title, subtitle, headers, rows, asset = false) {
  return panel(title, subtitle, `<div class="ledger${asset ? " asset" : ""}">
    <div class="ledger-head">${headers.map((head) => `<span>${head}</span>`).join("")}</div>
    <div class="ledger-body">${ledgerRows(rows)}</div>
  </div>`, `<span class="pill">显示 7 条</span>`);
}

function pageHeader(meta, actions = []) {
  return `<header class="page-header">
    <div><div class="eyebrow">${meta.eyebrow}</div><h1>${meta.title}</h1><p>${meta.desc}</p></div>
    <div class="actions">${actions.join("")}</div>
  </header>`;
}

function renderShell(pageId, content) {
  const active = byId[pageId];
  const groups = ["工作台", "采集", "分析", "执行", "基础"];
  const nav = groups.map((group) => `<section class="nav-section">
    <div class="nav-title"><span>${group}</span><span>${group === "采集" ? "LIVE" : "LOCAL"}</span></div>
    ${pages.filter((page) => page.group === group).map((page) => `<a class="nav-link${page.id === pageId ? " active" : ""}" href="${page.file}"><span>${page.label}</span><span class="nav-count">${page.badge}</span></a>`).join("")}
  </section>`).join("");
  return `<div class="prototype-shell">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">F</span><div><strong>Falcon</strong><small>Layout prototype</small></div></div>
      <div class="nav-section-wrap">${nav}</div>
    </aside>
    <main class="main"><div class="page${cls(active.width)}">${content}</div></main>
  </div>`;
}

const templates = {
  dashboard() {
    const meta = {
      eyebrow: "workspace entry",
      title: "仪表盘",
      desc: "只作为工作台入口和关键待办，不再铺满一屏空面板。常用动作向采集、分析、执行三条链路分流。",
    };
    return pageHeader(meta, [button("初始化数据库"), button("整理采集计划", "primary")]) +
      metricRow([
        ["样本总数", "128", "本机 SQLite"],
        ["待人工", "2", "登录 / 风控"],
        ["高意图", "37", "分析后样本"],
        ["待确认", "9", "草稿执行队列"],
      ]) +
      `<section class="layout-grid">
        ${panel("今日待办", "只保留可行动项，入口不展示完整长表。", `<div class="stack">
          <div class="thin-card"><h3>小红书 creator 需要处理登录态</h3><p>任务 xiaohongshu-20260524-101840 暂停在详情页扫码。</p><div class="inline-actions">${button("打开账号管理", "primary")}${button("查看任务")}</div></div>
          <div class="thin-card"><h3>3 个 queued run 可启动</h3><p>default profile 空闲，可以串行启动 AI头像 / 头像小程序任务。</p><div class="inline-actions">${button("进入任务队列", "primary")}</div></div>
          <div class="thin-card"><h3>7 条高价值样本待复核</h3><p>从分析结果进入复核工作台，逐条确认“优秀 / 有用 / 噪音”。</p><div class="inline-actions">${button("开始复核")}</div></div>
        </div>`)}
        <div class="stack">
          ${panel("链路入口", "按职责归类，不在首页重复展示表格。", `<div class="facts columns-2">
            <div class="fact"><span>采集</span><strong>首页 / 队列 / 创建 / 账号 / 自检</strong></div>
            <div class="fact"><span>分析</span><strong>趋势 / 样本 / 复核</strong></div>
            <div class="fact"><span>执行</span><strong>草稿入口 / 触达任务</strong></div>
            <div class="fact"><span>基础</span><strong>关键词池 / 日报</strong></div>
          </div>`)}
          ${panel("最近日报", "文档入口只展示摘要和打开动作。", `<div class="callout">2026-05-24 日报已生成，包含 AI头像、封面设计、证件照三个主题的高价值样本和可写选题。</div><div class="inline-actions" style="margin-top:10px">${button("阅读日报", "primary")}${button("重新生成")}</div>`)}
        </div>
      </section>`;
  },

  "collector-home"() {
    const meta = {
      eyebrow: "collector home",
      title: "采集首页",
      desc: "首页只看本机状态、今日概况、待处理焦点和最近任务入口。配置、队列、账号、自检拆到独立页面。",
    };
    return pageHeader(meta, [button("任务队列"), button("创建任务", "primary")]) +
      metricRow([
        ["本机状态", "可采集", "必要依赖就绪"],
        ["今日任务", "8", "3 完成 / 2 阻塞"],
        ["采集样本", "46", "含 34 个媒体资产"],
        ["待人工", "2", "扫码或风控"],
      ]) +
      `<section class="layout-grid">
        ${panel("待处理焦点", "可立即处理的 run 放在首页，不把完整任务表塞进来。", `<div class="stack">
          <div class="thin-card"><h3>creator profile 需要扫码</h3><p>小红书封面 run 暂停于详情页提示，需要打开处理窗口后继续。</p><div class="inline-actions">${button("打开处理窗口", "primary")}${button("任务详情")}</div></div>
          <div class="thin-card"><h3>1 个失败任务可重新入队</h3><p>生图头像 run 保存了错误截图，建议重新运行新任务。</p><div class="inline-actions">${button("重新运行")}${button("查看证据")}</div></div>
          <div class="thin-card"><h3>3 个任务等待启动</h3><p>default profile 空闲；backup 正在运行，按 profile 串行调度。</p><div class="inline-actions">${button("启动队列", "primary")}</div></div>
        </div>`)}
        <div class="stack">
          ${panel("采集入口", "功能入口按页面拆开，首页不承载表单。", `<div class="facts columns-2">
            <div class="fact"><span>任务队列</span><strong>筛选、批量、单项操作</strong></div>
            <div class="fact"><span>任务创建</span><strong>平台、账号、关键词、节奏</strong></div>
            <div class="fact"><span>账号管理</span><strong>Profile 登录 / 检查 / 退出</strong></div>
            <div class="fact"><span>环境自检</span><strong>依赖、路径、运行配置</strong></div>
          </div>`)}
          ${panel("最近任务", "只展示最近 4 条，完整列表去任务队列。", table(["Run", "关键词", "状态", "动作"], runs.slice(0, 4).map((run) => `<tr><td><div class="cell-main"><strong>${run[0]}</strong><small>${run[1]}</small></div></td><td>${run[2]}</td><td>${status(run[4], run[3])}</td><td>${button(run[7])}</td></tr>`).join(""), ""))}
        </div>
      </section>`;
  },

  "collector-runs"() {
    const meta = {
      eyebrow: "collector runs",
      title: "任务队列",
      desc: "独立承载筛选器、批量操作、任务表格和单项操作；表格可更宽，但行高保持紧凑。",
    };
    return pageHeader(meta, [button("批量启动"), button("创建任务", "primary")]) +
      `<section class="panel tight">
        <div class="filters">
          <div class="field compact"><label>平台</label><select><option>全部平台</option><option>小红书</option><option>抖音</option></select></div>
          <div class="field compact"><label>状态</label><select><option>全部状态</option><option>待启动</option><option>需人工</option><option>失败</option></select></div>
          <div class="field medium"><label>日期范围</label><input value="2026-05-23 至 2026-05-24"></div>
          <div class="field medium"><label>关键词</label><input value="AI头像"></div>
          ${button("筛选", "primary")}
        </div>
        ${table(["Run / Profile", "平台 / 关键词", "状态", "开启时间", "操作"], [runRows()], "")}
      </section>`;
  },

  "collector-create"() {
    const meta = {
      eyebrow: "collector create",
      title: "任务创建",
      desc: "独立表单页按平台、账号、关键词、采样范围和节奏分组。输入区按内容定宽，不做满屏大块。",
    };
    return pageHeader(meta, [button("返回队列"), button("加入队列", "primary")]) +
      `<section class="layout-grid reverse">
        <div class="stack">
          ${panel("入队摘要", "表单旁边只保留必要核对项。", facts([
            ["平台", "小红书 / xiaohongshu"],
            ["Profile", "default"],
            ["关键词组", "AI头像 / 小红书封面 / AI证件照"],
            ["任务拆分", "3 个独立 queued run"],
            ["采样范围", "20 帖 / 每帖 10 评论"],
            ["执行策略", "入队后手动或队列 worker 启动"],
          ], 2))}
          ${panel("节奏与限制", "控制采集强度，避免被埋在巨大表单里。", `<div class="form-grid">
            <div class="field compact"><label>最大帖子数</label><input value="20"></div>
            <div class="field compact"><label>每帖评论数</label><input value="10"></div>
            <div class="field compact"><label>滚动节奏</label><select><option>低频稳妥</option></select></div>
            <div class="field compact"><label>失败策略</label><select><option>暂停等待人工</option></select></div>
          </div>`)}
        </div>
        ${panel("任务参数", "平台和 Profile 先定，关键词支持标签化拆分。", `<div class="form-grid">
          <div class="field full"><div class="field-title">平台</div><div class="option-grid">
            <div class="option-card selected"><strong>小红书 ${status("当前开发", "ready")}</strong><p>关键词搜索、瀑布流快照、详情页证据、人工恢复。</p></div>
            <div class="option-card"><strong>抖音 ${status("待接入", "idle")}</strong><p>保留入口，不允许误判为可运行。</p></div>
            <div class="option-card"><strong>微博 ${status("待接入", "idle")}</strong><p>后续平台 adapter 接入后启用。</p></div>
          </div></div>
          <div class="field"><label>Profile</label><select><option>default</option><option>creator</option><option>backup</option></select><span class="subtext">只能选择账号管理里已有的 Profile。</span></div>
          <div class="field"><label>任务标签</label><input value="头像增长素材"></div>
          <div class="field full"><label>关键词组</label><div class="chips"><span class="chip">AI头像</span><span class="chip">小红书封面</span><span class="chip">AI证件照</span></div><input style="margin-top:8px" placeholder="输入关键词，按 Enter 或逗号添加"></div>
        </div>`)}
      </section>`;
  },

  "collector-accounts"() {
    const meta = {
      eyebrow: "profile command",
      title: "账号管理",
      desc: "平台用户矩阵保留，但减弱大卡片感。每行明确用户状态、任务锁和登录 / 检查 / 退出操作。",
    };
    return pageHeader(meta, [button("返回采集首页"), button("新建 Profile", "primary")]) +
      metricRow([
        ["平台", "4", "小红书可运行"],
        ["用户/Profile", "6", "本机环境"],
        ["本机目录", "3", "已创建"],
        ["运行占用", "1", "backup"],
      ]) +
      panel("平台用户矩阵", "创建多个用户就是新增 platform/profile，本机目录隔离登录态。", table(
        ["平台", "Profile / 本机目录", "用户状态", "任务锁", "历史任务", "操作"],
        profiles.map((item) => `<tr>
          <td>${item[0]}</td>
          <td><div class="cell-main"><strong>${item[1]}</strong><small>browser-profiles/${item[0]}/${item[1]}</small></div></td>
          <td>${status(item[2], item[3])}</td>
          <td>${item[4]}</td>
          <td>${item[5]}</td>
          <td><div class="inline-actions">${button(item[6], item[3] === "idle" ? "disabled" : "ghost")}${button(item[7], item[3] === "idle" ? "disabled" : "primary")}${button(item[8], item[3] === "idle" ? "disabled" : "danger")}</div></td>
        </tr>`).join(""),
        ""
      ), `<span class="pill">platform/profile</span>`) +
      panel("新建或打开 Profile", "表单尺寸按内容收紧，不占满页面。", `<div class="form-grid">
        <div class="field compact"><label>平台</label><select><option>小红书</option></select></div>
        <div class="field medium"><label>Profile 名称</label><input value="creator-2"></div>
        <div class="field" style="align-self:end">${button("新建/登录", "primary")}</div>
      </div>`);
  },

  "collector-environment"() {
    const meta = {
      eyebrow: "collector environment",
      title: "环境自检",
      desc: "运维清单式布局，集中展示必要依赖、可选提醒、路径和处理命令，不挤在采集首页。",
    };
    return pageHeader(meta, [button("返回采集首页"), button("重新检查", "primary")]) +
      metricRow([
        ["本机状态", "READY", "必要依赖就绪"],
        ["就绪项", "5/7", "含可选提醒"],
        ["必要异常", "0", "可采集"],
        ["可选提醒", "2", "GPT / Image2"],
      ]) +
      panel("自检清单", "高密度表格更适合版本、路径和命令。", table(
        ["状态", "组件", "作用", "路径 / 版本", "处理命令"],
        envChecks.map((item) => `<tr><td>${status(item[0], item[0] === "OK" ? "ready" : "waiting")}</td><td>${item[1]}</td><td>${item[2]}</td><td><code>${item[3]}</code></td><td><code>${item[4]}</code></td></tr>`).join(""),
        ""
      ));
  },

  "collector-run-detail"() {
    const meta = {
      eyebrow: "collector run detail",
      title: "任务详情",
      desc: "状态、样本、事件链、资产证据分区更清晰；避免重复状态区，事件链和资产摘要固定 7 条可滚动。",
    };
    const events = [
      ["01", "run_started", "sidecar 启动并读取 request.json", "collector", "09:02:57"],
      ["02", "profile_attached", "使用 xiaohongshu/default 持久化 profile", "profile", "09:03:01"],
      ["03", "search_opened", "打开小红书关键词搜索页", "browser", "09:03:12"],
      ["04", "card_snapshot", "保存瀑布流字段快照", "evidence", "09:03:40"],
      ["05", "detail_opened", "进入第 1 条笔记详情页", "browser", "09:04:04"],
      ["06", "media_saved", "下载图片与视频封面资产", "asset", "09:04:16"],
      ["07", "comments_saved", "保存热评 5 条", "record", "09:04:24"],
      ["08", "detail_closed", "关闭详情页并返回搜索结果", "browser", "09:04:31"],
      ["09", "run_completed", "采集结束并写入 records.jsonl", "collector", "09:08:12"],
    ];
    const assets = [
      ["图片", "65-cover.webp", "runtime/collector/.../assets/65-cover.webp", "sha256", "媒体资产"],
      ["截图", "detail-65.png", "runtime/collector/.../evidence/detail-65.png", "证据", "post"],
      ["字段", "fields-65.json", "runtime/collector/.../evidence/fields-65.json", "证据", "post"],
      ["图片", "66-cover.webp", "runtime/collector/.../assets/66-cover.webp", "sha256", "媒体资产"],
      ["截图", "search-page-1.png", "runtime/collector/.../evidence/search-page-1.png", "证据", "search"],
      ["视频", "69-demo.mp4", "runtime/collector/.../assets/69-demo.mp4", "sha256", "媒体资产"],
      ["字段", "run-summary.json", "runtime/collector/.../evidence/run-summary.json", "证据", "run"],
      ["截图", "manual-handoff.png", "runtime/collector/.../evidence/manual-handoff.png", "证据", "manual"],
    ];
    return pageHeader(meta, [button("返回任务队列"), button("重新运行")]) +
      metricRow([
        ["生命周期", "已完成", "run_completed"],
        ["运行时长", "5m 15s", "无资源占用"],
        ["采样范围", "5 / 5", "帖子 / 评论"],
        ["产物", "5 / 23 / 34", "帖子 / 评论 / 资产"],
      ]) +
      panel("当前状态与操作", "单一状态区，避免页面上反复展示同一套状态。", `<div class="facts columns-3">
        <div class="fact"><span>Run ID</span><strong>xiaohongshu-20260524-090257</strong></div>
        <div class="fact"><span>平台 / Profile</span><strong>小红书 / default</strong></div>
        <div class="fact"><span>关键词</span><strong>AI头像</strong></div>
      </div><div class="inline-actions" style="margin-top:10px">${button("打开样本预览", "primary")}${button("归档")}</div>`) +
      panel("采集样本", "样本表只放关键字段，完整媒体查看进入样本预览。", table(["标题", "作者", "互动", "正文摘要", "操作"], samples.slice(0, 5).map((item) => `<tr><td><div class="cell-main"><strong>${item[1]}</strong><small>ID ${item[0]}</small></div></td><td>${item[3]}</td><td>赞 2.1k · 藏 340 · 评 52</td><td>${item[5]}</td><td>${button("预览", "primary")}</td></tr>`).join(""), "")) +
      `<section class="layout-grid equal">
        ${renderLedger("事件链", "按采集总览任务列表密度展示，超过 7 条内部滚动。", ["#", "事件", "范围", "时间"], events)}
        ${renderLedger("资产 / 证据摘要", "媒体文件和截图证据合并，超过 7 条内部滚动。", ["类型", "路径", "指纹", "范围"], assets, true)}
      </section>`;
  },

  "collector-sample-preview"() {
    const meta = {
      eyebrow: "sample preview",
      title: "样本预览",
      desc: "按照查看流程排列：媒体预览、正文热评、结构字段、证据链。平台原始 URL 只作为文本证据。",
    };
    return pageHeader(meta, [button("返回任务详情"), button("送入分析", "primary")]) +
      panel("样本摘要", "", facts([
        ["标题", "AI头像怎么做才不像模板？"],
        ["作者", "小鹿同学"],
        ["发布时间", "2026-05-24"],
        ["本地样本 ID", "65"],
      ], 4)) +
      `<section class="preview-grid">
        ${panel("媒体预览", "详情页截图优先，随后轮播图片 / 视频资产。", `<div class="media-stage"><div class="media-phone"></div></div><div class="thumbs"><div class="thumb"></div><div class="thumb"></div><div class="thumb"></div><div class="thumb"></div></div>`)}
        <div class="stack">
          ${panel("正文与热评", "聚焦内容判断，不展示本地文件路径。", `<div class="stack">
            <div class="thin-card"><h3>正文</h3><p>第一次做 AI 头像，最怕生成出来像模板照。这里记录真实感、五官稳定和背景统一的提示词组合。</p></div>
            <div class="thin-card"><h3>热评 01</h3><p>想要一套适合职场头像的提示词，最好能直接复制。</p></div>
            <div class="thin-card"><h3>热评 02</h3><p>生成图最大问题是眼神很空，求修正方法。</p></div>
          </div>`)}
          ${panel("结构化字段", "", facts([
            ["点赞", "2.1k"],
            ["收藏", "340"],
            ["评论", "52"],
            ["平台地址", "<code>https://www.xiaohongshu.com/...</code>"],
          ], 2))}
        </div>
      </section>` +
      panel("证据链", "证据作为列表展示，不和媒体预览混成大面板。", table(["类型", "文件", "范围", "状态"], [
        `<tr><td>详情截图</td><td><code>detail-65.png</code></td><td>post</td><td>${status("可追溯", "ready")}</td></tr>`,
        `<tr><td>字段快照</td><td><code>fields-65.json</code></td><td>post</td><td>${status("可追溯", "ready")}</td></tr>`,
        `<tr><td>媒体资产</td><td><code>65-cover.webp</code></td><td>asset</td><td>${status("已下载", "ready")}</td></tr>`,
      ].join(""), ""));
  },

  keywords() {
    const meta = {
      eyebrow: "keyword pool",
      title: "关键词池",
      desc: "紧凑配置页：生成表单和关键词表分离，表单不拉满整屏。",
    };
    const rows = ["AI头像", "小红书封面", "AI证件照", "头像小程序", "AI写真提示词", "封面设计"].map((word, index) => `<tr><td>生图小程序</td><td>${word}</td><td>${index % 2 ? "转化素材" : "需求采样"}</td><td>${index + 3}</td><td>${10 + index * 2}</td></tr>`).join("");
    return pageHeader(meta, [button("导入 CSV"), button("生成默认池", "primary")]) +
      `<section class="layout-grid reverse">
        ${panel("生成配置", "按内容定宽，不把输入框做成大横条。", `<div class="form-grid">
          <div class="field medium"><label>保存路径</label><input value="data/collection_keywords.csv"></div>
          <div class="field medium"><label>主题</label><input value="生图小程序"></div>
          <div class="field compact"><label>每日上限</label><input value="20"></div>
          <div class="field" style="align-self:end">${button("生成", "primary")}</div>
        </div>`)}
        ${panel("关键词策略", "少量摘要帮助判断，不占用大屏。", facts([
          ["主题", "3"],
          ["关键词", "26"],
          ["高权重", "8"],
          ["计划状态", "可采集"],
        ], 2))}
      </section>` +
      panel("关键词表", "配置结果以紧凑表格展示。", table(["主题", "关键词", "场景", "权重", "每日上限"], rows, ""));
  },

  report() {
    const meta = {
      eyebrow: "daily report",
      title: "日报",
      desc: "保持文档阅读页，限制正文宽度，提高连续阅读的舒适度。",
    };
    return pageHeader(meta, [button("返回总览"), button("导出 Markdown")]) +
      panel("日报摘要", "", facts([
        ["报告路径", "reports/daily-report.md"],
        ["样本覆盖", "46"],
        ["可写选题", "5"],
        ["高意图线索", "12"],
      ], 2)) +
      `<section class="panel doc-body">
        <h2>今日结论</h2>
        <p>AI头像相关样本中，用户更关心“真实感”和“可直接复制的提示词”，而不是泛泛的生成效果展示。</p>
        <p>封面设计类样本集中在标题层级、留白和平台裁切问题，适合拆成教程型内容。</p>
        <h2>建议选题</h2>
        <p>1. AI头像不像模板照的 5 个提示词修正点。</p>
        <p>2. 小红书封面标题为什么显乱：3 层信息结构。</p>
        <p>3. 证件照风格如何避免“塑料感”。</p>
        <h2>风险与备注</h2>
        <p>涉及肖像、商用和平台素材时，执行动作继续保持人工确认。</p>
      </section>`;
  },

  "analysis-home"() {
    const meta = {
      eyebrow: "analysis home",
      title: "分析首页",
      desc: "只放分析概况、关键词趋势、高价值样本入口和选题洞察。样本长表拆到分析样本页。",
    };
    return pageHeader(meta, [button("分析样本"), button("送入分析队列", "primary")]) +
      metricRow([
        ["已评分样本", "86", "规则 + GPT-5.5"],
        ["高意图", "37", "intent >= 0.70"],
        ["关键词", "14", "今日覆盖"],
        ["待复核", "7", "Top 样本"],
      ]) +
      `<section class="layout-grid">
        ${panel("关键词趋势", "用小图表看方向，不把样本表塞在首页。", bars([
          ["AI头像", "37", 88],
          ["封面设计", "24", 62, "var(--blue)"],
          ["AI证件照", "18", 48, "var(--amber)"],
          ["提示词包", "12", 34],
        ]))}
        <div class="stack">
          ${panel("高价值样本入口", "进入专页筛选、排序和送复核。", `<div class="facts columns-2"><div class="fact"><span>样本</span><strong>37</strong></div><div class="fact"><span>未复核</span><strong>7</strong></div></div><div class="inline-actions" style="margin-top:10px">${button("打开分析样本", "primary")}${button("开始复核")}</div>`)}
          ${panel("选题洞察", "只保留可写方向摘要。", `<div class="stack"><div class="thin-card"><h3>真实感头像</h3><p>用户追求不像模板、眼神自然、可商用。</p></div><div class="thin-card"><h3>封面层级</h3><p>标题和元素拥挤，是高频痛点。</p></div></div>`)}
        </div>
      </section>`;
  },

  "analysis-samples"() {
    const meta = {
      eyebrow: "analysis samples",
      title: "分析样本",
      desc: "承载高价值样本表格和筛选，首页只保留入口。",
    };
    return pageHeader(meta, [button("批量送复核"), button("导出样本")]) +
      `<section class="panel tight">
        <div class="filters">
          <div class="field compact"><label>关键词</label><select><option>全部</option><option>AI头像</option></select></div>
          <div class="field compact"><label>意图分</label><select><option>>= 0.70</option></select></div>
          <div class="field compact"><label>复核状态</label><select><option>未复核</option></select></div>
          ${button("筛选", "primary")}
        </div>
        ${table(["ID", "标题", "关键词", "意图", "价值", "建议选题", "痛点", "操作"], samples.map((item) => `<tr><td>${item[0]}</td><td><div class="cell-main"><strong>${item[1]}</strong><small>${item[3]}</small></div></td><td>${item[2]}</td><td>${item[4]}</td><td>${(Number(item[4]) - 0.08).toFixed(2)}</td><td>${item[5]}</td><td>需要可复制方案</td><td>${button("送复核", "primary")}</td></tr>`).join(""), "scroll-7")}
      </section>`;
  },

  review() {
    const meta = {
      eyebrow: "human review",
      title: "人工复核",
      desc: "改成复核工作台：左侧表格选择样本，右侧固定复核表单，行内操作保持紧凑。",
    };
    return pageHeader(meta, [button("上一条"), button("保存并下一条", "primary")]) +
      `<section class="review-workbench">
        ${panel("待复核样本", "Top 20 样本列表，不在行内塞长备注表单。", table(["ID", "关键词", "标题", "意图", "价值", "状态"], samples.map((item, index) => `<tr><td>${item[0]}</td><td>${item[2]}</td><td><div class="cell-main"><strong>${item[1]}</strong><small>${item[5]}</small></div></td><td>${item[4]}</td><td>${(Number(item[4]) - 0.06).toFixed(2)}</td><td>${status(index === 0 ? "当前" : "待复核", index === 0 ? "running" : "queued")}</td></tr>`).join(""), "scroll-7"))}
        ${panel("复核表单", "表单动作独立，避免每行都拉宽。", `<div class="stack">
          <div class="thin-card"><h3>当前样本</h3><p>AI头像怎么做才不像模板？</p><small>痛点：头像真实感 / 可复用提示词</small></div>
          <div class="field"><label>判断</label><select><option>优秀</option><option>有用</option><option>一般</option><option>噪音</option></select></div>
          <div class="field"><label>备注</label><textarea>适合整理成提示词修正教程。</textarea></div>
          <div class="inline-actions">${button("保存", "primary")}${button("跳过")}</div>
        </div>`)}
      </section>`;
  },

  "execution-home"() {
    const meta = {
      eyebrow: "execution home",
      title: "执行首页",
      desc: "展示待确认草稿队列和优先级概览。完整状态管理放到触达任务页。",
    };
    return pageHeader(meta, [button("触达任务"), button("生成草稿", "primary")]) +
      metricRow([
        ["待确认", "9", "人工确认"],
        ["高优先级", "3", "评论 / 私信"],
        ["素材待补", "2", "Image2 可选"],
        ["最终动作", "人工确认", "不自动发布"],
      ]) +
      `<section class="layout-grid">
        ${panel("待确认草稿", "首页只展示优先队列摘要。", `<div class="stack">
          <div class="task-card"><div class="task-head"><strong>[高] AI头像真实感教程评论</strong>${status("待确认", "waiting")}</div><p class="muted">评论草稿：可以先从眼神、肤色和背景三个变量排查...</p></div>
          <div class="task-card"><div class="task-head"><strong>[高] 小红书封面选题草稿</strong>${status("待确认", "waiting")}</div><p class="muted">发帖标题：封面看起来乱，通常不是颜色问题...</p></div>
          <div class="task-card"><div class="task-head"><strong>[中] AI证件照私信草稿</strong>${status("素材待补", "queued")}</div><p class="muted">需要确认是否生成配图示例。</p></div>
        </div>`)}
        <div class="stack">
          ${panel("优先级概览", "", bars([["高", "3", 72, "var(--danger)"], ["中", "4", 58, "var(--amber)"], ["低", "2", 24, "var(--blue)"]]))}
          ${panel("确认规则", "", `<div class="callout">Falcon 只准备草稿、素材和执行预览；发布、评论、私信仍由人确认。</div>`)}
        </div>
      </section>`;
  },

  tasks() {
    const meta = {
      eyebrow: "outreach tasks",
      title: "触达任务",
      desc: "作为任务状态管理页，避免和执行首页重复展示同一批内容。状态、草稿和处理动作在这里闭环。",
    };
    const taskRows = [
      ["T-1024", "AI头像真实感教程评论", "评论", "高", "pending", "待确认"],
      ["T-1025", "封面层级选题发布预览", "发帖", "高", "pending", "待确认"],
      ["T-1026", "AI证件照私信回复", "私信", "中", "copied", "已复制"],
      ["T-1027", "提示词包评论回复", "评论", "中", "handled", "已处理"],
      ["T-1028", "版权风险样本", "复核", "低", "skipped", "已跳过"],
    ];
    return pageHeader(meta, [button("批量更新"), button("打开执行预览", "primary")]) +
      `<section class="layout-grid reverse">
        ${panel("任务筛选", "按状态和优先级管理，不占大面积。", `<div class="form-grid">
          <div class="field compact"><label>状态</label><select><option>待确认</option><option>已复制</option><option>已处理</option></select></div>
          <div class="field compact"><label>优先级</label><select><option>全部</option><option>高</option><option>中</option></select></div>
          <div class="field medium"><label>搜索</label><input value="AI头像"></div>
          <div class="field" style="align-self:end">${button("筛选", "primary")}</div>
        </div>`)}
        ${panel("当前草稿预览", "选中任务后在侧栏确认状态。", `<div class="stack">
          <div class="thin-card"><h3>评论草稿</h3><p>可以先从眼神、肤色和背景三个变量排查，尤其是背景太干净会显得模板化。</p></div>
          <div class="field"><label>更新状态</label><select><option>copied</option><option>handled</option><option>skipped</option><option>invalid</option></select></div>
          <div class="inline-actions">${button("保存状态", "primary")}${button("标记风险", "danger")}</div>
        </div>`)}
      </section>` +
      panel("任务表", "完整状态管理页使用表格，不再重复首页卡片队列。", table(["任务 ID", "标题", "类型", "优先级", "状态", "操作"], taskRows.map((row) => `<tr><td>${row[0]}</td><td><div class="cell-main"><strong>${row[1]}</strong><small>来源样本 / 风险提示 / 草稿数量</small></div></td><td>${row[2]}</td><td>${row[3]}</td><td>${status(row[5], row[4] === "pending" ? "waiting" : "ready")}</td><td>${button("查看")}</td></tr>`).join(""), ""));
  },
};

function init() {
  const pageId = document.body.dataset.page;
  const app = document.getElementById("app");
  if (!pageId || !app || !templates[pageId]) return;
  document.title = `${byId[pageId].label} - Falcon 布局重设计`;
  app.innerHTML = renderShell(pageId, templates[pageId]());
}

init();
