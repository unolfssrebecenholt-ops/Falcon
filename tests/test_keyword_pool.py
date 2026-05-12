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
            path = Path(tmp) / "rpa_keywords.csv"

            write_default_keyword_pool(path, theme="生图小程序")

            tasks = load_keyword_tasks(path)
            self.assertGreaterEqual(len(tasks), 6)
            self.assertEqual(tasks[0].theme, "生图小程序")
            self.assertEqual(tasks[0].keyword, "小红书封面")
            self.assertEqual(tasks[0].scene, "cover")
            self.assertEqual(tasks[0].weight, 10)
            self.assertEqual(tasks[0].daily_limit, 20)
            self.assertIn("AI头像", [task.keyword for task in tasks])

    def test_cli_writes_keyword_pool_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rpa_keywords.csv"

            with redirect_stdout(io.StringIO()):
                exit_code = main(["write-keyword-pool", str(path), "--theme", "生图小程序"])

            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(exit_code, 0)
            self.assertEqual(rows[0]["theme"], "生图小程序")
            self.assertEqual(rows[0]["keyword"], "小红书封面")
            self.assertEqual(rows[0]["daily_limit"], "20")

    def test_generates_program_name_search_intent_keywords(self):
        tasks = generate_program_keyword_tasks("生图小程序")
        keywords = [task.keyword for task in tasks]

        self.assertIn("生图小程序不好用", keywords)
        self.assertIn("求推荐更好用的生图工具", keywords)
        self.assertIn("有没有好用的生图小程序", keywords)
        self.assertIn("生图小程序平替", keywords)
        self.assertIn("小红书封面生图工具", keywords)


if __name__ == "__main__":
    unittest.main()
