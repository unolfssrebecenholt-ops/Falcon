import tempfile
import unittest
from pathlib import Path

from falcon.db import FalconRepository
from falcon.workflows import run_yingdao_daily
from tests.test_yingdao_xlsx import write_minimal_xlsx


class WorkflowTest(unittest.TestCase):
    def test_run_yingdao_daily_imports_analyzes_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            xlsx_path = tmp_path / "xhs_raw_export.xlsx"
            report_path = tmp_path / "daily-report.md"
            write_minimal_xlsx(
                xlsx_path,
                [["小红书封面怎么做才有人点？", "https://www.xiaohongshu.com/search_result/1"]],
            )
            repo = FalconRepository(db_path)
            repo.init_schema()

            result = run_yingdao_daily(
                repo,
                xlsx_path=xlsx_path,
                keyword="生图小程序",
                report_output=report_path,
                drafts_mode="template",
            )

            self.assertEqual(result.imported_count, 1)
            self.assertEqual(result.analyzed_count, 1)
            self.assertEqual(result.report_path, report_path)
            self.assertTrue(report_path.exists())
            self.assertIn("Falcon 日报", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
