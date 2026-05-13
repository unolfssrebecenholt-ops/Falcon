# 影刀 RPA 混合架构开发指南

本文是 Falcon 项目的影刀知识资产，用于指导小红书等复杂现代网页的低频公开样本采集流程。它总结影刀在 SPA、动态渲染和视觉遮挡页面上的核心坑点，并把后续 AI 辅助开发回答约束在“影刀可视化流程 + Python 代码段”的混合架构内。

本项目边界不变：Falcon 不做纯代码爬虫，不自动评论、不自动私信，不以规避平台规则为目标。影刀流程只采集公开可见样本，并通过 Falcon 做本地导入、分析、日报和人工复核。

配套资料：

- [影刀组件对象手册](yingdao-component-handbook.md)：按影刀组件分类记录操作方式、常用输入输出、坑点和验证方式。
- [影刀辅助规则](yingdao-assistant-rules.md)：约束后续 Codex 辅助写影刀时的提问方式、伪工作流格式和排查顺序。

## 1. 核心结论

推荐架构是“手眼分离”：

- 影刀可视化流程负责网页导航、点击、滚动、等待、DOM 元素捕获、相似元素列表获取和最终表格写入。
- Python 代码段负责数据清洗、空值兜底、字段拼装、列表追加和结构化行生成。
- 影刀侧先声明全局列表，例如 `row_data_list`；循环中用 Python 直接 `row_data_list.append(cleaned_row)`；循环结束后再一次性写入 CSV/xlsx。
- 抓取详情页时优先模拟真实路径：点击卡片、等待弹窗或详情渲染、读取当前页面 URL、采集数据、按 `{Esc}` 关闭弹窗。
- 不建议批量收集 URL 后循环直接跳转详情页，这会失去来源路径，更容易触发平台风控或 App 扫码提示。

## 2. 影刀核心机制与避坑

### 动态属性导致元素定位失效

现代前端框架常生成动态类名或属性，例如 `data-v-xxx`。影刀默认捕获规则可能把这些随机特征写进去，刷新、滚动或重新打开页面后元素就找不到。

处理原则：

- 不盲用默认捕获规则。
- 进入元素编辑界面，改用 CSS 选择器或 XPath。
- 选择稳定特征，例如业务 class、id、可读结构关系或文本附近结构。
- 忽略 `data-v-*` 这类构建期属性。

### 默认严格模式导致流程中断

非关键字段可能缺失，例如无标题笔记、无摘要卡片、隐藏点赞数。若 `获取元素信息(web)` 默认抛错，流程会直接中断。

处理原则：

- 对非必需字段开启错误处理。
- 错误动作设为“继续执行后续指令”。
- 设置默认输出值，例如空字符串、`0` 或 `None` 对应的文本占位。
- 必需字段才允许中断，例如当前卡片对象不存在、页面对象失效。

### 视觉层遮挡导致模拟点击失效

部分页面真实事件绑定在底层节点上，上面有透明蒙层、图片容器或浮层。模拟人工点击可能点在遮挡层上，页面没有响应。

处理原则：

- 先确认元素是否被遮挡。
- 点击指令高级设置优先尝试“JS 点击”。
- JS 点击用于直接触发 DOM 事件，适合卡片、关闭按钮、弹窗内按钮等复杂层级。
- 若 JS 点击也失败，再检查元素选择器是否选到了容器而非可点击节点。

### SPA 路由变化造成网页对象误判

小红书这类单页面应用可能点击卡片后出现全屏弹窗，地址栏 URL 改变，但没有新标签页，也没有真正打开新网页对象。

处理原则：

- 不新建 `web_page` 对象。
- 继续使用原有网页对象。
- 点击后随机等待 1-3 秒，让弹窗和评论区渲染。
- 通过“获取网页信息”读取当前地址栏 URL。
- 采集完成后向当前页面发送 `{Esc}` 关闭弹窗，回到搜索结果流。

### 匹配项非唯一导致错误码 129

当选择器匹配多个元素时，影刀可能报“匹配到多个元素，无法唯一定位”。

处理原则：

- 只要第一个元素：在高级设置里把“匹配序号”设为 `1`。
- 要全部元素：改用 `获取相似元素列表(web)`。
- 轮播图、评论列表、搜索结果卡片都优先按相似元素列表处理。

## 3. 标准混合工作流

### 步骤 1：声明全局结果列表

在可视化流程外层使用 `新建列表`：

```text
row_data_list = 新建列表
```

后续所有笔记行和评论行都追加到这个列表。

### 步骤 2：可视化流程负责交互

在影刀中保留真实页面行为：

```text
打开小红书 -> 输入 keyword -> 点击搜索 -> 随机等待 -> 低频滚动
获取相似元素列表(web) -> ForEach current_card
点击 current_card -> 随机等待 -> 获取详情字段 -> 采集评论 -> Esc 关闭弹窗
```

所有点击、滚动、等待、元素列表捕获都放在可视化流程里。每次交互间加入随机等待，例如 1-3 秒；滚动和打开详情页保持低频。

### 步骤 3：Python 代码段负责清洗和组装

