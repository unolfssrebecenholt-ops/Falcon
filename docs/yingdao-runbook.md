# Falcon × 影刀日常运行手册

本手册用于把影刀网页采集结果稳定接入 Falcon。第一版只做低频公开样本采集、分析、日报和人工复核，不自动评论、不自动私信。

配套架构资料见 [影刀 RPA 混合架构开发指南](rpa-elements/yingdao-hybrid-architecture-guide.md)。遇到动态选择器、SPA 弹窗、点击遮挡、非唯一匹配、Python 变量回写等问题时，先按该指南排查。

## 1. 影刀流程参数

影刀流程里保留这些流程参数，换机器或换主题时只改参数：

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `output_dir` | `F:\projects\Falcon\data` | 影刀 xlsx 导出目录 |
| `output_filename` | `xhs_raw_export.xlsx` | 影刀 xlsx 文件名 |
| `keyword` | `小红书封面` | 当前搜索词 |
| `max_search_items` | `50` | 当前关键词最多采集搜索结果数 |
| `search_scroll_times` | `5` | 搜索结果页最大滚动次数 |
| `detail_open_limit` | `10` | 当前关键词最多打开详情页数量 |
| `comment_top_limit` | `15` | 每篇笔记最多采集热度靠前评论数 |
| `comment_scroll_times` | `3` | 评论区最大滚动次数 |

PD 虚拟 Windows 或另一台 Windows 机器只需要改 `output_dir`。不要把路径写入 Falcon 代码。

## 2. 影刀采集质量升级流程

第一版不追求全量抓取，只追求稳定拿到高价值公开样本。推荐流程：

1. 打开小红书搜索页，输入流程参数 `keyword`。
2. 循环滚动搜索结果页，直到满足任一条件：
   - 已收集链接数达到 `max_search_items`。
   - 已滚动 `search_scroll_times` 次。
   - 连续 2 次滚动后没有新增笔记链接。
3. 去重笔记链接，只保留小红书笔记详情链接。
4. 按顺序打开前 `detail_open_limit` 篇笔记详情页。
5. 优先通过“点击卡片 -> 等待弹窗渲染 -> 读取当前地址栏 URL”的方式进入详情，不批量直接跳转 URL。
6. 在详情页采集：
   - 笔记标题。
   - 笔记正文。
   - 作者。
   - 当前笔记 URL。
7. 打开或定位评论区，按页面默认顺序采集热度靠前评论：
   - 最多采集 `comment_top_limit` 条。
   - 最多滚动 `comment_scroll_times` 次。
   - 如果页面不暴露真实点赞数，`comment_rank` 记录展示顺序。
8. 用 `{Esc}` 关闭 SPA 弹窗，回到搜索结果页继续处理下一张卡片。
9. 导出统一 xlsx，建议表头如下：

```csv
platform,keyword,source_type,title,content,url,parent_url,author,commenter,like_count,comment_rank,collected_at
```

其中：

- 笔记正文行：`source_type=post`，`content` 放正文，`author` 放作者，`parent_url/commenter/comment_rank` 可为空。
- 评论行：`source_type=comment`，`content` 放评论文本，`parent_url` 放所属笔记链接，`commenter` 放评论用户，`comment_rank` 放热评顺序。
- `platform` 固定为 `xiaohongshu`。
- `keyword` 使用当前流程参数，不要写死在影刀节点里。

流程内建议先用 `新建列表` 声明 `row_data_list`。循环中由可视化流程捕获元素和字段，Python 代码段负责清洗并 `row_data_list.append(row)`；循环结束后再一次性写入 xlsx/CSV。

## 3. 关键词池

首次运行时生成本地关键词池：

```powershell
py -3 -m falcon write-keyword-pool data\rpa_keywords.csv --theme "生图小程序"
```

`data/` 已被 `.gitignore` 忽略。关键词池是本机运行数据，不提交到 GitHub。

字段：

```csv
theme,keyword,scene,weight,daily_limit
```

第一版按 `daily_limit` 控制每天每个关键词的采样量。关键词池会同时包含：

- 场景词：小红书封面、标题图、AI头像、活动海报等。
- 程序名意图词：例如 `生图小程序不好用`、`求推荐更好用的生图工具`、`生图小程序平替`。

影刀当前先手工读取关键词；后续如影刀支持读取 CSV，再把 `data\rpa_keywords.csv` 作为输入表。

## 4. 每日采集

影刀侧：

1. 打开“小红书截流”流程。
2. 设置 `keyword`。
3. 设置 `output_dir` 和 `output_filename`。
4. 设置 `max_search_items/detail_open_limit/comment_top_limit`。
5. 运行流程，导出 xlsx。
5. 确认文件存在，例如 `data\xhs_raw_export.xlsx`。

Falcon 侧一条命令完成导入、分析、日报：

```powershell
py -3 -m falcon --db data\falcon.sqlite3 run-yingdao-daily data\xhs_raw_export.xlsx --keyword "生图小程序" --report-output reports\daily-report.md
```

如果只想分步排查，可以运行：

```powershell
py -3 -m falcon --db data\falcon.sqlite3 import-yingdao-xlsx data\xhs_raw_export.xlsx --keyword "生图小程序"
py -3 -m falcon --db data\falcon.sqlite3 analyze --drafts template
py -3 -m falcon --db data\falcon.sqlite3 report --output reports\daily-report.md
```

## 5. Windows 分段定时调度

推荐先让影刀负责定时采集，Windows 任务计划负责 Falcon 导入分析，两段分开排错。

Falcon 侧可以创建一个本地 PowerShell 脚本，例如 `run-falcon-daily.ps1`：

```powershell
cd F:\projects\Falcon
py -3 -m falcon --db data\falcon.sqlite3 run-yingdao-daily data\xhs_raw_export.xlsx --keyword "生图小程序" --report-output reports\daily-report.md *> logs\falcon-daily.log
```

注意：

- `logs/` 属于本地运行日志，不提交仓库。
- 任务计划触发时间应晚于影刀导出完成时间。
- 如果影刀当天没有导出新文件，先不要删除旧文件，避免 Falcon 分析空输入。

## 6. 人工复核

打开 `reports\daily-report.md`，优先看 Top 样本和触达任务箱。日报中的 `raw_id` 用于记录复核结果：

```powershell
py -3 -m falcon --db data\falcon.sqlite3 review-raw-item 12 有用 --note "可做封面教程选题"
py -3 -m falcon --db data\falcon.sqlite3 review-raw-item 15 噪音 --note "只是泛泛夸图"
```

允许的标记：

- `优秀`
- `有用`
- `一般`
- `无用`
- `噪音`

触达任务处理后，用原有任务状态流转：

```powershell
py -3 -m falcon --db data\falcon.sqlite3 review-task 3 handled --feedback "已人工处理"
```

## 7. 7 天稳定运行记录

每天结束后在 `docs/progress.md` 更新：

- 今日采集条数。
- 有效样本数。
- Top 20 中 `优秀/有用` 数量。
- 触达任务数。
- 明天要增删的关键词。
- Windows/Mac 或 PD 虚拟 Windows 的路径注意事项。

7 天目标：

- 每天稳定采集 50-100 条公开样本。
- 每天产出 3-5 个可发布选题。
- Top 20 中 `优秀/有用` 比例接近 70%。
- 每天生成 5-15 条可人工处理触达任务。
