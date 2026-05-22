# 影刀组件对象手册

本文把 Falcon 项目中已经用过的影刀组件按类别归档。后续辅助编排影刀流程时，优先按本文的组件属性、操作手册和避坑记录输出伪工作流。

## 组件记录规则

每个组件按同一套对象属性记录：

```text
组件名：
类别：
用途：
常用输入：
常用输出：
操作手册：
已知坑：
推荐写法：
验证方式：
```

如果用户提供新的影刀截图、DOM 截图、HTML 片段、运行日志或交互描述，应把新增经验补到对应组件的“已知坑”和“推荐写法”里。

## 一、流程控制组件

### ForEach列表循环

```text
组件名：ForEach列表循环
类别：流程控制
用途：遍历关键词列表、当前 DOM 快照列表、评论列表等。
常用输入：keywords、post_link_list、raw_image_list、comment_list
常用输出：current_keyword、current_card、img_element、current_comment
操作手册：
1. 先由“新建列表”或“获取相似元素列表(web)”得到列表。
2. 循环当前项必须保存成明确变量，例如 current_keyword 或 current_card。
3. 循环内部所有操作都绑定当前项，不回到静态元素库节点。
已知坑：
- 瀑布流 DOM 会随滚动变化，post_link_list 只能代表当前 DOM 快照，不能跨滚动长期保存。
- 如果循环里仍点击元素库里的静态节点，可能每次都点同一张卡片。
- 多关键词时，关键词内状态必须在 current_keyword 循环内重置，不能继承上一个关键词的 stop_current_keyword。
推荐写法：
ForEach keywords -> current_keyword
  新建 row_data_list
  新建 seen_card_keys
  初始化 processed_count / no_new_scroll_rounds / stop_current_keyword
  搜索 current_keyword
  For次数循环滚动窗口
    获取 post_link_list
    ForEach post_link_list -> current_card
验证方式：
- 日志打印 current_keyword、loop_index、processed_count。
- 每个关键词开始时应看到“当前关键词控制变量初始化完成”。
```

### For次数循环

```text
组件名：For次数循环
类别：流程控制
用途：控制滚动轮次，形成“当前窗口采集 -> 滚动 -> 重新获取 DOM 快照”的节奏。
常用输入：开始值 0，结束值 4，递增值 1
常用输出：loop_index
操作手册：
1. 每轮开始先用 Python 设置 new_count_this_round = 0。
2. 每轮重新执行“获取相似元素列表(web)”。
3. 当前轮处理完后，根据 new_count_this_round 和 no_new_scroll_rounds 决定是否继续滚动。
已知坑：
- 不要在滚动前拿一大批 DOM 后慢慢处理，旧 DOM 会失效、重排或点错。
- 影刀里如果没有可靠“跳出循环”指令，不要写空 IF，改用 stop_current_keyword 让后续轮次空跑。
推荐写法：
For次数循环 0 到 4 -> loop_index
  new_count_this_round = 0
  获取当前 DOM 快照
  处理未见过的 current_card
  更新 no_new_scroll_rounds
  IF stop_current_keyword == False
    IF no_new_scroll_rounds < 2
      鼠标滚动网页
验证方式：
- 日志里 loop_index 应递增。
- 如果 processed_count 达到 detail_open_limit，后续不应继续点击卡片。
```

### IF 条件

```text
组件名：IF 条件
类别：流程控制
用途：判断当前元素是否为空、是否允许点击、是否继续滚动。
常用输入：current_card、should_click_card、stop_current_keyword、no_new_scroll_rounds
常用输出：无
操作手册：
1. 对 Python 布尔值不要直接用 skip_current_card == False 做关键判断。
2. 推荐由 Python 输出整数旗标，例如 should_click_card = 1 或 0。
3. 影刀 IF 里判断 should_click_card > 0 更稳定。
已知坑：
- Python 的 False 不一定被影刀 IF 识别成影刀布尔值。
- IF 容器本身不会自动跳出循环，里面必须有实际动作。
推荐写法：
IF current_card 不是空值
  Python 设置 should_click_card
  IF should_click_card > 0
    点击 current_card
验证方式：
- 日志同时打印 skip_current_card 和 should_click_card。
- 只要 should_click_card: 1，下一步应进入点击节点。
```

## 二、数据与变量组件

### 新建列表

