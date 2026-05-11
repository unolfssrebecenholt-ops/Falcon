# Falcon 第一版完整方案：需求雷达 + AI 触达任务箱

## 1. 项目定位

Falcon 第一版服务于 `AI出图助手`，定位为小红书优先的社媒需求雷达和内容截流辅助系统。

第一版不做低价产品的销售 CRM，不自动发送评论或私信。系统只负责低频采集公开可见样本、分析需求、生成日报和触达草稿，最终处理由人工确认。

## 2. 第一版范围

- 平台：只接入小红书，代码结构预留其他平台适配器。
- 主推场景：小红书封面，占主要采样和分析资源。
- 探针场景：活动海报、微信头像、朋友圈背景、随便画画，做少量机会探测。
- 数据中枢：SQLite。
- 采集接口：RPA 或人工整理 CSV 导入。
- AI 草稿：可接 GPT-5.5 OpenAI 兼容中转站；未配置时使用保守模板。

## 3. 模块

### RPA 采集层

影刀或其他 RPA 低频采集公开可见的小红书搜索结果、帖子和评论，导出 CSV 后由 Falcon 入库。

### AI 分析层

分析器输出：

- `scene_tag`
- `intent_score`
- `content_value_score`
- `pain_point`
- `suggested_topic`
- `recommended_action`
- `outreach_type`
- `reason`

### AI 触达任务箱

高价值样本会进入任务箱。每条任务包含来源链接、原始内容、触达建议、风险提示和 1-3 条草稿。

任务状态：

- `pending`
- `copied`
- `handled`
- `skipped`
- `invalid`

### 日报层

每日输出 Markdown 报告：

- 今日关键词表现。
- 小红书封面主报告。
- 其他入口探针。
- 触达任务箱。
- 人工复核区。

## 4. 运行方式

```bash
python3 -m falcon --db data/falcon.sqlite3 init-db
python3 -m falcon --db data/falcon.sqlite3 import-csv examples/xiaohongshu_samples.csv
python3 -m falcon --db data/falcon.sqlite3 analyze --drafts template
python3 -m falcon --db data/falcon.sqlite3 report --output reports/daily-report.md
```

如需 GPT-5.5 中转站生成草稿，配置：

```bash
export FALCON_GPT_BASE_URL="https://your-gpt55-relay.example.com"
export FALCON_GPT_ENDPOINT="/v1/chat/completions"
export FALCON_GPT_API_KEY="..."
export FALCON_GPT_MODEL="gpt-5.5"
```

然后运行：

```bash
python3 -m falcon --db data/falcon.sqlite3 analyze --drafts gpt
```

## 5. 成功标准

第一阶段：

- 连续 7 天稳定采集小红书样本。
- 每天产出 3-5 个可发布选题。
- Top 20 高分样本中，人工判定“优秀/有用”比例达到 70% 以上。
- 每天生成 5-15 条可人工处理的触达任务。
- AI 草稿中至少 60% 经轻微修改即可使用。

第二阶段：

- Falcon 推荐选题能带来内容互动或小程序访问。
- 人工处理过的评论/私信任务能带来有效反馈。
- 小程序上线后，可追踪访问、生成、首购数据并反哺评分。

## 6. 边界

- 不自动发送评论或私信。
- 不做批量触达。
- 不以规避平台规则为目标。
- 不改动 `Image-sp` 小程序代码。
- 真实 API Key 只放本地环境变量或服务端环境变量，不写入仓库。
