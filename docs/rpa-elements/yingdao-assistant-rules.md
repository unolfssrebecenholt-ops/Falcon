# 影刀辅助规则

本文约束 Codex 后续辅助编排、排查和修改影刀流程时的回答方式。用户只要提到影刀、小红书 RPA、流程截图、DOM、卡片点击、采集、CSV/xlsx 输出，就优先按本文执行。

## 0. 必读资料

回答、设计、排查或修改任何影刀相关问题前，必须先读完本项目影刀资料：

```text
docs/rpa-elements/yingdao-assistant-rules.md
docs/rpa-elements/yingdao-component-handbook.md
docs/rpa-elements/yingdao-hybrid-architecture-guide.md
docs/yingdao-runbook.md
docs/rpa-elements/current-yingdao-mainflow.md
docs/rpa-elements/xiaohongshu-workflow-draft.md
```

读完后再结合用户本次提供的流程截图、DOM 截图、HTML 片段、运行日志和页面行为描述给建议。

## 1. 默认输入要求

每次用户问影刀问题时，主动索取或确认以下材料：

```text
1. 当前影刀流程截图，最好包含行号和缩进。
2. 相关节点的配置截图，尤其是点击、获取相似元素、获取元素信息、IF、写 CSV。
3. DOM 证据：
   - DevTools 截图；
   - 或 HTML 片段；
   - 或说明目标元素和点击区域的交互关系。
4. 运行日志，尤其是 Python print 输出和影刀报错。
5. 用户观察到的真实页面行为：
   - 是否进入详情；
   - 是否误入图片放大层；
   - 是否成功写 CSV；
   - 是否换关键词后状态异常。
```

如果缺 DOM 或交互描述，不要直接拍脑袋写选择器。先问用户要 DOM 截图或 HTML 片段。

## 2. 回答格式

后续辅助写影刀时，使用“伪工作流格式”，并尽量贴近用户现有行号和变量名。

```text
改动清单：
- 第 N 行：禁用 / 保留 / 修改
- 第 M 行：替换 Python
- 其他行：不动

局部伪工作流：
N. 组件名
   输入：
   输出：
   说明：
```

Python 代码：

```python
...
```

验证日志应该看到：

```text
...
```

如果用户说“按照我的工作流改”，必须沿用用户已有步骤命名和变量名。要删节点时优先建议“禁用”，不要让行号和顺序大幅变化。

## 3. 排查顺序

影刀问题按证据排查，不先给大改方案：

```text
1. 先读日志，判断流程实际执行到哪一层。
2. 再看行号和缩进，确认 IF / 循环是否包住了预期动作。
3. 再看 DOM，确认选择器拿到的是容器、链接、图片还是文本。
4. 再看点击行为，确认是否进入详情、图片查看器或无反应。
5. 最后才改代码或节点配置。
```

常见判断：

```text
post_link_list 有循环日志，但 card_key 为空：
  href 或文本提取失败。

card_key 有值，should_click_card = 1，但没点击：
  影刀 IF 没识别条件，改用整数旗标。

点击后进入图片放大层：
  点击落点命中图片区域，需要调整点击对象、点击位置或 DOM 策略。

多关键词第二个直接跳过：
  stop_current_keyword 或 seen_card_keys 放错作用域。
```

## 4. 架构边界

```text
1. 不把纯 requests、Selenium、Playwright 爬虫作为主方案。
2. 网页交互仍由影刀可视化组件完成。
3. Python 只负责变量控制、字段清洗、href 提取、去重、CSV 写入、图片下载等数据处理。
4. 不自动评论、不自动私信、不做批量触达。
5. 不以规避平台规则为目标，只做低频公开样本采集。
```

## 5. DOM 与选择器规则

```text
1. 忽略 data-v-* 等动态构建属性。
2. 优先使用稳定 class、业务结构、href、文本附近结构。
3. 小红书搜索结果是瀑布流，post_link_list 只代表当前 DOM 快照。
4. 已验证 XPath 比 CSS 点击更稳时，优先复用 XPath：
   //section[contains(@class, 'note-item')]//a[contains(@class, 'cover')]
5. 影刀“获取关联元素(web)”没有子孙元素选项，只有父元素、子元素、相邻元素；不要把子元素当后代元素。
```

## 6. 变量与控制流规则

```text
1. 多关键词循环内必须重置：
   row_data_list
   seen_card_keys
   processed_count
   no_new_scroll_rounds
   stop_current_keyword
2. 影刀 IF 不稳定识别 Python 布尔值时，使用整数旗标：
   should_click_card = 1 或 0
3. 没有可靠“跳出循环”时，用 stop_current_keyword 控制后续卡片和滚动跳过。
4. 调试阶段优先一行一写 CSV，降低中途崩溃的数据损失。
```

## 7. 点击与运行环境规则

```text
1. 小红书禁用 JS 点击，不把 JS 点击作为默认建议。
2. 点击不稳定时，先确认点击对象是不是图片链接、标题区、按钮或容器。
3. 点击中心进入图片放大层时，不要继续盲调等待时间；要看 DOM 和交互描述。
4. 脚本运行时用户不要移动鼠标、切换窗口或分屏操作其它应用。
5. ESC 发送给当前激活窗口；若焦点错位，会关闭错误窗口或不关闭详情。
```

## 8. 更新资料规则

每次当天影刀问题解决或形成新坑点，应同步更新：

```text
docs/rpa-elements/yingdao-component-handbook.md
docs/rpa-elements/yingdao-assistant-rules.md
docs/rpa-elements/yingdao-hybrid-architecture-guide.md
docs/progress.md
```

如果新增了真实 DOM 截图或元素命名，应继续更新：

```text
docs/rpa-elements/xiaohongshu-elements.md
docs/rpa-elements/current-yingdao-mainflow.md
```
