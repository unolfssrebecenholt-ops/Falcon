import tempfile
import unittest
from pathlib import Path

from falcon.analysis import AnalysisResult
from falcon.db import FalconRepository
from falcon.models import Draft, RawItem


class FalconRepositoryTest(unittest.TestCase):
    def test_initializes_schema_and_deduplicates_raw_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()

            item = RawItem(
                platform="xiaohongshu",
                keyword="内容表现",
                source_type="comment",
                title="内容求助",
                content="标题怎么做？",
                url="https://example.com/note/1",
                published_at="2026-05-11",
            )

            first_id = repo.upsert_raw_item(item)
            second_id = repo.upsert_raw_item(item)
            items = repo.list_raw_items()

            self.assertEqual(first_id, second_id)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].keyword, "内容表现")

    def test_saves_analysis_and_outreach_task_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="内容表现",
                    source_type="comment",
                    title="内容求助",
                    content="标题怎么做才有人点？",
                    url="https://example.com/note/1",
                    published_at="2026-05-11",
                )
            )
            analysis = AnalysisResult(
                scene_tag="content_performance",
                intent_score=88,
                content_value_score=82,
                pain_point="不会优化内容表现",
                suggested_topic="内容没人点？3 个表达结构方法",
                recommended_action="comment_reply",
                outreach_type="comment_reply",
                outreach_priority="high",
                reason="明确求助",
            )
            analysis_id = repo.save_analysis(raw_id, analysis)
            task_id = repo.create_outreach_task(
                raw_id,
                analysis_id,
                analysis,
                [
                    Draft(kind="comment_reply", text="可以先把标题做短一点。"),
                    Draft(kind="private_message", text="看到你在研究封面，可以给你一个思路。"),
                ],
                risk_note="语气保持克制",
            )

            tasks = repo.list_outreach_tasks()

            self.assertIsInstance(task_id, int)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].task_status, "pending")
            self.assertEqual(tasks[0].outreach_priority, "high")
            self.assertEqual(tasks[0].drafts[0].kind, "comment_reply")


if __name__ == "__main__":
    unittest.main()
