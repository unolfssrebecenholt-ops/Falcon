import tempfile
import unittest
from pathlib import Path

from falcon.db import FalconRepository
from falcon.models import RawItem
from falcon.workflows import analyze_unanalyzed, write_report


class WorkflowTest(unittest.TestCase):
    def test_analyze_and_report_workflow_uses_repository_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            report_path = tmp_path / "daily-report.md"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    source_type="post",
                    title="小红书封面怎么做才有人点？",
                    content="想找一个能直接生成封面标题图的工具。",
                    url="local://seed/1",
                )
            )

            result = analyze_unanalyzed(repo, drafts_mode="template")
            output = write_report(repo, report_path)

            self.assertEqual(result.analyzed_count, 1)
            self.assertEqual(output, report_path)
            self.assertTrue(report_path.exists())
            self.assertIn("Falcon 日报", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