```text
组件名：新建列表
类别：数据处理
用途：初始化关键词列表、当前关键词输出行列表、去重 key 列表。
常用输出：keywords、row_data_list、seen_card_keys
操作手册：
1. 全局层创建 keywords。
2. 每个 current_keyword 内部重新创建 row_data_list 和 seen_card_keys。
3. row_data_list 可用于批量写 CSV；如果一行一写，可以保留但不再依赖它。
已知坑：
- seen_card_keys 放到关键词循环外，会导致不同关键词之间互相去重污染。
- row_data_list 放到关键词循环外，可能多个关键词写入同一个文件或重复写。
推荐写法：
ForEach keywords -> current_keyword
  新建 row_data_list
  新建 seen_card_keys
验证方式：
- 每个关键词的 CSV 文件只包含当前关键词数据。
```

### 列表插入一项

```text
组件名：列表插入一项
类别：数据处理
用途：添加关键词，或在批量写模式下把 cleaned_row 放入 row_data_list。
常用输入：keywords、row_data_list、cleaned_row
常用输出：更新后的列表
操作手册：
1. 添加关键词时，在 keywords 末尾追加文本。
2. 批量写模式下，在 row_data_list 末尾追加 cleaned_row。
3. 一行一写模式下，禁用 row_data_list 追加节点，由 Python 直接写 CSV。
已知坑：
- 如果 Python 已经 writer.writerow(cleaned_row)，再启用列表插入和最终数据写入 CSV，会重复写或写空。
- 为保留行号和流程顺序，调试时优先“禁用”节点，不直接删除。
推荐写法：
一行一写模式：
  第 N 行 Python 直接写 CSV
  禁用 row_data_list 追加节点
  禁用最终数据写入 CSV
验证方式：
- 脚本中途失败时，CSV 已经有前面成功采集的行。
```

### 设置变量

```text
组件名：设置变量
类别：数据处理
用途：设置 root_path 等简单变量。
常用输入：文本、整数、布尔
常用输出：root_path 等变量
操作手册：
1. 适合设置 root_path 这种简单文本变量。
2. 复杂控制变量建议用 Python 初始化，避免变量名无法绑定。
已知坑：
- 变量名框如果出现红色感叹号，通常表示影刀没有识别成合法变量引用。
- 手写 processed_count 这类新变量名可能无法创建变量 chip。
推荐写法：
root_path 用设置变量。
processed_count / stop_current_keyword / no_new_scroll_rounds 用 Python 初始化。
验证方式：
- 变量名显示为蓝色变量 chip，而不是普通白色文本。
```

### 插入代码段(Python)

```text
组件名：插入代码段(Python)
类别：数据处理
用途：初始化控制变量、创建 CSV、从元素对象读取 href、去重判断、清洗内容、下载图片、一行一写 CSV。
常用输入：root_path、current_keyword、timestamp、current_card、raw_title、raw_content、raw_image_list、note_url
常用输出：book_csv_path、should_click_card、cleaned_row、processed_count、stop_current_keyword
操作手册：
1. 用 Python 管理复杂变量和判断逻辑。
2. 从 current_card 读取 href 时，优先使用 current_card.get_attribute("href")。
3. 给影刀 IF 使用 should_click_card = 1/0，而不是 Python 布尔值。
4. 一行一写时，在生成 cleaned_row 后立刻 writer.writerow(cleaned_row)。
已知坑：
- Python 代码段内临时变量要确认后续影刀节点能访问；不确定时用日志打印。
- 影刀节点获取 href 可能失败，但 Python 里 current_card.get_attribute("href") 可用。
- 小红书内容如果后续要投喂 AI，可按需要过滤 emoji 和特殊符号。
- 给用户替换 Python 代码段时必须提供该节点的全量代码；如果当前代码版本不确定，先让用户贴对应行完整代码块做校准，再输出全量替换版。
推荐写法：
- `href_raw = current_card.get_attribute("href") or ""`
- `should_click_card = 1`
验证方式：
- 日志必须打印 href_raw、card_key、should_click_card、processed_count。
```

## 三、网页交互组件

### 打开网页

```text
组件名：打开网页
类别：网页自动化
用途：打开小红书首页或搜索入口。
常用输入：https://www.xiaohongshu.com/
常用输出：web_page
操作手册：
1. 每个关键词可重新打开首页，保证搜索状态干净。
2. 输出网页对象统一命名为 web_page。
已知坑：
- 小红书是 SPA，后续点击详情通常不产生新网页对象。
- 不要点击详情后新建 web_page。
推荐写法：
打开网页 -> web_page
后续详情弹窗仍读取 web_page 当前 URL。
验证方式：
- 点击详情后“获取网页信息”能读取变化后的当前地址。
```

### 等待网页加载完成 / 等待

