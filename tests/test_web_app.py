import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from falcon.analysis import AnalysisResult
from falcon.cli import build_parser
from falcon.db import FalconRepository
from falcon.doctor import DoctorCheck, DoctorReport
from falcon.models import (
    CollectedComment,
    CollectedPost,
    CollectionEvent,
    CollectionRun,
    Draft,
    Evidence,
    MediaAsset,
    RawItem,
)
from falcon.web.app import create_app


LEGACY_COLLECTION_MARKERS = ("".join(chr(code) for code in (24433, 20992)), "R" + "PA")


def assert_no_legacy_collection_markers(test_case: unittest.TestCase, content: str) -> None:
    for marker in LEGACY_COLLECTION_MARKERS:
        test_case.assertNotIn(marker, content)


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

    def test_keywords_page_renders_collection_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/keywords")

            self.assertEqual(response.status_code, 200)
            self.assertIn("Falcon Agent 采集计划", response.text)

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

    def test_collector_overview_renders_current_information_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-running",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="running",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-latest-completed",
                    platform="xiaohongshu",
                    keyword="AI avatar",
                    profile="default",
                    status="completed",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn("采集总览", response.text)
            self.assertIn("平台入口", response.text)
            self.assertIn('class="running-attention-banner"', response.text)
            self.assertIn('class="platform-card active has-running"', response.text)
            self.assertIn("xhs-running", response.text)
            self.assertIn('class="panel recent-runs-panel"', response.text)
            self.assertLess(
                response.text.index('class="panel recent-runs-panel"'),
                response.text.index('class="overview-column overview-column-right"'),
            )
            self.assertNotIn('class="flow-grid"', response.text)
            self.assertNotIn('class="panel overview-entry-panel"', response.text)
            assert_no_legacy_collection_markers(self, response.text)

    def test_collector_overview_uses_huashu_queue_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            for index in range(12):
                repo.create_collection_run(
                    CollectionRun(
                        run_id=f"xhs-list-{index}",
                        platform="xiaohongshu",
                        keyword=f"keyword-{index}",
                        profile="default",
                        status="completed" if index % 2 else "failed",
                        created_at=f"2026-05-23T0{index % 9}:00:00+00:00",
                    )
                )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs")

            self.assertEqual(response.status_code, 200)
            self.assertIn("任务队列", response.text)
            self.assertIn("任务开启日期范围", response.text)
            self.assertIn('id="queue-calendar-panel"', response.text)
            self.assertIn('data-platform-filter="xiaohongshu"', response.text)
            self.assertIn('class="queue-wrap"', response.text)

    def test_collector_overview_compacts_cards_and_removes_queue_horizontal_scroll(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-compact-manual",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="creator",
                    status="manual_action_required",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs")
            css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
                encoding="utf-8"
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="queue-action-primary"', response.text)
            self.assertIn('class="queue-action-more"', response.text)
            self.assertIn("align-items: stretch", css)
            self.assertIn("table-layout: fixed", css)
            self.assertIn(".queue-wrap td:nth-child(9) {\n  overflow: visible;", css)
            self.assertNotIn("min-width: 1240px", css)

    def test_web_theme_uses_slate_command_stone_moss_palette_without_neon_grid(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )
        base_template = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "templates" / "base.html").read_text(
            encoding="utf-8"
        )

        body_rule = css[css.index("body {") : css.index(".inline-link {")]
        sidebar_rule = css[css.index(".sidebar {") : css.index(".brand {")]

        self.assertIn("--bg: #1a252c;", css)
        self.assertIn("--panel: #24333c;", css)
        self.assertIn("--accent: #748876;", css)
        self.assertIn("--accent-dark: #5f7162;", css)
        self.assertIn("--blue: #76a5c5;", css)
        self.assertIn("--amber: #d1a24d;", css)
        self.assertIn("--danger: #df6767;", css)
        self.assertIn("--ok: #85957f;", css)
        self.assertNotIn("radial-gradient(circle at 1px 1px", body_rule)
        self.assertNotIn("radial-gradient(circle at 1px 1px", sidebar_rule)
        self.assertNotIn("#060807", css)
        self.assertNotIn("#a6ff63", css)
        self.assertNotIn("#6fc17b", css)
        self.assertNotIn("#87d994", css)
        self.assertNotIn("#8fb68f", css)
        self.assertNotIn("#9fbd8f", css)
        self.assertNotIn("graphite-sage-all-pages-20260524", base_template)
        self.assertNotIn("slate-command-reference-pages-20260524", base_template)
        self.assertNotIn("slate-command-soft-sage-pages-20260524", base_template)
        self.assertIn("slate-command-stone-moss-pages-20260524", base_template)

    def test_collector_overview_links_to_environment_page_without_inline_doctor(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs")

            self.assertEqual(response.status_code, 200)
            self.assertIn('href="/collector/environment"', response.text)
            self.assertIn("环境自检", response.text)
            self.assertNotIn('class="panel environment-panel"', response.text)
            self.assertNotIn('aria-label="Falcon environment doctor"', response.text)

    def test_collector_environment_page_renders_expanded_doctor(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/environment")

            self.assertEqual(response.status_code, 200)
            self.assertIn("环境自检", response.text)
            self.assertIn('class="nav-link active" href="/collector/environment"', response.text)
            self.assertIn('<details class="panel environment-panel environment-page-panel" open>', response.text)
            self.assertIn('aria-label="Falcon environment doctor"', response.text)

    def test_collector_overview_links_to_dedicated_create_and_queue_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            (profile_root / "xiaohongshu" / "default").mkdir(parents=True)
            client = TestClient(create_app(db_path, profile_root=profile_root))

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn("最近任务", response.text)
            self.assertIn('href="/collector/runs"', response.text)
            self.assertIn('href="/collector/create"', response.text)
            self.assertNotIn('id="collector-create-form"', response.text)
            self.assertNotIn('class="queue-wrap"', response.text)

    def test_collector_overview_merges_queue_health_and_collection_rhythm(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            for run_id, status in [
                ("xhs-rhythm-running", "running"),
                ("xhs-rhythm-manual", "manual_action_required"),
                ("xhs-rhythm-failed", "failed"),
                ("xhs-rhythm-queued", "queued"),
            ]:
                repo.create_collection_run(
                    CollectionRun(
                        run_id=run_id,
                        platform="xiaohongshu",
                        keyword=f"keyword-{status}",
                        profile="default",
                        status=status,
                    )
                )
            client = TestClient(create_app(db_path))

            response = client.get("/collector")
            css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
                encoding="utf-8"
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="panel queue-health-panel"', response.text)
            self.assertIn('class="health-metrics"', response.text)
            self.assertIn('class="health-actions"', response.text)
            self.assertNotIn('class="panel rhythm-panel"', response.text)
            self.assertNotIn("采集节奏", response.text)
            self.assertIn("运行中", response.text)
            self.assertIn("待人工", response.text)
            self.assertIn("待启动", response.text)
            self.assertIn('href="/collector/create"', response.text)
            self.assertIn('action="/collector/queue/start"', response.text)
            self.assertIn(".queue-health-panel", css)
            self.assertIn(".health-metrics", css)
            self.assertIn("grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr))", css)
            self.assertIn("grid-template-columns: minmax(170px, 0.75fr) minmax(240px, 1.25fr)", css)
            self.assertIn(".health-actions {\n  display: grid;\n  grid-template-columns: 1fr;", css)
            self.assertNotIn("grid-template-columns: repeat(4, minmax(160px, 1fr));", css)

    def test_collector_create_get_renders_standalone_task_creation_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertIn("任务创建", response.text)
            self.assertIn('id="collector-create-form"', response.text)
            self.assertNotIn('class="panel create-side-panel"', response.text)
            self.assertNotIn('aria-label="入队前摘要"', response.text)
            self.assertIn('id="collector-create-confirm-dialog"', response.text)
            self.assertIn('id="confirm-create-submit"', response.text)
            self.assertIn("返回修改", response.text)
            self.assertIn("确认入队", response.text)

    def test_layout_redesign_adds_standalone_collector_queue_and_create_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            (profile_root / "xiaohongshu" / "default").mkdir(parents=True)
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-layout-queued",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="queued",
                )
            )
            client = TestClient(create_app(db_path, profile_root=profile_root))

            queue = client.get("/collector/runs")
            create = client.get("/collector/create")

            self.assertEqual(queue.status_code, 200)
            self.assertIn("任务队列", queue.text)
            self.assertIn("独立承载筛选器", queue.text)
            self.assertIn("xhs-layout-queued", queue.text)
            self.assertIn('action="/collector/runs/xhs-layout-queued/start"', queue.text)
            self.assertIn('href="/collector/create"', queue.text)
            self.assertEqual(create.status_code, 200)
            self.assertIn("任务创建", create.text)
            self.assertIn('id="collector-create-form"', create.text)
            self.assertIn('action="/collector/create"', create.text)
            self.assertNotIn('class="panel create-side-panel"', create.text)
            self.assertIn('id="collector-create-confirm-dialog"', create.text)

    def test_layout_redesign_adds_analysis_samples_page_and_links_from_analysis_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="AI cover",
                    source_type="post",
                    title="Need better covers",
                    content="How can I improve cover click-through?",
                    url="https://example.test/post/analysis-samples",
                )
            )
            repo.save_analysis(
                raw_id,
                AnalysisResult(
                    scene_tag="xhs_cover",
                    intent_score=91,
                    content_value_score=84,
                    pain_point="cover click-through is low",
                    suggested_topic="Cover upgrade checklist",
                    recommended_action="write_topic",
                    outreach_type="comment_reply",
                    outreach_priority="high",
                    reason="clear pain point",
                ),
            )
            client = TestClient(create_app(db_path))

            home = client.get("/analysis")
            samples_response = client.get("/analysis/samples")

            self.assertEqual(home.status_code, 200)
            self.assertIn('href="/analysis/samples"', home.text)
            self.assertIn("分析样本", home.text)
            self.assertEqual(samples_response.status_code, 200)
            self.assertIn("分析样本", samples_response.text)
            self.assertIn("Need better covers", samples_response.text)
            self.assertIn("Cover upgrade checklist", samples_response.text)

    def test_layout_redesign_navigation_exposes_split_page_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn('href="/collector/runs"', response.text)
            self.assertIn('href="/collector/create"', response.text)
            self.assertIn('href="/analysis/samples"', response.text)
            self.assertIn('href="/tasks"', response.text)

    def test_layout_redesign_applies_workbench_keywords_and_report_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            keyword_path = tmp_path / "keywords.csv"
            keyword_path.write_text(
                "theme,keyword,scene,weight,daily_limit\n"
                "AI头像,头像小程序,avatar,5,20\n",
                encoding="utf-8",
            )
            report_path = tmp_path / "daily-report.md"
            report_path.write_text("# Falcon 日报\n\n今日样本。", encoding="utf-8")
            client = TestClient(create_app(db_path))

            dashboard = client.get("/")
            keywords = client.get("/keywords", params={"path": str(keyword_path)})
            report = client.get("/report", params={"path": str(report_path)})

            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("工作台入口", dashboard.text)
            self.assertIn("今日待办", dashboard.text)
            self.assertIn("链路入口", dashboard.text)
            self.assertIn('href="/collector/create"', dashboard.text)
            self.assertIn('href="/analysis/samples"', dashboard.text)
            self.assertIn('href="/tasks"', dashboard.text)
            self.assertEqual(keywords.status_code, 200)
            self.assertIn("关键词配置", keywords.text)
            self.assertIn("关键词表", keywords.text)
            self.assertIn('class="keyword-layout"', keywords.text)
            self.assertIn("头像小程序", keywords.text)
            self.assertEqual(report.status_code, 200)
            self.assertIn('class="report-reader"', report.text)
            self.assertIn("阅读宽度", report.text)
            self.assertIn("Falcon 日报", report.text)

    def test_layout_redesign_applies_review_execution_and_tasks_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="AI cover",
                    source_type="post",
                    title="Review and execute candidate",
                    content="Need a reply",
                    url="https://example.test/post/review-execution",
                )
            )
            analysis = AnalysisResult(
                scene_tag="xhs_cover",
                intent_score=91,
                content_value_score=86,
                pain_point="cover click-through is low",
                suggested_topic="Cover upgrade checklist",
                recommended_action="comment_reply",
                outreach_type="comment_reply",
                outreach_priority="high",
                reason="clear request",
            )
            analysis_id = repo.save_analysis(raw_id, analysis)
            repo.create_outreach_task(
                raw_id,
                analysis_id,
                analysis,
                [Draft(kind="comment_reply", text="Try stronger contrast and fewer words.")],
                risk_note="human confirmation required",
            )
            client = TestClient(create_app(db_path))

            review = client.get("/review")
            execution = client.get("/execution")
            tasks = client.get("/tasks")

            self.assertEqual(review.status_code, 200)
            self.assertIn("复核工作台", review.text)
            self.assertIn('class="review-workbench"', review.text)
            self.assertIn('class="review-action-panel"', review.text)
            self.assertIn("Review and execute candidate", review.text)
            self.assertNotIn('class="row-form"', review.text)
            self.assertEqual(execution.status_code, 200)
            self.assertIn("执行首页", execution.text)
            self.assertIn("待确认草稿队列", execution.text)
            self.assertIn("优先级概览", execution.text)
            self.assertIn('href="/tasks"', execution.text)
            self.assertIn("Try stronger contrast", execution.text)
            self.assertEqual(tasks.status_code, 200)
            self.assertIn("触达任务状态管理", tasks.text)
            self.assertIn('class="task-table-wrap"', tasks.text)
            self.assertIn('action="/tasks/', tasks.text)
            self.assertIn("human confirmation required", tasks.text)

    def test_collector_overview_exposes_inline_archive_button_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-inline-archive",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-inline-archived",
                    platform="xiaohongshu",
                    keyword="AI archived",
                    profile="default",
                    status="cancelled",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs")

            self.assertEqual(response.status_code, 200)
            self.assertIn('data-run-id="xhs-inline-archive"', response.text)
            self.assertIn('data-queue-archive-form', response.text)
            self.assertIn('action="/collector/runs/xhs-inline-archive/archive"', response.text)
            self.assertIn('class="button small archive"', response.text)
            self.assertIn('class="button small archived"', response.text)
            self.assertNotIn('class="queue-action-more"', response.text)
            self.assertIn("fetch(form.action", response.text)
            self.assertIn("/static/app.css?v=", response.text)
            css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
                encoding="utf-8"
            )
            self.assertIn("flex-wrap: nowrap", css)
            self.assertIn(".queue-action-primary .inline-form:not(.queue-archive-form)", css)
            self.assertIn("flex: 0 0 auto", css)
            self.assertIn("flex: 0 0 104px", css)
            self.assertIn("flex: 0 0 62px", css)
            self.assertIn(".button.archived", css)
            self.assertIn(".queue-action-primary .button.archived", css)

    def test_collector_archive_supports_inline_json_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-inline-json",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.post(
                "/collector/runs/xhs-inline-json/archive",
                headers={"Accept": "application/json", "X-Requested-With": "fetch"},
                follow_redirects=False,
            )

            repo = FalconRepository(db_path)
            repo.init_schema()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["run_id"], "xhs-inline-json")
            self.assertEqual(response.json()["status"], "cancelled")
            self.assertEqual(response.json()["status_label"], "已归档")
            self.assertEqual(repo.get_collection_run("xhs-inline-json").status, "cancelled")

    def test_collector_archive_releases_profile_and_dispatches_next_queued_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual-release",
                    platform="xiaohongshu",
                    keyword="blocked",
                    profile="default",
                    status="manual_action_required",
                    created_at="2026-05-23T00:00:00+00:00",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-next-after-release",
                    platform="xiaohongshu",
                    keyword="next",
                    profile="default",
                    status="queued",
                    created_at="2026-05-23T00:01:00+00:00",
                )
            )
            launches = []
            client = TestClient(create_app(db_path, collector_run_launcher=lambda run_id: launches.append(run_id)))

            response = client.post("/collector/runs/xhs-manual-release/archive", follow_redirects=False)

            repo = FalconRepository(db_path)
            repo.init_schema()
            released = repo.get_collection_run("xhs-manual-release")
            next_run = repo.get_collection_run("xhs-next-after-release")
            next_events = {event.event for event in repo.list_collection_events("xhs-next-after-release")}
            self.assertEqual(response.status_code, 303)
            self.assertEqual(released.status, "cancelled")
            self.assertEqual(next_run.status, "running")
            self.assertEqual(launches, ["xhs-next-after-release"])
            self.assertIn("queue_worker_dispatched", next_events)

    def test_collector_overview_shows_actionable_focus_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            for run_id, status in [
                ("xhs-focus-manual", "manual_action_required"),
                ("xhs-focus-failed", "failed"),
                ("xhs-focus-queued", "queued"),
            ]:
                repo.create_collection_run(
                    CollectionRun(
                        run_id=run_id,
                        platform="xiaohongshu",
                        keyword=f"keyword-{status}",
                        profile="default",
                        status=status,
                    )
                )
            client = TestClient(create_app(db_path))

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="panel focus-panel"', response.text)
            self.assertIn("待处理焦点", response.text)
            self.assertIn("xhs-focus-manual", response.text)
            self.assertIn("xhs-focus-failed", response.text)
            self.assertIn("xhs-focus-queued", response.text)
            self.assertIn('action="/collector/runs/xhs-focus-manual/open-manual-action"', response.text)
            self.assertIn('action="/collector/runs/xhs-focus-failed/rerun"', response.text)
            self.assertIn('action="/collector/runs/xhs-focus-queued/start"', response.text)

    def test_collector_environment_page_shows_blocked_doctor_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            report = DoctorReport(
                [
                    DoctorCheck("python", "Python", "ok", "3.11", True),
                    DoctorCheck("node", "Node.js", "missing", "not found", True, "node --version"),
                    DoctorCheck("sidecar_package", "Collector sidecar package", "ok", "package.json", True),
                    DoctorCheck(
                        "playwright_chromium",
                        "Playwright Chromium",
                        "warning",
                        "install needed",
                        True,
                        "npx playwright install chromium",
                    ),
                ]
            )
            client = TestClient(create_app(db_path, doctor_report_builder=lambda _root: report))

            response = client.get("/collector/environment")

            self.assertEqual(response.status_code, 200)
            self.assertIn('<details class="panel environment-panel environment-page-panel" open>', response.text)
            self.assertIn("<summary", response.text)
            self.assertIn("展开明细", response.text)
            self.assertIn("收起明细", response.text)
            self.assertIn("环境自检", response.text)
            self.assertIn("ACTION", response.text)
            self.assertIn("状态", response.text)
            self.assertIn("作用", response.text)
            self.assertIn("路径 / 版本", response.text)
            self.assertIn("处理命令", response.text)
            self.assertIn("Node.js", response.text)
            self.assertIn("Playwright Chromium", response.text)
            self.assertIn("运行 Node Playwright sidecar", response.text)
            self.assertIn("采集合同", response.text)
            self.assertNotIn("dry-run", response.text)
            self.assertIn("node --version", response.text)

    def test_collector_environment_page_keeps_doctor_expanded_when_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            report = DoctorReport(
                [
                    DoctorCheck("python", "Python", "ok", "3.11", True),
                    DoctorCheck("node", "Node.js", "ok", "v24.14.0", True, "node --version"),
                ]
            )
            client = TestClient(create_app(db_path, doctor_report_builder=lambda _root: report))

            response = client.get("/collector/environment")

            self.assertEqual(response.status_code, 200)
            self.assertIn('<details class="panel environment-panel environment-page-panel" open>', response.text)
            self.assertIn("READY", response.text)
            self.assertIn("2/2 项就绪", response.text)

    def test_collector_account_management_is_separate_from_overview(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            (profile_root / "xiaohongshu" / "backup").mkdir(parents=True)
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-running",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="running",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="dy-queued",
                    platform="douyin",
                    keyword="AI cover",
                    profile="creator",
                    status="queued",
                )
            )
            client = TestClient(create_app(db_path, profile_root=profile_root))

            overview = client.get("/collector/runs")
            accounts = client.get("/collector/accounts")

            self.assertEqual(overview.status_code, 200)
            self.assertEqual(accounts.status_code, 200)
            self.assertIn('href="/collector/accounts"', overview.text)
            self.assertNotIn('action="/collector/profiles/open-login"', overview.text)
            self.assertNotIn("平台账号 / Profile", overview.text)
            self.assertIn("账号管理", accounts.text)
            self.assertIn('action="/collector/profiles/open-login"', accounts.text)
            self.assertIn("platform/profile", accounts.text)
            self.assertIn("xiaohongshu/default", accounts.text)
            self.assertIn("xiaohongshu/backup", accounts.text)
            self.assertIn("douyin/creator", accounts.text)
            self.assertIn("browser-profiles", accounts.text)

    def test_collector_accounts_render_platform_user_matrix_actions_without_select_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            (profile_root / "xiaohongshu" / "backup").mkdir(parents=True)
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual-account",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="creator",
                    status="manual_action_required",
                )
            )
            client = TestClient(create_app(db_path, profile_root=profile_root))

            response = client.get("/collector/accounts")

            self.assertEqual(response.status_code, 200)
            self.assertIn("account-workbench", response.text)
            self.assertIn('class="account-platform-section"', response.text)
            self.assertIn("account-platform-identity", response.text)
            self.assertIn("account-platform-meta", response.text)
            self.assertIn("account-create-toolbar", response.text)
            self.assertIn("account-action-bar", response.text)
            self.assertIn("平台用户矩阵", response.text)
            self.assertIn("xiaohongshu/default", response.text)
            self.assertIn("xiaohongshu/backup", response.text)
            self.assertIn("xiaohongshu/creator", response.text)
            self.assertIn("等待人工", response.text)
            self.assertIn("登录", response.text)
            self.assertIn("检查", response.text)
            self.assertIn("退出", response.text)
            self.assertIn("新建 Profile", response.text)
            self.assertIn("输入名称后打开登录窗口", response.text)
            self.assertIn('action="/collector/profiles/logout"', response.text)
            self.assertNotIn("<select", response.text)
            css_path = Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css"
            css_text = css_path.read_text(encoding="utf-8")
            self.assertIn(".account-action-bar", css_text)
            self.assertIn(".account-create-toolbar", css_text)
            self.assertIn("max-width: 260px", css_text)
            self.assertIn("width: auto", css_text)
            self.assertNotIn(".account-actions", css_text)

    def test_collector_profile_logout_clears_idle_local_profile_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            profile_dir = profile_root / "xiaohongshu" / "backup"
            profile_dir.mkdir(parents=True)
            (profile_dir / "cookies.sqlite").write_text("local profile state", encoding="utf-8")
            client = TestClient(create_app(db_path, profile_root=profile_root))

            response = client.post(
                "/collector/profiles/logout",
                data={"platform": "xiaohongshu", "profile": "backup"},
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertIn("profile_action=logged_out", response.headers["location"])
            self.assertFalse(profile_dir.exists())

    def test_collector_profile_logout_rejects_busy_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            profile_dir = profile_root / "xiaohongshu" / "default"
            profile_dir.mkdir(parents=True)
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-busy-logout",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="running",
                )
            )
            client = TestClient(create_app(db_path, profile_root=profile_root))

            response = client.post(
                "/collector/profiles/logout",
                data={"platform": "xiaohongshu", "profile": "default"},
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 400)
            self.assertTrue(profile_dir.exists())

    def test_desktop_sidebar_is_fixed_while_content_scrolls(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        sidebar_rule = css[css.index(".sidebar {") : css.index(".brand {")]
        main_rule = css[css.index(".main {") : css.index(".page-header {")]
        nav_rule = css[css.index(".nav-groups {") : css.index(".nav-group {")]

        self.assertIn("position: fixed", sidebar_rule)
        self.assertIn("height: 100vh", sidebar_rule)
        self.assertIn("overflow: hidden", sidebar_rule)
        self.assertIn("flex: 1 1 auto", nav_rule)
        self.assertIn("overflow-y: auto", nav_rule)
        self.assertIn("overscroll-behavior: contain", nav_rule)
        self.assertIn("scrollbar-gutter: stable", nav_rule)
        self.assertIn("scrollbar-color: transparent transparent", nav_rule)
        self.assertIn(".nav-groups:hover", css)
        self.assertIn(".nav-groups::-webkit-scrollbar", css)
        self.assertIn(".nav-groups::-webkit-scrollbar-thumb:hover", css)
        self.assertIn("margin-left: 232px", main_rule)

    def test_layout_redesign_shared_css_supports_base_page_splits(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        for selector in [
            ".workbench-grid",
            ".keyword-layout",
            ".report-reader",
            ".review-workbench",
            ".execution-grid",
            ".task-table-wrap",
        ]:
            self.assertIn(selector, css)
        self.assertIn("max-width: 860px", css)
        self.assertIn(".review-workbench,\n  .execution-grid,\n  .keyword-layout", css)

    def test_collector_profile_login_launches_supported_platform_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            launches = []

            def fake_launcher(**kwargs):
                launches.append(kwargs)
                return {"pid": 4321}

            client = TestClient(
                create_app(db_path, profile_root=profile_root, profile_login_launcher=fake_launcher)
            )

            response = client.post(
                "/collector/profiles/open-login",
                data={"platform": "xiaohongshu", "profile": "creator"},
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertTrue(response.headers["location"].startswith("/collector/accounts?profile_action=opened"))
            self.assertEqual(len(launches), 1)
            self.assertEqual(launches[0]["platform"], "xiaohongshu")
            self.assertEqual(launches[0]["profile"], "creator")
            self.assertEqual(launches[0]["profile_path"], profile_root / "xiaohongshu" / "creator")
            self.assertEqual(launches[0]["url"], "https://www.xiaohongshu.com/")

    def test_collector_profile_login_rejects_unsupported_or_unsafe_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            launches = []

            def fake_launcher(**kwargs):
                launches.append(kwargs)
                return {"pid": 4321}

            client = TestClient(
                create_app(db_path, profile_root=profile_root, profile_login_launcher=fake_launcher)
            )

            unsupported = client.post(
                "/collector/profiles/open-login",
                data={"platform": "douyin", "profile": "default"},
                follow_redirects=False,
            )
            unsafe = client.post(
                "/collector/profiles/open-login",
                data={"platform": "xiaohongshu", "profile": "..\\outside"},
                follow_redirects=False,
            )

            self.assertEqual(unsupported.status_code, 400)
            self.assertEqual(unsafe.status_code, 400)
            self.assertEqual(launches, [])
            self.assertFalse((tmp_path / "outside").exists())

    def test_collector_create_get_renders_task_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertIn("任务配置", response.text)
            self.assertIn('name="keyword"', response.text)
            self.assertIn('name="max_posts"', response.text)
            assert_no_legacy_collection_markers(self, response.text)

    def test_collector_create_get_renders_huashu_keyword_group_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertIn("任务配置", response.text)
            self.assertIn("关键词组", response.text)
            self.assertIn('name="keywords"', response.text)
            self.assertIn('class="help-dot"', response.text)
            self.assertIn('id="confirm-run-count"', response.text)

    def test_collector_create_get_starts_with_blank_keyword_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertIn('id="keywords-hidden"', response.text)
            self.assertIn('name="keywords"', response.text)
            self.assertIn('value=""', response.text)
            self.assertIn('id="confirm-keywords"', response.text)
            self.assertIn('id="confirm-run-count"', response.text)
            self.assertNotIn('data-keyword="小红书封面"', response.text)
            self.assertNotIn('data-keyword="AI 封面"', response.text)
            self.assertNotIn('data-keyword="副业"', response.text)

    def test_collector_create_get_uses_existing_profile_select(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            (profile_root / "xiaohongshu" / "default").mkdir(parents=True)
            (profile_root / "xiaohongshu" / "creator").mkdir(parents=True)
            client = TestClient(create_app(db_path, profile_root=profile_root))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertIn('<select id="profile-select" name="profile" required>', response.text)
            self.assertIn('<option value="default" selected>', response.text)
            self.assertIn('<option value="creator" >', response.text)
            self.assertIn("只能选择账号管理里已有的 Profile", response.text)
            self.assertNotIn('<input name="profile"', response.text)

    def test_collector_create_get_hides_profiles_without_local_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-old-profile",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="legacy",
                    status="completed",
                )
            )
            client = TestClient(create_app(db_path, profile_root=profile_root))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertNotIn('<option value="default"', response.text)
            self.assertNotIn('<option value="legacy"', response.text)
            self.assertIn("请先在账号管理创建 Profile", response.text)
            self.assertIn('href="/collector/accounts"', response.text)

    def test_collector_create_get_uses_compact_task_parameter_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="field profile-field"', response.text)
            self.assertIn('class="field keyword-field"', response.text)
            self.assertIn('class="field compact-field"', response.text)
            self.assertIn('class="field-grid task-config-grid"', response.text)

    def test_collector_create_post_queues_run_and_redirects_to_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.post(
                "/collector/create",
                data={
                    "platform": "xiaohongshu",
                    "profile": "creator",
                    "keyword": "AI cover",
                    "max_posts": "7",
                    "max_comments_per_post": "3",
                },
                follow_redirects=False,
            )

            repo = FalconRepository(db_path)
            repo.init_schema()
            runs = repo.list_collection_runs()
            self.assertEqual(response.status_code, 303)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "queued")
            self.assertEqual(runs[0].platform, "xiaohongshu")
            self.assertEqual(runs[0].keyword, "AI cover")
            self.assertEqual(runs[0].profile, "creator")
            self.assertEqual(runs[0].max_posts, 7)
            self.assertEqual(response.headers["location"], "/collector/runs?status=queued&created=1")
            request_path = tmp_path / "runtime" / "collector" / runs[0].run_id / "request.json"
            self.assertTrue(request_path.exists())
            self.assertIn('"platform": "xiaohongshu"', request_path.read_text(encoding="utf-8"))

    def test_collector_create_post_splits_multiple_keywords_into_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.post(
                "/collector/create",
                data={
                    "platform": "xiaohongshu",
                    "profile": "creator",
                    "keywords": "小红书封面\nAI 封面，副业",
                    "max_posts": "7",
                    "max_comments_per_post": "3",
                },
                follow_redirects=False,
            )

            repo = FalconRepository(db_path)
            repo.init_schema()
            runs = sorted(repo.list_collection_runs(), key=lambda run: run.keyword)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/collector/runs?status=queued&created=3")
            self.assertEqual([run.keyword for run in runs], ["AI 封面", "副业", "小红书封面"])
            for run in runs:
                self.assertEqual(run.status, "queued")
                self.assertEqual(run.platform, "xiaohongshu")
                self.assertEqual(run.profile, "creator")
                self.assertEqual(run.max_posts, 7)
                request_path = tmp_path / "runtime" / "collector" / run.run_id / "request.json"
                self.assertTrue(request_path.exists())
                self.assertIn(f'"keyword": "{run.keyword}"', request_path.read_text(encoding="utf-8"))

    def test_collector_create_rejects_unknown_platform_and_path_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            bad_platform = client.post(
                "/collector/create",
                data={
                    "platform": "../outside",
                    "profile": "default",
                    "keyword": "AI cover",
                    "max_posts": "5",
                    "max_comments_per_post": "1",
                },
                follow_redirects=False,
            )
            bad_profile = client.post(
                "/collector/create",
                data={
                    "platform": "xiaohongshu",
                    "profile": "..\\outside",
                    "keyword": "AI cover",
                    "max_posts": "5",
                    "max_comments_per_post": "1",
                },
                follow_redirects=False,
            )

            repo = FalconRepository(db_path)
            repo.init_schema()
            self.assertEqual(bad_platform.status_code, 400)
            self.assertEqual(bad_profile.status_code, 400)
            self.assertEqual(repo.list_collection_runs(), [])
            self.assertFalse((tmp_path / "outside").exists())

    def test_collector_run_detail_shows_event_chain_outputs_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-detail",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="running",
                    progress=35,
                    current_step="reading detail cards",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-detail",
                    sequence=1,
                    scope="search",
                    event="open_search",
                    message="Opened keyword search",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-detail",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Cover prompt ideas",
                    content="Useful notes",
                    url="https://example.test/post/1",
                    author="creator",
                    detail_fingerprint="fp-detail",
                )
            )
            repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-detail",
                    post_id=post_id,
                    path="runtime/collector/xhs-detail/assets/cover.jpg",
                    asset_type="image",
                    sha256="abc123",
                )
            )
            repo.save_evidence(
                Evidence(
                    run_id="xhs-detail",
                    evidence_type="screenshot",
                    path="runtime/collector/xhs-detail/evidence/search.png",
                    scope="search",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs/xhs-detail")

            self.assertEqual(response.status_code, 200)
            self.assertIn("任务详情", response.text)
            self.assertIn("reading detail cards", response.text)
            self.assertIn("Opened keyword search", response.text)
            self.assertIn("Cover prompt ideas", response.text)
            self.assertIn("cover.jpg", response.text)
            self.assertIn("search.png", response.text)
            self.assertIn('class="table-wrap sample-table-wrap"', response.text)
            self.assertIn('class="run-ledger timeline-ledger"', response.text)
            self.assertIn('class="run-ledger asset-evidence-ledger"', response.text)
            self.assertIn('data-visible-rows="7"', response.text)
            self.assertIn("显示 7 条", response.text)
            self.assertLess(response.text.index("采集样本"), response.text.index("事件链"))
            assert_no_legacy_collection_markers(self, response.text)

    def test_collector_run_detail_ledger_css_limits_panels_to_seven_scrollable_rows(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        ledger_body_rule = css[css.index(".run-ledger-body {") : css.index(".run-ledger-body::-webkit-scrollbar {")]

        self.assertIn("max-height: calc(7 * 64px)", ledger_body_rule)
        self.assertIn("overflow-y: auto", ledger_body_rule)

    def test_collector_run_detail_sample_table_limits_to_seven_scrollable_rows(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        sample_table_rule = css[css.index(".sample-table-wrap {") : css.index(".sample-table-wrap thead th {")]

        self.assertIn("max-height: calc(43px + (7 * 56px))", sample_table_rule)
        self.assertIn("overflow-y: auto", sample_table_rule)
        self.assertIn("scrollbar-width: thin", sample_table_rule)

    def test_collector_run_detail_wraps_long_failed_reason(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        failed_reason_rule = css[css.index(".run-state-main .alert {") : css.index(".run-hero-meta {")]

        self.assertIn("overflow-wrap: anywhere", failed_reason_rule)
        self.assertIn("white-space: pre-wrap", failed_reason_rule)
        self.assertIn("max-height: 220px", failed_reason_rule)

    def test_collector_run_detail_uses_overview_breadcrumb_without_sidebar_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-breadcrumb",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="manual_action_required",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs/xhs-breadcrumb")

            self.assertEqual(response.status_code, 200)
            self.assertIn("采集总览 -&gt; 任务详情(xhs-breadcrumb)", response.text)
            self.assertNotIn('href="/collector/runs/xhs-breadcrumb">任务详情</a>', response.text)

    def test_collector_overview_shows_lifecycle_columns_operations_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="manual_action_required",
                    progress=50,
                    current_step="检测到 手机扫码查看，需要人工处理后再继续。",
                    created_at="2026-05-23T08:14:07+00:00",
                    updated_at="2026-05-23T08:14:27+00:00",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs")

            self.assertEqual(response.status_code, 200)
            self.assertIn("开启时间", response.text)
            self.assertIn("运行时长", response.text)
            self.assertIn("资源占用", response.text)
            self.assertIn("操作", response.text)
            self.assertIn("需人工处理", response.text)
            self.assertIn("已暂停", response.text)
            self.assertIn("不占用采集器", response.text)
            self.assertIn("2026-05-23 16:14:07", response.text)
            self.assertIn("20 秒", response.text)
            self.assertIn('action="/collector/runs/xhs-manual/open-manual-action"', response.text)
            self.assertIn('action="/collector/runs/xhs-manual/rerun"', response.text)
            self.assertIn('action="/collector/runs/xhs-manual/mark-failed"', response.text)
            self.assertIn('action="/collector/runs/xhs-manual/archive"', response.text)

    def test_collector_queued_run_has_obvious_waiting_state_and_start_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-queued",
                    platform="xiaohongshu",
                    keyword="side hustle",
                    profile="default",
                    status="queued",
                    progress=0,
                    current_step="等待浏览器采集调度",
                )
            )
            client = TestClient(create_app(db_path))
            css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
                encoding="utf-8"
            )

            overview = client.get("/collector/runs")
            filtered = client.get("/collector/runs?status=queued&created=1")
            detail = client.get("/collector/runs/xhs-queued")

            self.assertEqual(overview.status_code, 200)
            self.assertIn(".queue-attention-banner", css)
            self.assertIn(".run-row.status-queued.is-attention", css)
            self.assertIn('class="queue-attention-banner"', overview.text)
            self.assertIn("待启动任务", overview.text)
            self.assertIn("不占用资源", overview.text)
            self.assertIn('action="/collector/queue/start"', overview.text)
            self.assertIn('href="/collector/runs?status=queued"', overview.text)
            self.assertIn('class="run-row status-queued is-attention"', overview.text)
            self.assertIn('class="status-badge status-queued"', overview.text)
            self.assertIn('action="/collector/runs/xhs-queued/start"', overview.text)
            self.assertIn("未启动，不占用资源", overview.text)
            self.assertEqual(filtered.status_code, 200)
            self.assertIn('data-status-filter="all" aria-pressed="false"', filtered.text)
            self.assertIn('data-status-filter="queued" aria-pressed="true"', filtered.text)
            self.assertIn("刚加入 1 个任务", filtered.text)
            self.assertEqual(detail.status_code, 200)
            self.assertIn('class="run-state-banner status-queued"', detail.text)
            self.assertIn('action="/collector/runs/xhs-queued/start"', detail.text)

    def test_collector_queue_running_and_failed_status_badges_are_prominent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            for run_id, status in [("xhs-running-badge", "running"), ("xhs-failed-badge", "failed")]:
                repo.create_collection_run(
                    CollectionRun(
                        run_id=run_id,
                        platform="xiaohongshu",
                        keyword="AI cover",
                        profile="default",
                        status=status,
                    )
                )
            client = TestClient(create_app(db_path))
            css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
                encoding="utf-8"
            )

            response = client.get("/collector/runs")

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="status-badge status-running"', response.text)
            self.assertIn('class="status-badge status-failed"', response.text)
            self.assertIn(".status-badge.status-running {\n  min-width: 98px;", css)
            self.assertIn(".status-badge.status-failed {\n  min-width: 98px;", css)
            self.assertIn(".status-badge.status-running i,\n.status-badge.status-failed i {\n  width: 12px;", css)
            self.assertIn("box-shadow: 0 0 0 2px rgba(209, 162, 77, 0.12)", css)
            self.assertIn("box-shadow: 0 0 0 2px rgba(223, 103, 103, 0.1)", css)

    def test_collector_start_marks_run_running_and_dispatches_background_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-start",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="queued",
                    progress=0,
                    current_step="等待浏览器采集调度",
                )
            )
            launches = []

            def fake_launcher(run_id):
                launches.append(run_id)

            client = TestClient(create_app(db_path, collector_run_launcher=fake_launcher))

            response = client.post("/collector/runs/xhs-start/start", follow_redirects=False)

            repo = FalconRepository(db_path)
            repo.init_schema()
            run = repo.get_collection_run("xhs-start")
            events = repo.list_collection_events("xhs-start")
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/collector/runs/xhs-start")
            self.assertEqual(run.status, "running")
            self.assertGreaterEqual(run.progress, 5)
            self.assertIn("启动", run.current_step)
            self.assertEqual(launches, ["xhs-start"])
            self.assertIn("run_start_requested", {event.event for event in events})

    def test_collector_start_rejects_run_when_profile_is_already_busy(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-running-profile",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="running",
                    progress=40,
                    current_step="采集器运行中",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-waiting-same-profile",
                    platform="xiaohongshu",
                    keyword="AI title",
                    profile="default",
                    status="queued",
                    progress=0,
                    current_step="等待浏览器采集调度",
                )
            )
            launches = []
            client = TestClient(create_app(db_path, collector_run_launcher=lambda run_id: launches.append(run_id)))

            response = client.post("/collector/runs/xhs-waiting-same-profile/start", follow_redirects=False)

            repo = FalconRepository(db_path)
            repo.init_schema()
            run = repo.get_collection_run("xhs-waiting-same-profile")
            self.assertEqual(response.status_code, 400)
            self.assertIn("profile is already busy", response.text)
            self.assertEqual(run.status, "queued")
            self.assertEqual(launches, [])

    def test_collector_queue_start_dispatches_one_run_per_available_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-default-old",
                    platform="xiaohongshu",
                    keyword="小红书封面",
                    profile="default",
                    status="queued",
                    current_step="等待浏览器采集调度",
                    created_at="2026-05-23T00:00:00+00:00",
                    updated_at="2026-05-23T00:00:00+00:00",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-default-new",
                    platform="xiaohongshu",
                    keyword="AI 封面",
                    profile="default",
                    status="queued",
                    current_step="等待浏览器采集调度",
                    created_at="2026-05-23T00:01:00+00:00",
                    updated_at="2026-05-23T00:01:00+00:00",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-creator-old",
                    platform="xiaohongshu",
                    keyword="副业",
                    profile="creator",
                    status="queued",
                    current_step="等待浏览器采集调度",
                    created_at="2026-05-23T00:02:00+00:00",
                    updated_at="2026-05-23T00:02:00+00:00",
                )
            )
            launches = []
            client = TestClient(create_app(db_path, collector_run_launcher=lambda run_id: launches.append(run_id)))

            response = client.post("/collector/queue/start", follow_redirects=False)

            repo = FalconRepository(db_path)
            repo.init_schema()
            default_old = repo.get_collection_run("xhs-default-old")
            default_new = repo.get_collection_run("xhs-default-new")
            creator_old = repo.get_collection_run("xhs-creator-old")
            default_events = {event.event for event in repo.list_collection_events("xhs-default-old")}
            creator_events = {event.event for event in repo.list_collection_events("xhs-creator-old")}
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/collector/runs")
            self.assertEqual(default_old.status, "running")
            self.assertEqual(default_new.status, "queued")
            self.assertEqual(creator_old.status, "running")
            self.assertEqual(launches, ["xhs-default-old", "xhs-creator-old"])
            self.assertIn("queue_worker_dispatched", default_events)
            self.assertIn("queue_worker_dispatched", creator_events)

    def test_collector_manual_action_opens_matching_profile_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            profile_root = Path(tmp) / "browser-profiles"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual-open",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="creator",
                    status="manual_action_required",
                    progress=50,
                    current_step="检测到 手机扫码查看，需要人工处理后再继续。",
                )
            )
            launches = []

            def fake_launcher(**kwargs):
                launches.append(kwargs)

            client = TestClient(create_app(db_path, profile_root=profile_root, profile_login_launcher=fake_launcher))

            detail = client.get("/collector/runs/xhs-manual-open")
            response = client.post("/collector/runs/xhs-manual-open/open-manual-action", follow_redirects=False)

            repo = FalconRepository(db_path)
            repo.init_schema()
            events = repo.list_collection_events("xhs-manual-open")
            self.assertEqual(detail.status_code, 200)
            self.assertIn('action="/collector/runs/xhs-manual-open/open-manual-action"', detail.text)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/collector/runs/xhs-manual-open?manual_action=opened")
            self.assertEqual(len(launches), 1)
            self.assertEqual(launches[0]["platform"], "xiaohongshu")
            self.assertEqual(launches[0]["profile"], "creator")
            self.assertEqual(launches[0]["profile_path"], profile_root / "xiaohongshu" / "creator")
            self.assertEqual(launches[0]["url"], "https://www.xiaohongshu.com/")
            self.assertIn("manual_action_window_opened", {event.event for event in events})

    def test_collector_manual_action_window_does_not_reopen_blocked_post_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            profile_root = Path(tmp) / "browser-profiles"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual-post-url",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="manual_action_required",
                    progress=50,
                    current_step="检测到 手机扫码查看，需要人工处理后再继续。",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-manual-post-url",
                    sequence=1,
                    scope="xiaohongshu",
                    event="manual_action_required",
                    message="blocked",
                    payload_json='{"url": "https://www.xiaohongshu.com/explore/65abc123"}',
                )
            )
            launches = []

            def fake_launcher(**kwargs):
                launches.append(kwargs)

            client = TestClient(create_app(db_path, profile_root=profile_root, profile_login_launcher=fake_launcher))

            response = client.post("/collector/runs/xhs-manual-post-url/open-manual-action", follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertEqual(len(launches), 1)
            self.assertEqual(launches[0]["url"], "https://www.xiaohongshu.com/")

    def test_collector_manual_action_can_resume_same_run_after_user_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual-resume",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="manual_action_required",
                    progress=50,
                    current_step="检测到 手机扫码查看，需要人工处理后再继续。",
                )
            )
            launches = []
            client = TestClient(create_app(db_path, collector_run_launcher=lambda run_id: launches.append(run_id)))

            detail = client.get("/collector/runs/xhs-manual-resume")
            response = client.post("/collector/runs/xhs-manual-resume/resume", follow_redirects=False)

            repo = FalconRepository(db_path)
            repo.init_schema()
            run = repo.get_collection_run("xhs-manual-resume")
            events = {event.event for event in repo.list_collection_events("xhs-manual-resume")}
            self.assertEqual(detail.status_code, 200)
            self.assertIn('action="/collector/runs/xhs-manual-resume/resume"', detail.text)
            self.assertIn("继续采集", detail.text)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/collector/runs/xhs-manual-resume")
            self.assertEqual(run.status, "running")
            self.assertEqual(run.current_step, "人工处理已完成，继续采集器")
            self.assertEqual(launches, ["xhs-manual-resume"])
            self.assertIn("manual_action_resumed", events)
            self.assertEqual(len(repo.list_collection_runs(limit=100)), 1)

    def test_collector_running_detail_auto_refreshes_and_ingests_streaming_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-streaming",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="running",
                    progress=5,
                    current_step="采集器启动中",
                )
            )
            run_dir = tmp_path / "runtime" / "collector" / "xhs-streaming"
            run_dir.mkdir(parents=True)
            (run_dir / "events.jsonl").write_text(
                "\n".join(
                    json.dumps(event, ensure_ascii=False)
                    for event in [
                        {
                            "sequence": 1,
                            "time": "2026-05-23T10:00:00+00:00",
                            "level": "info",
                            "scope": "collector",
                            "event": "run_started",
                            "message": "采集任务已启动",
                            "payload": {},
                        },
                        {
                            "sequence": 2,
                            "time": "2026-05-23T10:00:03+00:00",
                            "level": "info",
                            "scope": "xiaohongshu",
                            "event": "browser_launching",
                            "message": "小红书浏览器采集已启动",
                            "payload": {},
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs/xhs-streaming")

            repo = FalconRepository(db_path)
            repo.init_schema()
            run = repo.get_collection_run("xhs-streaming")
            events = repo.list_collection_events("xhs-streaming")
            self.assertEqual(response.status_code, 200)
            self.assertIn('data-auto-refresh="3000"', response.text)
            self.assertIn("自动刷新", response.text)
            self.assertEqual(len(events), 2)
            self.assertEqual(run.status, "running")
            self.assertGreaterEqual(run.progress, 15)
            self.assertEqual(run.current_step, "小红书浏览器采集已启动")

    def test_collector_run_actions_mark_failed_archive_and_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            for run_id in ["xhs-fail", "xhs-archive", "xhs-rerun"]:
                repo.create_collection_run(
                    CollectionRun(
                        run_id=run_id,
                        platform="xiaohongshu",
                        keyword="AI cover",
                        profile="default",
                        status="manual_action_required",
                        progress=50,
                        current_step="检测到 手机扫码查看，需要人工处理后再继续。",
                    )
                )
            client = TestClient(create_app(db_path))

            failed = client.post("/collector/runs/xhs-fail/mark-failed", follow_redirects=False)
            archived = client.post("/collector/runs/xhs-archive/archive", follow_redirects=False)
            rerun = client.post("/collector/runs/xhs-rerun/rerun", follow_redirects=False)

            repo = FalconRepository(db_path)
            repo.init_schema()
            runs = repo.list_collection_runs()
            new_run = next(run for run in runs if run.run_id not in {"xhs-fail", "xhs-archive", "xhs-rerun"})
            self.assertEqual(failed.status_code, 303)
            self.assertEqual(archived.status_code, 303)
            self.assertEqual(rerun.status_code, 303)
            self.assertEqual(repo.get_collection_run("xhs-fail").status, "failed")
            self.assertEqual(repo.get_collection_run("xhs-archive").status, "cancelled")
            self.assertEqual(new_run.status, "queued")
            self.assertEqual(new_run.platform, "xiaohongshu")
            self.assertEqual(new_run.keyword, "AI cover")
            self.assertTrue((tmp_path / "runtime" / "collector" / new_run.run_id / "request.json").exists())

    def test_collector_run_detail_formats_event_times_as_shanghai_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-time",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="manual_action_required",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-time",
                    sequence=1,
                    scope="collector",
                    event="run_started",
                    message="采集任务已启动",
                    created_at="2026-05-23T08:14:07.274Z",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs/xhs-time")

            self.assertEqual(response.status_code, 200)
            self.assertIn("2026-05-23 16:14:07", response.text)
            self.assertNotIn("2026-05-23T08:14:07.274Z", response.text)

    def test_collected_post_title_links_to_local_preview_not_platform_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-preview",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-preview",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Local preview post",
                    content="Preview this inside Falcon.",
                    url="https://www.xiaohongshu.com/explore/abc123",
                    author="creator",
                    like_count="12",
                    comment_count="3",
                    detail_fingerprint="abc123",
                )
            )
            client = TestClient(create_app(db_path))

            detail = client.get("/collector/runs/xhs-preview")
            preview = client.get(f"/collector/runs/xhs-preview/posts/{post_id}")

            self.assertEqual(detail.status_code, 200)
            self.assertEqual(preview.status_code, 200)
            self.assertIn(f'href="/collector/runs/xhs-preview/posts/{post_id}"', detail.text)
            self.assertNotIn('href="https://www.xiaohongshu.com/explore/abc123"', detail.text)
            self.assertIn("样本预览", preview.text)
            self.assertIn("Local preview post", preview.text)
            self.assertIn("Preview this inside Falcon.", preview.text)
            self.assertIn("https://www.xiaohongshu.com/explore/abc123", preview.text)
            self.assertNotIn('target="_blank"', preview.text)

    def test_collector_post_preview_renders_local_image_video_carousel_and_asset_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            asset_root = tmp_path / "runtime" / "collector" / "xhs-assets" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "cover.jpg").write_bytes(b"fake image")
            (asset_root / "clip.mp4").write_bytes(b"fake video")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-assets",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-assets",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Carousel sample",
                    content="Preview local files.",
                    url="https://www.xiaohongshu.com/explore/carousel",
                    author="creator",
                    detail_fingerprint="carousel",
                )
            )
            image_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-assets",
                    post_id=post_id,
                    path="runtime/collector/xhs-assets/assets/cover.jpg",
                    asset_type="image",
                    sha256="imagehash",
                )
            )
            video_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-assets",
                    post_id=post_id,
                    path="runtime/collector/xhs-assets/assets/clip.mp4",
                    asset_type="video",
                    sha256="videohash",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get(f"/collector/runs/xhs-assets/posts/{post_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="sample-carousel"', response.text)
            self.assertIn("第 1 / 2 张", response.text)
            self.assertIn(f'src="/collector/runs/xhs-assets/assets/{image_id}"', response.text)
            self.assertIn(f'src="/collector/runs/xhs-assets/assets/{video_id}"', response.text)
            self.assertIn("<img", response.text)
            self.assertIn("<video", response.text)
            self.assertIn("controls", response.text)
            self.assertIn('class="thumbnail-track"', response.text)
            self.assertNotIn("imagehash", response.text)
            self.assertNotIn("videohash", response.text)
            self.assertNotIn("runtime/collector/xhs-assets/assets/cover.jpg", response.text)
            self.assertNotIn("runtime/collector/xhs-assets/assets/clip.mp4", response.text)
            self.assertIn("https://www.xiaohongshu.com/explore/carousel", response.text)
            self.assertNotIn('href="https://www.xiaohongshu.com/explore/carousel"', response.text)

    def test_collector_post_preview_replaces_asset_path_panel_with_body_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            asset_root = tmp_path / "runtime" / "collector" / "xhs-readable-preview" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "cover.jpg").write_bytes(b"fake image")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-readable-preview",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-readable-preview",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Readable sample",
                    content="Main body should sit beside the preview.",
                    url="https://www.xiaohongshu.com/explore/readable",
                    author="creator",
                    detail_fingerprint="readable",
                )
            )
            repo.save_collected_comment(
                CollectedComment(
                    run_id="xhs-readable-preview",
                    post_id=post_id,
                    commenter="reader",
                    content="Useful comment should replace asset paths.",
                    like_count="8",
                    comment_rank="1",
                )
            )
            repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-readable-preview",
                    post_id=post_id,
                    path="runtime/collector/xhs-readable-preview/assets/cover.jpg",
                    asset_type="image",
                    sha256="assetsha",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get(f"/collector/runs/xhs-readable-preview/posts/{post_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn("Main body should sit beside the preview.", response.text)
            self.assertIn("Useful comment should replace asset paths.", response.text)
            self.assertIn(f'src="/collector/runs/xhs-readable-preview/assets/', response.text)
            self.assertIn('class="panel asset-list-panel sample-copy-panel"', response.text)
            self.assertIn('class="sample-copy-scroll"', response.text)
            self.assertNotIn("runtime/collector/xhs-readable-preview/assets/cover.jpg", response.text)
            self.assertNotIn("assetsha", response.text)
            self.assertNotIn("图片 / 视频资产", response.text)

    def test_collector_post_preview_copy_panel_matches_preview_height_and_scrolls(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        panel_height_rule = css[
            css.index(".sample-preview-panel,\n.sample-copy-panel {")
            : css.index(".sample-preview-panel {")
        ]
        copy_panel_rule = css[css.index(".sample-copy-panel {") : css.index(".sample-copy-scroll {")]
        copy_scroll_rule = css[css.index(".sample-copy-scroll {") : css.index(".sample-copy-scroll::-webkit-scrollbar {")]

        self.assertIn("height: clamp(620px, calc(100vh - 170px), 760px)", panel_height_rule)
        self.assertIn("overflow: hidden", copy_panel_rule)
        self.assertIn("overflow-y: auto", copy_scroll_rule)
        self.assertIn("min-height: 0", copy_scroll_rule)

    def test_collector_post_preview_marks_missing_assets_and_falls_back_to_detail_screenshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            evidence_root = tmp_path / "runtime" / "collector" / "xhs-fallback" / "evidence"
            evidence_root.mkdir(parents=True)
            (evidence_root / "detail.png").write_bytes(b"fake screenshot")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-fallback",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-fallback",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Fallback sample",
                    content="Preview fallback.",
                    url="https://www.xiaohongshu.com/explore/fallback",
                    author="creator",
                    detail_fingerprint="fallback",
                )
            )
            missing_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-fallback",
                    post_id=post_id,
                    path="runtime/collector/xhs-fallback/assets/missing.jpg",
                    asset_type="image",
                    sha256="missinghash",
                )
            )
            evidence_id = repo.save_evidence(
                Evidence(
                    run_id="xhs-fallback",
                    evidence_type="detail_screenshot",
                    path="runtime/collector/xhs-fallback/evidence/detail.png",
                    scope="detail_screenshot",
                    payload_json='{"post_id": "fallback"}',
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get(f"/collector/runs/xhs-fallback/posts/{post_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn(f'src="/collector/runs/xhs-fallback/evidences/{evidence_id}"', response.text)
            self.assertNotIn(f'src="/collector/runs/xhs-fallback/assets/{missing_id}"', response.text)
            self.assertIn("详情页截图", response.text)
            self.assertNotIn("missinghash", response.text)

    def test_collector_post_preview_allows_project_runtime_asset_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "data" / "falcon.sqlite3"
            asset_root = tmp_path / "runtime" / "collector" / "xhs-project-runtime" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "cover.jpg").write_bytes(b"fake image")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-project-runtime",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-project-runtime",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Project runtime sample",
                    content="Preview project runtime file.",
                    url="https://www.xiaohongshu.com/explore/project-runtime",
                    author="creator",
                    detail_fingerprint="project-runtime",
                )
            )
            asset_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-project-runtime",
                    post_id=post_id,
                    path="runtime/collector/xhs-project-runtime/assets/cover.jpg",
                    asset_type="image",
                    sha256="projecthash",
                )
            )
            app = create_app(db_path)
            app.state.project_root = tmp_path
            client = TestClient(app)

            response = client.get(f"/collector/runs/xhs-project-runtime/posts/{post_id}")
            file_response = client.get(f"/collector/runs/xhs-project-runtime/assets/{asset_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn(f'src="/collector/runs/xhs-project-runtime/assets/{asset_id}"', response.text)
            self.assertNotIn("projecthash", response.text)
            self.assertEqual(file_response.status_code, 200)
            self.assertEqual(file_response.content, b"fake image")

    def test_collector_post_preview_does_not_render_json_placeholder_or_search_screenshot_as_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            asset_root = tmp_path / "runtime" / "collector" / "xhs-json-placeholder" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "image-placeholder.json").write_text('{"url":"https://example.test/image"}', encoding="utf-8")
            (asset_root / "search.png").write_bytes(b"fake screenshot")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-json-placeholder",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-json-placeholder",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="JSON placeholder sample",
                    content="Preview screenshot instead.",
                    url="https://www.xiaohongshu.com/explore/json-placeholder",
                    author="creator",
                    detail_fingerprint="json-placeholder",
                )
            )
            asset_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-json-placeholder",
                    post_id=post_id,
                    path="runtime/collector/xhs-json-placeholder/assets/image-placeholder.json",
                    asset_type="image",
                    sha256="jsonhash",
                )
            )
            evidence_id = repo.save_evidence(
                Evidence(
                    run_id="xhs-json-placeholder",
                    evidence_type="search_results_screenshot",
                    path="runtime/collector/xhs-json-placeholder/assets/search.png",
                    scope="search_results_screenshot",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get(f"/collector/runs/xhs-json-placeholder/posts/{post_id}")

            self.assertEqual(response.status_code, 200)
            self.assertNotIn("jsonhash", response.text)
            self.assertNotIn(f'src="/collector/runs/xhs-json-placeholder/assets/{asset_id}"', response.text)
            self.assertNotIn(f'src="/collector/runs/xhs-json-placeholder/evidences/{evidence_id}"', response.text)

    def test_collector_post_preview_only_uses_matching_detail_screenshot_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            evidence_root = tmp_path / "runtime" / "collector" / "xhs-detail-match" / "assets"
            evidence_root.mkdir(parents=True)
            (evidence_root / "search.png").write_bytes(b"search list screenshot")
            (evidence_root / "post-2-detail.png").write_bytes(b"post 2 detail screenshot")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-detail-match",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_1_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-detail-match",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Post without detail screenshot",
                    content="This post should not fall back to the search page.",
                    url="https://www.xiaohongshu.com/explore/post-1",
                    author="creator one",
                    detail_fingerprint="xiaohongshu:post-1",
                )
            )
            post_2_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-detail-match",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Post with detail screenshot",
                    content="This post has a matching detail screenshot.",
                    url="https://www.xiaohongshu.com/explore/post-2",
                    author="creator two",
                    detail_fingerprint="xiaohongshu:post-2",
                )
            )
            search_evidence_id = repo.save_evidence(
                Evidence(
                    run_id="xhs-detail-match",
                    evidence_type="search_results_screenshot",
                    path="runtime/collector/xhs-detail-match/assets/search.png",
                    scope="search_results_screenshot",
                    payload_json='{"keyword": "AI cover"}',
                )
            )
            detail_evidence_id = repo.save_evidence(
                Evidence(
                    run_id="xhs-detail-match",
                    evidence_type="detail_screenshot",
                    path="runtime/collector/xhs-detail-match/assets/post-2-detail.png",
                    scope="detail_screenshot",
                    payload_json='{"post_id": "xiaohongshu:post-2"}',
                )
            )
            client = TestClient(create_app(db_path))

            post_1_response = client.get(f"/collector/runs/xhs-detail-match/posts/{post_1_id}")
            post_2_response = client.get(f"/collector/runs/xhs-detail-match/posts/{post_2_id}")

            self.assertEqual(post_1_response.status_code, 200)
            self.assertNotIn(
                f'src="/collector/runs/xhs-detail-match/evidences/{search_evidence_id}"',
                post_1_response.text,
            )
            self.assertNotIn(
                f'src="/collector/runs/xhs-detail-match/evidences/{detail_evidence_id}"',
                post_1_response.text,
            )
            self.assertEqual(post_2_response.status_code, 200)
            self.assertIn(
                f'src="/collector/runs/xhs-detail-match/evidences/{detail_evidence_id}"',
                post_2_response.text,
            )
            self.assertNotIn(
                f'src="/collector/runs/xhs-detail-match/evidences/{search_evidence_id}"',
                post_2_response.text,
            )

    def test_collector_post_preview_prioritizes_detail_screenshot_before_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            asset_root = tmp_path / "runtime" / "collector" / "xhs-detail-first" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "detail.png").write_bytes(b"detail screenshot")
            (asset_root / "cover.jpg").write_bytes(b"downloaded cover")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-detail-first",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-detail-first",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Detail first sample",
                    content="Detail screenshot should be the first preview item.",
                    url="https://www.xiaohongshu.com/explore/detail-first",
                    author="creator",
                    detail_fingerprint="xiaohongshu:detail-first",
                )
            )
            asset_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-detail-first",
                    post_id=post_id,
                    path="runtime/collector/xhs-detail-first/assets/cover.jpg",
                    asset_type="image",
                    sha256="coverhash",
                )
            )
            evidence_id = repo.save_evidence(
                Evidence(
                    run_id="xhs-detail-first",
                    evidence_type="detail_screenshot",
                    path="runtime/collector/xhs-detail-first/assets/detail.png",
                    scope="detail_screenshot",
                    payload_json='{"post_id": "xiaohongshu:detail-first"}',
                )
            )
            repo.save_evidence(
                Evidence(
                    run_id="xhs-detail-first",
                    evidence_type="field_snapshot",
                    path="runtime/collector/xhs-detail-first/assets/detail-snapshot.json",
                    scope="field_snapshot",
                    payload_json='{"post_id": "xiaohongshu:detail-first", "media_scope": "detail_container"}',
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get(f"/collector/runs/xhs-detail-first/posts/{post_id}")

            self.assertEqual(response.status_code, 200)
            detail_src = f'src="/collector/runs/xhs-detail-first/evidences/{evidence_id}"'
            asset_src = f'src="/collector/runs/xhs-detail-first/assets/{asset_id}"'
            self.assertIn(detail_src, response.text)
            self.assertIn(asset_src, response.text)
            self.assertLess(response.text.index(detail_src), response.text.index(asset_src))

    def test_collector_post_preview_dedupes_media_and_shows_collects_and_reply_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            asset_root = tmp_path / "runtime" / "collector" / "xhs-preview-dedupe" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "detail.png").write_bytes(b"detail screenshot")
            (asset_root / "cover-detail.webp").write_bytes(b"detail cover")
            (asset_root / "cover-card.webp").write_bytes(b"card cover")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-preview-dedupe",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-preview-dedupe",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Preview metrics sample",
                    content="Preview body.",
                    url="https://www.xiaohongshu.com/explore/preview-dedupe",
                    author="creator",
                    like_count="24",
                    collect_count="10",
                    comment_count="37",
                    detail_fingerprint="xiaohongshu:preview-dedupe",
                )
            )
            first_asset_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-preview-dedupe",
                    post_id=post_id,
                    path="runtime/collector/xhs-preview-dedupe/assets/cover-detail.webp",
                    asset_type="image",
                    url="https://sns-webpic-qc.xhscdn.com/202605231943/da4f44570b3b857d293582c72529419e/notes_pre_post/1040g3k031ig9al7jns005nqfivhg9ckarv489h0!nd_dft_wlteh_webp_3",
                    sha256="detailcover",
                )
            )
            duplicate_asset_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-preview-dedupe",
                    post_id=post_id,
                    path="runtime/collector/xhs-preview-dedupe/assets/cover-card.webp",
                    asset_type="image",
                    url="https://sns-webpic-qc.xhscdn.com/202605231942/108d1b1f65ce49c82955b43c18a5a9fc/notes_pre_post/1040g3k031ig9al7jns005nqfivhg9ckarv489h0!nc_n_webp_mw_1",
                    sha256="cardcover",
                )
            )
            repo.save_collected_comment(
                CollectedComment(
                    post_id=post_id,
                    run_id="xhs-preview-dedupe",
                    commenter="replyer",
                    content="nested reply",
                    comment_rank="2",
                    comment_type="reply",
                    reply_to="target user",
                )
            )
            evidence_id = repo.save_evidence(
                Evidence(
                    run_id="xhs-preview-dedupe",
                    evidence_type="detail_screenshot",
                    path="runtime/collector/xhs-preview-dedupe/assets/detail.png",
                    scope="detail_screenshot",
                    payload_json='{"post_id": "xiaohongshu:preview-dedupe"}',
                )
            )
            repo.save_evidence(
                Evidence(
                    run_id="xhs-preview-dedupe",
                    evidence_type="field_snapshot",
                    path="runtime/collector/xhs-preview-dedupe/assets/detail-snapshot.json",
                    scope="field_snapshot",
                    payload_json='{"post_id": "xiaohongshu:preview-dedupe", "media_scope": "detail_container"}',
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get(f"/collector/runs/xhs-preview-dedupe/posts/{post_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn(f'src="/collector/runs/xhs-preview-dedupe/evidences/{evidence_id}"', response.text)
            self.assertIn(f'src="/collector/runs/xhs-preview-dedupe/assets/{first_asset_id}"', response.text)
            self.assertNotIn(f'src="/collector/runs/xhs-preview-dedupe/assets/{duplicate_asset_id}"', response.text)
            self.assertIn("点赞 24", response.text)
            self.assertIn("收藏 10", response.text)
            self.assertIn("评论 37", response.text)
            self.assertIn("回复", response.text)
            self.assertIn("回复给 target user", response.text)

    def test_collector_post_preview_hides_untrusted_media_when_detail_screenshot_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            asset_root = tmp_path / "runtime" / "collector" / "xhs-untrusted-media" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "detail.png").write_bytes(b"detail screenshot")
            (asset_root / "background-card.jpg").write_bytes(b"wrong background card")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-untrusted-media",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-untrusted-media",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Untrusted media sample",
                    content="Use the detail screenshot only.",
                    url="https://www.xiaohongshu.com/explore/untrusted-media",
                    author="creator",
                    detail_fingerprint="xiaohongshu:untrusted-media",
                )
            )
            asset_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-untrusted-media",
                    post_id=post_id,
                    path="runtime/collector/xhs-untrusted-media/assets/background-card.jpg",
                    asset_type="image",
                    sha256="wrongmedia",
                )
            )
            evidence_id = repo.save_evidence(
                Evidence(
                    run_id="xhs-untrusted-media",
                    evidence_type="detail_screenshot",
                    path="runtime/collector/xhs-untrusted-media/assets/detail.png",
                    scope="detail_screenshot",
                    payload_json='{"post_id": "xiaohongshu:untrusted-media"}',
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get(f"/collector/runs/xhs-untrusted-media/posts/{post_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn(f'src="/collector/runs/xhs-untrusted-media/evidences/{evidence_id}"', response.text)
            self.assertNotIn(f'src="/collector/runs/xhs-untrusted-media/assets/{asset_id}"', response.text)
            self.assertNotIn("wrongmedia", response.text)

    def test_collector_pages_display_chinese_status_and_event_vocabulary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-localized",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                    progress=100,
                    current_step="sidecar completed",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-localized",
                    sequence=1,
                    scope="collector",
                    event="run_completed",
                    level="info",
                    message="Collector run completed",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-localized",
                    sequence=2,
                    scope="dry_run_fixture",
                    event="record_collected",
                    level="info",
                    message="Collected fixture record",
                )
            )
            repo.save_evidence(
                Evidence(
                    run_id="xhs-localized",
                    evidence_type="dry_run_fixture",
                    path="runtime/collector/xhs-localized/evidence.json",
                    scope="dry_run_fixture",
                )
            )
            client = TestClient(create_app(db_path))

            overview = client.get("/collector")
            detail = client.get("/collector/runs/xhs-localized")

            self.assertEqual(overview.status_code, 200)
            self.assertEqual(detail.status_code, 200)
            self.assertIn("已完成", overview.text)
            self.assertIn("已完成", detail.text)
            self.assertIn("采集器已完成", detail.text)
            self.assertIn("采集器", detail.text)
            self.assertIn("任务完成", detail.text)
            self.assertIn("信息", detail.text)
            self.assertIn("采集任务已完成", detail.text)
            self.assertIn("采集合同", detail.text)
            self.assertIn("已生成采集合同记录", detail.text)
            self.assertNotIn("测试合同", detail.text)
            for raw in [
                ">completed<",
                "sidecar completed",
                "Collector run completed",
                ">run_completed<",
                ">info<",
            ]:
                self.assertNotIn(raw, detail.text)

    def test_analysis_overview_uses_existing_scored_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="AI cover",
                    source_type="post",
                    title="Need better covers",
                    content="How can I improve cover click-through?",
                    url="https://example.test/post/analysis",
                )
            )
            repo.save_analysis(
                raw_id,
                AnalysisResult(
                    scene_tag="xhs_cover",
                    intent_score=91,
                    content_value_score=84,
                    pain_point="cover click-through is low",
                    suggested_topic="Cover upgrade checklist",
                    recommended_action="write_topic",
                    outreach_type="comment_reply",
                    outreach_priority="high",
                    reason="clear pain point",
                ),
            )
            client = TestClient(create_app(db_path))

            response = client.get("/analysis")

            self.assertEqual(response.status_code, 200)
            self.assertIn("分析总览", response.text)
            self.assertIn('action="/analysis/promote"', response.text)
            self.assertIn("Cover upgrade checklist", response.text)
            self.assertIn('href="/analysis/samples"', response.text)
            assert_no_legacy_collection_markers(self, response.text)

    def test_analysis_promote_collected_posts_creates_raw_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-promote",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="completed",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-promote",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    title="Promote this sample",
                    content="Need a reusable cover workflow.",
                    url="local://collector/xhs-promote/post-1",
                    author="creator",
                    detail_fingerprint="promote-1",
                )
            )
            client = TestClient(create_app(db_path))

            client.post("/collector/runs/xhs-promote/relevance/score", follow_redirects=False)
            response = client.post("/analysis/promote", follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            raw_items = repo.list_raw_items()
            self.assertEqual(len(raw_items), 1)
            self.assertEqual(raw_items[0].title, "Promote this sample")

    def test_collector_run_detail_shows_relevance_quality_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-quality-gate",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    profile="default",
                    status="completed",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-quality-gate",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    title="AI头像生成工具测评",
                    content="这篇笔记完整对比了 AI头像 的风格、价格和使用场景。",
                    url="local://quality/1",
                    author="creator",
                    like_count="128",
                    detail_fingerprint="quality-1",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-quality-gate",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    title="AI绘画头像风格整理",
                    content="整理一些头像风格和关键词，可作为选题参考。",
                    url="local://quality/2",
                    author="creator",
                    detail_fingerprint="quality-2",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-quality-gate",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    title="宇宙壁纸真的太好看了",
                    content="收藏一些星空壁纸，完全没有头像制作或 AI 生成需求。",
                    url="local://quality/3",
                    author="creator",
                    detail_fingerprint="quality-3",
                )
            )
            client = TestClient(create_app(db_path))

            score_response = client.post("/collector/runs/xhs-quality-gate/relevance/score", follow_redirects=False)
            response = client.get("/collector/runs/xhs-quality-gate")

            self.assertEqual(score_response.status_code, 303)
            self.assertEqual(response.status_code, 200)
            self.assertIn("相关性质量闸门", response.text)
            self.assertIn("优质", response.text)
            self.assertIn("默认优质", response.text)
            self.assertIn("主分析", response.text)
            self.assertIn('class="relevance-gate-overview"', response.text)
            self.assertIn("可推进", response.text)
            self.assertIn('class="sample-filter-toolbar"', response.text)
            self.assertLess(response.text.index("采集样本"), response.text.index('class="sample-filter-toolbar"'))
            self.assertIn('data-relevance-filter="excellent"', response.text)

    def test_collector_post_preview_shows_relevance_breakdown_and_manual_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-post-relevance",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-post-relevance",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    title="AI头像生成工具测评",
                    content="这篇笔记完整对比了 AI头像 的风格、价格和使用场景。",
                    url="local://post-relevance/1",
                    author="creator",
                    detail_fingerprint="post-relevance-1",
                )
            )
            client = TestClient(create_app(db_path))

            client.post("/collector/runs/xhs-post-relevance/relevance/score", follow_redirects=False)
            response = client.get(f"/collector/runs/xhs-post-relevance/posts/{post_id}")
            override_response = client.post(
                f"/collector/runs/xhs-post-relevance/posts/{post_id}/relevance",
                data={"manual_relevance_level": "poor", "manual_relevance_note": "人工判断跑偏"},
                follow_redirects=False,
            )
            overridden = client.get(f"/collector/runs/xhs-post-relevance/posts/{post_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn("相关性评估", response.text)
            self.assertIn("默认质量", response.text)
            self.assertIn("默认判定", response.text)
            self.assertIn("人工纠正", response.text)
            self.assertIn('class="relevance-score-meter"', response.text)
            self.assertIn('class="manual-correction-bar"', response.text)
            self.assertIn('class="compact-select"', response.text)
            self.assertIn('class="compact-note"', response.text)
            self.assertEqual(override_response.status_code, 303)
            self.assertIn("人工修正", overridden.text)
            self.assertIn("人工判断跑偏", overridden.text)
            self.assertEqual(repo.get_collected_post(post_id).manual_relevance_level, "poor")

    def test_analysis_entry_uses_quality_pool_and_promotes_only_excellent_and_medium(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-analysis-quality",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    profile="default",
                    status="completed",
                )
            )
            for title, content, fingerprint in [
                (
                    "AI头像生成工具测评",
                    "这篇笔记完整对比了 AI头像 的风格、价格和使用场景。",
                    "analysis-quality-1",
                ),
                ("AI绘画头像风格整理", "整理一些头像风格和关键词，可作为选题参考。", "analysis-quality-2"),
                ("宇宙壁纸真的太好看了", "收藏一些星空壁纸，完全没有头像制作或 AI 生成需求。", "analysis-quality-3"),
            ]:
                repo.save_collected_post(
                    CollectedPost(
                        run_id="xhs-analysis-quality",
                        platform="xiaohongshu",
                        keyword="AI头像",
                        title=title,
                        content=content,
                        url=f"local://analysis-quality/{fingerprint}",
                        author="creator",
                        detail_fingerprint=fingerprint,
                    )
                )
            client = TestClient(create_app(db_path))

            client.post("/collector/runs/xhs-analysis-quality/relevance/score", follow_redirects=False)
            analysis_response = client.get("/analysis")
            promote_response = client.post("/analysis/promote", follow_redirects=False)

            self.assertEqual(analysis_response.status_code, 200)
            self.assertIn("采集质量入口", analysis_response.text)
            self.assertIn("优质主分析", analysis_response.text)
            self.assertEqual(promote_response.status_code, 303)
            self.assertEqual([item.relevance_role for item in repo.list_raw_items()], ["primary", "primary", "primary"])

    def test_execution_overview_uses_existing_outreach_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="AI cover",
                    source_type="post",
                    title="Execution candidate",
                    content="Need a reply",
                    url="https://example.test/post/execution",
                )
            )
            analysis = AnalysisResult(
                scene_tag="xhs_cover",
                intent_score=88,
                content_value_score=79,
                pain_point="needs cover advice",
                suggested_topic="reply draft",
                recommended_action="comment_reply",
                outreach_type="comment_reply",
                outreach_priority="high",
                reason="clear request",
            )
            analysis_id = repo.save_analysis(raw_id, analysis)
            repo.create_outreach_task(
                raw_id,
                analysis_id,
                analysis,
                [Draft(kind="comment_reply", text="Try a shorter title and stronger contrast.")],
                risk_note="human confirmation required",
            )
            client = TestClient(create_app(db_path))

            response = client.get("/execution")

            self.assertEqual(response.status_code, 200)
            self.assertIn("执行总览", response.text)
            self.assertIn("Execution candidate", response.text)
            self.assertIn("Try a shorter title", response.text)
            assert_no_legacy_collection_markers(self, response.text)


if __name__ == "__main__":
    unittest.main()
