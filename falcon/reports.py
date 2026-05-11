from datetime import date
from typing import List

from .db import FalconRepository


class DailyReportBuilder:
    def __init__(self, repo: FalconRepository, summary_client=None):
        self.repo = repo
        self.summary_client = summary_client

    def build_markdown(self, report_date: str = "") -> str:
        report_date = report_date or date.today().isoformat()
        keyword_stats = self.repo.keyword_stats()
        scored_items = self.repo.list_scored_items(limit=20)
        tasks = self.repo.list_outreach_tasks(status="pending", limit=15)

        lines: List[str] = [
            f"# Falcon 日报 - {report_date}",
            "",
            "## 今日关键词表现",
        ]
        if keyword_stats:
            for stat in keyword_stats[:10]:
                lines.append(
                    f"- {stat['keyword']}：样本 {stat['total']}，平均意图 {stat['avg_intent'] or 0}，高意图 {stat['high_intent'] or 0}"
                )
        else:
            lines.append("- 暂无样本。")

        lines.extend(["", "## 小红书封面主报告"])
        xhs_items = [item for item in scored_items if item["scene_tag"] == "xhs_cover"]
        if xhs_items:
            seen_topics = set()
            for item in xhs_items:
                topic = item["suggested_topic"]
                if topic in seen_topics:
                    continue
                seen_topics.add(topic)
                lines.append(f"- 选题：{topic}（意图 {item['intent_score']}）")
        else:
            lines.append("- 暂无高价值小红书封面样本。")

        lines.extend(["", "## 其他入口探针"])
        probes = [item for item in scored_items if item["scene_tag"] != "xhs_cover"]
        if probes:
            for item in probes[:8]:
                lines.append(
                    f"- {item['scene_tag']}：{item['suggested_topic']}（意图 {item['intent_score']}，来源 {item['url']}）"
                )
        else:
            lines.append("- 今日未发现强探针信号。")

        summary = self._build_summary(keyword_stats, scored_items, tasks)
        if summary:
            lines.extend(["", "## GPT-5.5 总结", summary])

        lines.extend(["", "## 触达任务箱"])
        if tasks:
            for task in tasks:
                lines.append(f"- [{task.outreach_priority}] {task.title} - {task.url}")
                for draft in task.drafts:
                    lines.append(f"  - {draft.kind}: {draft.text}")
                if task.risk_note:
                    lines.append(f"  - risk_note: {task.risk_note}")
        else:
            lines.append("- 暂无待处理触达任务。")

        lines.extend(
            [
                "",
                "## 人工复核区",
                "- 请将 Top 样本标记为：优秀 / 有用 / 一般 / 无用。",
                "- 标记草稿是否可直接使用、需轻改、不可用。",
            ]
        )
        return "\n".join(lines) + "\n"

    def _build_summary(self, keyword_stats, scored_items, tasks) -> str:
        if self.summary_client is None:
            return ""
        payload = {
            "keywords": keyword_stats[:10],
            "top_items": scored_items[:10],
            "pending_task_count": len(tasks),
        }
        result = self.summary_client.complete_json(
            system_prompt=(
                "你是 Falcon 日报总结助手。请用一句中文总结今天最值得做的增长动作。"
                "只输出 JSON，例如 {\"summary\":\"...\"}。"
            ),
            user_prompt=str(payload),
        )
        return str(result.get("summary", "")).strip()