```text
组件名：等待网页加载完成 / 等待
类别：网页自动化
用途：等待首页、搜索结果、SPA 弹窗和瀑布流新卡片渲染。
常用输入：web_page、等待秒数
常用输出：无
操作手册：
1. 打开首页和搜索后使用等待网页加载完成。
2. 点击卡片后使用 1 到 4 秒等待。
3. ESC 关闭弹窗后等待 1 到 2 秒。
已知坑：
- 等待网页加载完成不一定能覆盖 SPA 弹窗渲染，仍需普通等待。
- 等待太短会导致 click_title/click_content 获取为空。
推荐写法：
搜索后等待网页加载完成 20 秒 + 等待 1 到 3 秒。
点击详情后等待 1 到 4 秒。
验证方式：
- 详情字段采集前，页面应已经显示标题和正文区域。
```

### 点击元素(web)

```text
组件名：点击元素(web)
类别：网页自动化
用途：点击搜索框、搜索按钮、搜索结果卡片。
常用输入：web_page、输入框_search-input、块元素_search-icon、current_card
常用输出：页面状态变化
操作手册：
1. 搜索框和搜索按钮可用普通左键点击。
2. 搜索结果卡片 current_card 来自 post_link_list。
3. 小红书禁用 JS 点击时，不能把 JS 点击作为主方案。
4. 点击配置应尽量复用已验证可用的 XPath 获取结果。
已知坑：
- 点击 a.cover 图片中心可能进入详情后又触发图片放大层。
- 瀑布流卡片高度不同，中心点点击不稳定。
- 运行脚本时用户不能乱动鼠标、切换窗口或分屏操作，否则点击、滚动、ESC 可能发错窗口。
推荐写法：
优先复用已验证 XPath：
//section[contains(@class, 'note-item')]//a[contains(@class, 'cover')]
点击 current_card。
如果误入图片放大层，优先调整点击位置，不使用 JS 点击。
验证方式：
- 点击后应进入正常详情弹窗，而不是图片查看器。
```

### 填写输入框(web)

```text
组件名：填写输入框(web)
类别：网页自动化
用途：输入 current_keyword。
常用输入：web_page、输入框_search-input、current_keyword
常用输出：搜索框文本
操作手册：
1. 先点击搜索框。
2. 再填写 current_keyword。
3. 再点击搜索按钮。
已知坑：
- 如果页面焦点被其它窗口抢走，输入会失败或输入到错误位置。
- 多关键词循环时，建议每个关键词重新打开首页，减少旧搜索状态影响。
推荐写法：
点击搜索框 -> 填写 current_keyword -> 点击 search-icon。
验证方式：
- 搜索结果页顶部关键词与 current_keyword 一致。
```

### 鼠标滚动网页

```text
组件名：鼠标滚动网页
类别：网页自动化
用途：加载下一批瀑布流卡片。
常用输入：web_page、滚动距离或滚动到底部
常用输出：新的 DOM 卡片
操作手册：
1. 只在 stop_current_keyword == False 且 no_new_scroll_rounds < 2 时滚动。
2. 滚动后等待 1 到 2 秒。
3. 下一轮必须重新获取 post_link_list。
已知坑：
- 瀑布流不是整齐网格，前面的 DOM 可能随滚动消失或重排。
- 不要跨滚动保存 current_card。
- 滚动到底部可能跳过中间区域，能固定距离滚动时优先固定距离。
推荐写法：
当前 DOM 快照处理完 -> 判断是否继续 -> 滚动 -> 等待 -> 重新获取 DOM。
验证方式：
- 每轮 loop_index 都重新打印 href_raw。
```

### 键盘输入

```text
组件名：键盘输入
类别：网页自动化
用途：发送 {ESCAPE} 关闭 SPA 详情弹窗。
常用输入：{ESCAPE}
常用输出：关闭弹窗或图片查看器
操作手册：
1. 详情采集完成后发送 ESC。
2. ESC 后等待 1 到 2 秒再继续。
已知坑：
- 如果当前激活窗口不是影刀浏览器，ESC 会发给错误窗口。
- 如果误入图片放大层，第一次 ESC 可能只关闭图片查看器，不一定关闭详情弹窗。
推荐写法：
采集完一条 post 后发送 ESC，再等待页面恢复。
验证方式：
- ESC 后搜索结果流可见，下一张 current_card 可点击。
```

## 四、网页元素提取组件

### 获取相似元素列表(web)

