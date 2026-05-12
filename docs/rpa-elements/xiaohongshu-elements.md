# 小红书影刀元素清单

本文件用于沉淀用户从影刀元素库截图中提供的元素。Codex 后续根据本文件和同目录 JSON 清单，把影刀元素组织成可执行的流程链条。

## 使用方式

1. 用户发送影刀“元素库/元素列表”截图。
2. Codex 从截图中识别元素名称、所属页面、可能用途和字段映射。
3. Codex 更新本文件的人类可读清单，并同步更新 `xiaohongshu-elements.json`。
4. 后续搭建流程时，优先复用已归档元素，不重新发明变量名。

## 命名约定

| 前缀 | 含义 | 示例 |
| --- | --- | --- |
| `search_` | 搜索页输入或按钮 | `search_input` |
| `result_` | 搜索结果列表/卡片 | `result_card` |
| `post_` | 帖子卡片或详情页字段 | `post_title` |
| `comment_` | 评论区字段 | `comment_text` |
| `nav_` | 返回、关闭、翻页等导航动作 | `nav_close_detail` |
| `table_` | 数据表格或 Excel 写入相关 | `table_append_row` |

## 元素状态

| 状态 | 含义 |
| --- | --- |
| `candidate` | 从截图初步识别，尚未跑通 |
| `verified` | 已在影刀流程中验证可用 |
| `unstable` | 偶尔失效，需要备用方案 |
| `deprecated` | 不再使用，保留历史记录 |

## 当前元素

暂未归档小红书网页元素。当前已归档的是影刀指令目录，见：

- `docs/rpa-elements/yingdao-command-catalog.md`
- `docs/rpa-elements/yingdao-command-catalog.json`

请继续发送小红书页面的影刀元素库截图后更新，例如搜索框、结果卡片、标题、链接、评论文本等。

## 待归档网页元素

| 建议变量名 | 类型 | 用途 | 当前状态 |
| --- | --- | --- | --- |
| `search_input` | web element | 输入当前关键词 | waiting_for_screenshot |
| `result_card` | similar web element | 搜索结果帖子卡片 | waiting_for_screenshot |
| `post_title` | related web element | 提取帖子标题 | waiting_for_screenshot |
| `post_summary` | related web element | 提取帖子摘要/正文片段 | waiting_for_screenshot |
| `post_link` | related web element | 提取原始链接或 href | waiting_for_screenshot |
| `post_time` | related web element | 提取发布时间，可空 | waiting_for_screenshot |
| `comment_text` | similar web element | 提取公开评论文本 | waiting_for_screenshot |
| `comment_time` | related web element | 提取评论时间，可空 | waiting_for_screenshot |
| `detail_close` | web element | 关闭详情页或返回搜索结果 | waiting_for_screenshot |

## 目标链条

```text
xhs_page
-> search_input
-> current_keyword
-> result_card_list
-> current_card
-> post_title / post_summary / post_url / post_time
-> optional comment_text
-> row_data
-> data_table_or_excel
-> CSV
-> Falcon import-csv
```
