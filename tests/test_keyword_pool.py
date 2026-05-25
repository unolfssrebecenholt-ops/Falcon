import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from falcon.cli import main
from falcon.keyword_pool import generate_program_keyword_tasks, load_keyword_tasks, write_default_keyword_pool


class KeywordPoolTest(unittest.TestCase):
    def test_writes_default_keyword_pool_for_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "collection_keywords.csv"

            write_default_keyword_pool(path, theme="内容运营")

            tasks = load_keyword_tasks(path)
            self.assertGreaterEqual(len(tasks), 6)
            self.assertEqual(tasks[0].theme, "内容运营")
            self.assertEqual(tasks[0].keyword, "内容运营自动化")
            self.assertEqual(tasks[0].scene, "workflow")
            self.assertEqual(tasks[0].weight, 10)
            self.assertEqual(tasks[0].daily_limit, 20)
            self.assertIn("账号增长策略", [task.keyword for task in tasks])

    def test_cli_writes_keyword_pool_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "collection_keywords.csv"

            with redirect_stdout(io.StringIO()):
                exit_code = main(["write-keyword-pool", str(path), "--theme", "内容运营"])

            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(exit_code, 0)
            self.assertEqual(rows[0]["theme"], "内容运营")
            self.assertEqual(rows[0]["keyword"], "内容运营自动化")
            self.assertEqual(rows[0]["daily_limit"], "20")

    def test_generates_program_name_search_intent_keywords(self):
        tasks = generate_program_keyword_tasks("内容运营")
        keywords = [task.keyword for task in tasks]

        self.assertIn("内容运营怎么做", keywords)
        self.assertIn("内容运营工具推荐", keywords)
        self.assertIn("有没有好用的内容运营工具", keywords)
        self.assertIn("内容运营自动化", keywords)
        self.assertIn("内容运营复盘模板", keywords)


if __name__ == "__main__":
    unittest.main()