```text
组件名：获取相似元素列表(web)
类别：网页元素提取
用途：获取搜索结果卡片、详情页图片列表、评论列表。
常用输入：web_page、XPath 或 CSS 选择器
常用输出：post_link_list、raw_image_list、comment_list
操作手册：
1. 搜索结果卡片优先使用已验证 XPath：
   //section[contains(@class, 'note-item')]//a[contains(@class, 'cover')]
2. 图片列表使用：
   //div[contains(@class, 'note-slider-img')]//img
3. 每次滚动后重新获取列表。
已知坑：
- CSS 和 XPath 在浏览器里语义相近，但影刀点击行为可能不同；已验证 XPath 更稳时优先 XPath。
- 获取到的是当前 DOM 快照，不是永久队列。
- 瀑布流中推荐块或广告可能混入，需要根据 href 或正文质量过滤。
推荐写法：
For次数循环内：
  获取 post_link_list
  ForEach post_link_list -> current_card
验证方式：
- 日志中每轮 href_raw 不为空。
```

### 获取元素信息(web)

```text
组件名：获取元素信息(web)
类别：网页元素提取
用途：提取详情标题、正文、网页元素文本、属性。
常用输入：click_title、click_content、current_card
常用输出：raw_title、raw_content、href_raw、card_preview
操作手册：
1. 标题和正文使用已归档元素 click_title、click_content。
2. 非必需字段开启错误处理，失败继续并给空值。
3. current_card 的 href 如果节点提取失败，改用 Python current_card.get_attribute("href")。
已知坑：
- a.cover 通常没有文本内容，card_preview 为空是正常的。
- 影刀节点读取 href 可能失败，但 Python 读取可行。
- 图片放大层会导致 click_title/click_content 取不到详情内容。
推荐写法：
详情字段使用节点提取。
卡片 href 使用 Python 读取。
验证方式：
- 日志打印 raw_title 或 cleaned_row 前 6 列。
```

### 获取网页信息

```text
组件名：获取网页信息
类别：网页元素提取
用途：读取 SPA 弹窗当前 URL。
常用输入：web_page
常用输出：note_url
操作手册：
1. 点击卡片进入详情后，不新建页面对象。
2. 使用原 web_page 读取当前网址。
3. note_url 写入 cleaned_row。
已知坑：
- 小红书详情可能是 SPA 弹窗，地址栏变化但 web_page 对象不变。
- 如果误入图片放大层，读取到的 URL 可能仍是详情 URL，但标题正文采集会失败。
推荐写法：
点击 current_card -> 等待 -> 获取网页信息 web_page 当前网址 -> note_url。
验证方式：
- note_url 应包含小红书详情或 search_result 路径。
```

### 获取关联元素(web)

```text
组件名：获取关联元素(web)
类别：网页元素提取
用途：从父元素、子元素或相邻元素获取关联节点。
常用输入：web_page、current_card
常用输出：current_card_link、current_card_inner
操作手册：
1. 影刀此节点只有父元素、子元素、相邻元素，没有“子孙元素”选项。
2. 如果 DOM 是 section -> div -> a，需要分两级取子元素。
3. 当前小红书卡片方案暂不优先使用该组件，优先直接获取 a.cover 列表。
已知坑：
- 把“子元素”当成“后代元素”会取不到 a。
- 指定位置子元素依赖 DOM 结构，一旦页面改版容易偏。
推荐写法：
优先不用关联元素获取 current_card。
直接用 XPath 获取 a.cover 为 current_card。
验证方式：
- 如必须使用，先打印关联元素是否为空。
```

## 五、文件输出组件

### 数据写入CSV

```text
组件名：数据写入CSV
类别：文件输出
用途：将 row_data_list 批量写入 CSV。
常用输入：row_data_list、book_csv_path
常用输出：CSV 文件
操作手册：
1. 批量写模式下，循环结束后把 row_data_list 写入 book_csv_path。
2. 一行一写模式下禁用该节点。
已知坑：
- 一行一写和批量写同时开启会重复写。
- 如果 row_data_list 为空，最终写入可能无数据或报错。
推荐写法：
调试阶段优先一行一写，稳定后再考虑批量写。
验证方式：
- CSV 文件每采集一条就出现一行。
```

### Python CSV 一行一写

```text
组件名：Python CSV 一行一写
类别：文件输出
用途：每采集一条详情后立即写 CSV。
常用输入：book_csv_path、cleaned_row
常用输出：CSV 文件
操作手册：
1. 第一次创建 CSV 时用 w 模式写表头。
2. 每条 cleaned_row 生成后用 a 模式追加。
3. 禁用 row_data_list 追加和最终数据写入 CSV。
已知坑：
- 如果没有禁用最终数据写入 CSV，可能重复写。
- book_csv_path 必须在当前 keyword 内创建并可访问。
推荐写法：
- `with open(book_csv_path, mode="a", encoding="utf-8-sig", newline="") as f:`
- `writer.writerow(cleaned_row)`
验证方式：
- 流程崩溃后，CSV 仍保留已成功采集的行。
```

