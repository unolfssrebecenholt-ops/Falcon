import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from falcon.cli import main
from falcon.db import FalconRepository
from tests.test_yingdao_xlsx import write_minimal_xlsx


class DailyYingdaoWorkflowTest(unittest.TestCase):
    def test_cli_runs_import_analyze_and_report_for_yingdao_xlsx(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            xlsx_path = tmp_path / "xhs_raw_export.xlsx"
            db_path = tmp_path / "falcon.sqlite3"
            report_path = tmp_path / "daily-report.md"
            write_minimal_xlsx(
                xlsx_path,
                [
                    ["小红书封面怎么做才有人点？", "https://www.xiaohongshu.com/search_result/1"],
                    ["路过看看这个颜色好可爱", "https://www.xiaohongshu.com/search_result/2"],
                ],
            )

            with redirect_stdout(io.StringIO()) as output:
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "run-yingdao-daily",
                        str(xlsx_path),
                        "--keyword",
                        "生图小程序",
                        "--report-output",
                        str(report_path),
                    ]
                )

            items = FalconRepository(db_path).list_raw_items()
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(items), 2)
            self.assertTrue(report_path.exists())
            self.assertIn("Imported 2 unique items", output.getvalue())
            self.assertIn("Analyzed 2 items", output.getvalue())
            self.assertIn("Wrote", output.getvalue())
            self.assertIn("Falcon 日报", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
