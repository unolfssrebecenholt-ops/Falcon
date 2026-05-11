# 小红书 RPA 接入说明

第一版目标是低频需求采样，不做高频抓取、不做自动评论发送、不做自动私信发送。

## 采样范围

- 平台：小红书。
- 主场景：小红书封面。
- 探针场景：活动海报、微信头像、朋友圈背景、随便画画。
- 建议每日样本：50-100 条。
- 建议人工复核：Top 20-30 条。

## CSV 字段

Falcon 支持英文或中文表头。

| Falcon 字段 | 可用表头 | 说明 |
| --- | --- | --- |
| `platform` | `platform`、`平台` | 默认 `xiaohongshu` |
| `keyword` | `keyword`、`关键词`、`搜索词` | RPA 搜索词 |
| `source_type` | `source_type`、`类型`、`来源类型` | `post` 或 `comment` |
| `title` | `title`、`标题`、`帖子标题` | 帖子标题 |
| `content` | `content`、`正文`、`内容`、`评论`、`评论内容` | 正文或评论文本 |
| `url` | `url`、`链接`、`来源链接` | 原始内容链接 |
| `published_at` | `published_at`、`发布时间`、`时间` | 可留空 |

## 示例

```csv
platform,keyword,source_type,title,content,url,published_at
xiaohongshu,小红书封面,comment,笔记没人点,小红书封面怎么做才有人点？有没有自动生成标题图的工具,https://example.com/note/1,2026-05-11
```

## 影刀 xlsx 导出

影刀“批量数据抓取”可以先导出两列表格，Falcon 支持直接导入这种 xlsx：

| 影刀列 | 含义 | Falcon 映射 |
| --- | --- | --- |
| A | 搜索结果标题或摘要 | `title` 和 `content` |
| B | 搜索结果链接 | `url` |

导入时必须显式传入本次采样关键词或主题，不在影刀流程或 Falcon 代码里写死：

Windows PowerShell:

```powershell
py -3 -m falcon --db data\falcon.sqlite3 import-yingdao-xlsx data\xhs_raw_export.xlsx --keyword "生图小程序"
```

macOS:

```bash
python3 -m falcon --db data/falcon.sqlite3 import-yingdao-xlsx data/xhs_raw_export.xlsx --keyword "生图小程序"
```

默认映射为 `platform=xiaohongshu`、`source_type=post`、`published_at` 留空。如后续影刀改成采集评论，可追加 `--source-type comment`。

## 推荐关键词

主线关键词：

- 小红书封面
- 小红书标题图
- 笔记没人看
- 封面怎么做
- 爆款封面
- 小红书封面模板

探针关键词：

- AI头像
- 微信头像生成
- 活动海报
- 门店海报
- 朋友圈背景图
- AI生图小程序

## 操作边界

- 只采集公开可见内容。
- 不把规避平台规则作为系统能力。
- 触达任务只生成草稿和链接，由人工确认处理。
- 私信文案必须克制，不承诺效果，不批量发送。