## 六、小红书页面对象

### post_link_list

```text
组件名：post_link_list
类别：页面对象列表
用途：当前 DOM 快照中的搜索结果卡片链接列表。
来源：获取相似元素列表(web)
推荐选择器：//section[contains(@class, 'note-item')]//a[contains(@class, 'cover')]
常用当前项：current_card
已知坑：
- 只代表当前 DOM 快照，不能跨滚动长期保存。
- CSS 选择器和 XPath 获取到的对象在影刀点击行为上可能不同。
推荐写法：
每轮滚动重新获取 post_link_list。
```

### current_card

```text
组件名：current_card
类别：页面对象
用途：当前待处理卡片链接。
来源：ForEach post_link_list
常用操作：读取 href、判断去重、点击进入详情。
已知坑：
- 如果 current_card 来自 a.cover，点击中心可能触发图片放大层。
- current_card 是 DOM 对象，不要跨滚动保存。
- href 用 Python get_attribute 更可靠。
推荐写法：
Python 读取 current_card.get_attribute("href")。
影刀 IF 判断 should_click_card > 0 后点击 current_card。
```

### click_title / click_content

```text
组件名：click_title / click_content
类别：页面对象
用途：详情弹窗中的标题和正文元素。
来源：影刀元素库截图或用户后续提供的 DOM 截图。
常用输出：raw_title、raw_content
已知坑：
- 如果点击进入图片放大层，会采集失败。
- 标题/正文可能为空，需开启错误处理。
推荐写法：
获取元素文本内容，失败继续，默认空值。
```

### raw_image_list

```text
组件名：raw_image_list
类别：页面对象列表
用途：详情页图片元素列表。
来源：获取相似元素列表(web)
推荐选择器：//div[contains(@class, 'note-slider-img')]//img
已知坑：
- 选择器在整个 web_page 上查找，误入图片查看器时可能拿到放大层图片。
- 用户已验证第 2 张作为封面更符合当前业务。
推荐写法：
下载图片时用 img_element.get_attribute("src")。
```

## 七、当前小红书工作流经验

### 多关键词

```text
规则：
keywords 放外层。
row_data_list、seen_card_keys、processed_count、no_new_scroll_rounds、stop_current_keyword 放 current_keyword 循环内。
原因：
避免上一个关键词的 stop_current_keyword 和 seen_card_keys 污染下一个关键词。
```

### 去重与点击

```text
规则：
当前去重问题仍在讨论中，不能把 href、note_url 或卡片 text 单独当稳定唯一 ID。
原因是小红书搜索结果是瀑布加载 + 虚拟 DOM，href 和详情 note_url 都可能是临时会话路径，卡片 text 也可能过长或为空。
点击前只能做弱过滤，例如当前 DOM 快照里的弱文本指纹或临时 card_key，用来减少重复点击尝试。
点击后再基于详情采集结果做强去重，候选内容指纹包括清洗后的标题、正文、作者和图片二进制 hash。
影刀 IF 判断 should_click_card > 0。
原因：
避免影刀 IF 不识别 Python False；同时避免把临时 URL 误判为真实唯一 ID。
待办：
继续验证“点击前弱过滤 + 详情后内容指纹强去重”，并确认滚动停止条件是否从 new_count_this_round 改成 unique_write_this_round。
```

### 瀑布流 DOM

```text
规则：
当前窗口获取 DOM -> 处理未见过 current_card -> 丢弃 DOM -> 滚动 -> 重新获取 DOM。
原因：
小红书卡片不是整齐排列，DOM 会随滚动消失、重排或复用。
```

### 点击稳定性

```text
规则：
小红书禁用 JS 点击，不把 JS 点击作为主方案。
优先复用已验证 XPath 获取 post_link_list。
如果点击进入图片放大层，调整点击区域或改点非图片区域；需要用户提供详情弹窗 DOM 和点击交互描述后再定。
```

### 运行环境

```text
规则：
脚本运行时不要移动鼠标、切换窗口、分屏操作其它应用。
原因：
流程使用模拟点击、鼠标滚动、键盘 ESC 和当前激活窗口，焦点错位会导致点击和 ESC 发错对象。
```
