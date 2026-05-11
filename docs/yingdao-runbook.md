# Falcon × 影刀日常运行手册

本手册用于把影刀网页采集结果稳定接入 Falcon。第一版只做低频公开样本采集、分析、日报和人工复核，不自动评论、不自动私信。

## 1. 影刀流程参数

影刀流程里保留这些流程参数，换机器或换主题时只改参数：

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `output_dir` | `F:\projects\Falcon\data` | 影刀 xlsx 导出目录 |
| `output_filename` | `xhs_raw_export.xlsx` | 影刀 xlsx 文件名 |
| `keyword` | `小红书封面` | 当前搜索词 |
| `max_items` | `50` | 当前关键词最多采集条数 |
| `scroll_times` | `5` | 搜索结果页滚动加载次数 |

PD 虚拟 Windows 或另一台 Windows 机器只需要改 `output_dir`。不要把路径写入 Falcon 代码。

## 2. 关键词池

首次运行时生成本地关键词池：

```powershell
py -3 -m falcon write-keyword-pool data\rpa_keywords.csv --theme "生图小程序"
```

`data/` 已被 `.gitignore` 忽略。关键词池是本机运行数据，不提交到 GitHub。

字段：

```csv
theme,keyword,scene,weight,daily_limit
```

第一版按 `daily_limit` 控制每天每个关键词的采样量。影刀当前先手工读取关键词；后续如影刀支持读取 CSV，再把 `data\rpa_keywords.csv` 作为输入表。

## 3. 每日采集

影刀侧：

1. 打开“小红书截流”流程。
2. 设置 `keyword`。
3. 设置 `output_dir` 和 `output_filename`。
4. 运行流程，导出 xlsx。
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

## 4. 人工复核

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

## 5. 7 天稳定运行记录

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
