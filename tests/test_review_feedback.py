import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
import io
from pathlib import Path

from falcon.cli import main
from falcon.db import FalconRepository
from falcon.models import RawItem


class ReviewFeedbackCliTest(unittest.TestCase):
    def test_cli_records_raw_item_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    source_type="post",
                    title="小红书封面怎么做",
                    content="小红书封面怎么做",
                    url="https://example.com/1",
                )
            )

            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "review-raw-item",
                        str(raw_id),
                        "有用",
                        "--note",
                        "可以作为选题",
                    ]
                )

            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute("SELECT raw_item_id, human_feedback, note FROM review_feedback").fetchone()
            self.assertEqual(exit_code, 0)
            self.assertEqual(row, (raw_id, "有用", "可以作为选题"))


if __name__ == "__main__":
    unittest.main()