Python 代码段只处理已经由可视化流程拿到的变量，不直接控制浏览器：

```python
import re


def clean_text(value):
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


row = [
    "xiaohongshu",
    clean_text(current_keyword),
    "post",
    clean_text(detail_title),
    clean_text(detail_content),
    clean_text(post_url),
    "",
    clean_text(author),
    "",
    "",
    "",
    clean_text(collected_at),
]

row_data_list.append(row)
```

如果要写评论行，保持同一表头：

```python
comment_row = [
    "xiaohongshu",
    clean_text(current_keyword),
    "comment",
    clean_text(detail_title),
    clean_text(comment_text),
    clean_text(post_url),
    clean_text(post_url),
    clean_text(author),
    clean_text(commenter),
    clean_text(like_count),
    clean_text(comment_rank),
    clean_text(collected_at),
]

row_data_list.append(comment_row)
```

### 步骤 4：循环结束后一次性落盘

循环内不要频繁写文件。循环结束后使用影刀可视化指令写入数据表格或 CSV/xlsx。

推荐字段顺序：

```csv
platform,keyword,source_type,title,content,url,parent_url,author,commenter,like_count,comment_rank,collected_at
```

落盘后用 Falcon 验证：

```powershell
py -3 -m falcon --db data\falcon.sqlite3 run-yingdao-daily data\xhs_raw_export.xlsx --keyword "生图小程序" --report-output reports\daily-report.md
```

macOS 接手验证：

```bash
python3 -m falcon --db data/falcon.sqlite3 run-yingdao-daily data/xhs_raw_export.xlsx --keyword "生图小程序" --report-output reports/daily-report.md
```

## 4. 新手典型错误

### 混淆内存变量和 DOM 元素

错误做法：判断变量为空时，用 `设置元素值(web)` 给变量赋空字符串。

正确做法：网页元素属于浏览器渲染层，普通文本和列表属于影刀内存变量。给变量赋值使用变量指令或 Python 代码段，不使用 web 元素指令。

### 循环中操作静态元素库节点

错误做法：ForEach 遍历卡片时，后续指令仍选择元素库里的静态卡片节点，导致每轮都回到页面顶部找同一个元素。

正确做法：循环内操作对象必须绑定当前循环变量，例如 `current_card`。需要子元素时，从 `current_card` 出发获取关联元素。

### Python 作用域理解错误

错误做法：在 Python 代码段内部创建列表，再回到可视化界面用“列表插入一项”操作该列表。

正确做法：先在可视化层创建全局列表，再在 Python 代码段中直接 append。Python 内部临时变量只在该代码段内可靠。

### 沿用传统爬虫思路

错误做法：批量提取详情 URL，循环新建标签页直接访问。

正确做法：RPA 的优势是沿着真实页面路径低频交互。列表页详情采集优先使用：

```text
模拟点击卡片 -> 等待弹窗或详情渲染 -> 读取地址栏 URL 和详情字段 -> Esc 关闭
```

## 5. 给 AI 的回答约束

当后续让我继续设计影刀流程时，回答必须遵守以下约束：

- 角色定位：高级影刀 RPA 架构师，目标是稳定、低频、可维护的自动化流程。
- 不提供 `requests`、纯 Selenium 或 Playwright 爬虫方案作为主方案。
- 网页交互、等待、滚动、点击和元素提取使用影刀可视化指令。
- 数据清洗、字段兜底、列表组装输出精简 Python 代码，放入影刀“插入代码段(Python)”。
- 变量交互采用“可视化全局列表 + Python append”的方式。
- 列表页详情采集优先点击卡片，不直接遍历 URL。
- 所有交互动作之间提醒加入随机等待，例如 1-3 秒。
- 遇到遮挡和层级复杂点击，先确认目标网站是否禁用 JS 点击；小红书当前不把 JS 点击作为默认方案。
- 非必需字段采集必须提醒开启错误处理，继续执行并赋空值。
- 动态前端选择器忽略 `data-v-*`，使用稳定 CSS/XPath 或结构关系。
- SPA 弹窗内 URL 优先读取当前地址栏，不假设新网页对象。
- 回答影刀编排问题时使用伪工作流格式，沿用用户已有行号、变量名和组件名；需要删除节点时优先建议禁用。
- 每次用户问影刀问题时，主动索取 DOM 元素证据，包括 DevTools 截图、HTML 片段或 DOM 交互形式描述。

## 6. 明天优先落地的影刀侧任务

1. 把 `row_data_list` 作为影刀全局列表固定下来。
2. 搜索结果页使用 `获取相似元素列表(web)` 获取卡片列表。
3. ForEach 中所有动作绑定 `current_card`，不要回到静态元素库节点。
4. 点击卡片后按 SPA 弹窗处理，读取当前地址栏 URL。
5. 为标题、正文、作者、评论文本等非关键字段配置错误处理和默认空值。
6. 用 Python 代码段按统一表头 append `post/comment` 行。
7. 导出结构化 xlsx 后，运行 Falcon `run-yingdao-daily` 验证导入、分析和日报。
