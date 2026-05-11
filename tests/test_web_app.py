import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from falcon.analysis import AnalysisResult
from falcon.cli import build_parser
from falcon.db import FalconRepository
from falcon.models import Draft, RawItem
from falcon.web.app import create_app
from tests.test_yingdao_xlsx import write_minimal_xlsx


class WebAppTest(unittest.TestCase):
    def test_cli_accepts_web_command(self):
        args = build_parser().parse_args(
            ["--db", "data/falcon.sqlite3", "web", "--host", "127.0.0.1", "--port", "8765"]
        )

        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8765)

    def test_cli_accepts_web_db_after_subcommand(self):
        args = build_parser().parse_args(
            ["web", "--host", "127.0.0.1", "--port", "8765", "--db", "data/falcon.sqlite3"]
        )

        self.assertEqual(args.command, "web")
        self.assertEqual(args.web_db, "data/falcon.sqlite3")

    def test_dashboard_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            app = create_app(db_path)
            client = TestClient(app)

            response = client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn("Falcon 控制台", response.text)

    def test_run_daily_post_imports_analyzes_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            xlsx_path = tmp_path / "xhs_raw_export.xlsx"
            report_path = tmp_path / "daily-report.md"
            write_minimal_xlsx(
                xlsx_path,
                [["小红书封面怎么做才有人点？", "https://www.xiaohongshu.com/search_result/1"]],
            )
            client = TestClient(create_app(db_path))

            response = client.post(
                "/run",
                data={
                    "xlsx_path": str(xlsx_path),
                    "keyword": "生图小程序",
                    "drafts": "template",
                    "report_output": str(report_path),
                },
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertTrue(report_path.exists())
            self.assertEqual(len(FalconRepository(db_path).list_raw_items()), 1)

    def test_init_db_post_creates_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.post("/init-db", follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertTrue(db_path.exists())

    def test_report_page_reads_markdown_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            report_path = tmp_path / "daily-report.md"
            report_path.write_text("# Falcon 日报\n\n今日样本。", encoding="utf-8")
            client = TestClient(create_app(db_path))

            response = client.get("/report", params={"path": str(report_path)})

            self.assertEqual(response.status_code, 200)
            self.assertIn("Falcon 日报", response.text)
            self.assertIn("今日样本。", response.text)

    def test_run_daily_post_records_error_for_missing_xlsx(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.post(
                "/run",
                data={
                    "xlsx_path": str(tmp_path / "missing.xlsx"),
                    "keyword": "生图小程序",
                    "drafts": "template",
                    "report_output": str(tmp_path / "daily-report.md"),
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("运行失败", response.text)

    def test_review_raw_item_post_records_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    source_type="post",
                    title="封面怎么做",
                    content="封面怎么做",
                    url="https://example.com/1",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.post(
                f"/review/raw/{raw_id}",
                data={"feedback": "有用", "note": "可做选题"},
                follow_redirects=False,
            )

            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute("SELECT raw_item_id, human_feedback, note FROM review_feedback").fetchone()
            self.assertEqual(response.status_code, 303)
            self.assertEqual(row, (raw_id, "有用", "可做选题"))

    def test_task_status_post_updates_outreach_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    source_type="post",
                    title="封面怎么做",
                    content="封面怎么做",
                    url="https://example.com/1",
                )
            )
            analysis = AnalysisResult(
                scene_tag="xhs_cover",
                intent_score=90,
                content_value_score=80,
                pain_point="封面点击率低",
                suggested_topic="封面怎么做",
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
                [Draft(kind="comment_reply", text="可以先缩短标题。")],
                risk_note="人工确认",
            )
            client = TestClient(create_app(db_path))

            response = client.post(
                f"/tasks/{task_id}/status",
                data={"status": "handled"},
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertEqual(repo.list_outreach_tasks()[0].task_status, "handled")


if __name__ == "__main__":
    unittest.main()
