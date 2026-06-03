import json
import os
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
    IntentAnalysisMatch,
    IntentAnalysisProbe,
    IntentAnalysisTask,
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
                    keyword="内容运营",
                    source_type="post",
                    title="内容怎么做",
                    content="内容怎么做",
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
                    keyword="内容运营",
                    source_type="post",
                    title="内容怎么做",
                    content="内容怎么做",
                    url="https://example.com/1",
                )
            )
            analysis = AnalysisResult(
                scene_tag="content_performance",
                intent_score=90,
                content_value_score=80,
                pain_point="内容点击率低",
                suggested_topic="内容怎么做",
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
                    keyword="内容表现",
                    profile="default",
                    status="running",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-latest-completed",
                    platform="xiaohongshu",
                    keyword="账号增长",
                    profile="default",
                    status="completed",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-latest-failed",
                    platform="xiaohongshu",
                    keyword="失败复查",
                    profile="default",
                    status="failed",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn("采集总览", response.text)
            self.assertIn("最近状态", response.text)
            self.assertIn("平台入口", response.text)
            self.assertIn('class="running-attention-banner"', response.text)
            self.assertIn('class="platform-card active has-running"', response.text)
            self.assertIn("xhs-running", response.text)
            self.assertIn("失败任务", response.text)
            self.assertIn('href="/collector/runs?status=failed"', response.text)
            self.assertIn('class="panel recent-runs-panel"', response.text)
            self.assertNotIn('class="panel focus-panel"', response.text)
            self.assertNotIn("待处理焦点", response.text)
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
                    keyword="内容表现",
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

    def test_web_theme_uses_neutral_teal_glass_palette_without_purple(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )
        base_template = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "templates" / "base.html").read_text(
            encoding="utf-8"
        )

        body_rule = css[css.index("body {") : css.index(".inline-link {")]
        sidebar_rule = css[css.index(".sidebar {") : css.index(".brand {")]

        self.assertIn("--bg: #f6f7f9;", css)
        self.assertIn("--panel: #ffffff;", css)
        self.assertIn("--ink-strong: #121a24;", css)
        self.assertIn("--accent: #5f7190;", css)
        self.assertIn("--accent-dark: #52677f;", css)
        self.assertIn("--blue: #5f7190;", css)
        self.assertIn("--amber: #d89a36;", css)
        self.assertIn("--danger: #e36f61;", css)
        self.assertIn("--ok: #7f8794;", css)
        self.assertIn('font-size: 17px;', css[css.index("h1 {") : css.index("h2 {")])
        self.assertIn("position: sticky;", css[css.index(".topbar {") : css.index(".brand {")])
        self.assertIn(".nav-group.current", css)
        self.assertNotIn("radial-gradient(circle at 1px 1px", body_rule)
        self.assertNotIn("radial-gradient(circle at 1px 1px", sidebar_rule)
        for forbidden in ("#7467e8", "#df5aa8", "#7c5cff", "#ff4fb8", "#ece8f6"):
            self.assertNotIn(forbidden, css.lower())
        self.assertNotIn("graphite-sage-all-pages-20260524", base_template)
        self.assertNotIn("slate-command-reference-pages-20260524", base_template)
        self.assertNotIn("slate-command-soft-sage-pages-20260524", base_template)
        self.assertNotIn("slate-command-stone-moss-pages-", base_template)
        self.assertIn("controlled-color-v3-analysis-single-screen-v2", base_template)

    def test_help_tooltips_are_not_clipped_by_panels(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )
        panel_rule = css[css.index(".panel {") : css.index(".panel::before {")]
        hover_rule = css[css.index(".panel:has(.help-dot:hover)") : css.index(".panel.tight {")]
        dot_rule = css[css.index(".help-dot {") : css.index(".help-dot::after {")]
        tooltip_rule = css[css.index(".help-dot::after {") : css.index(".help-dot:hover::after")]

        self.assertIn("overflow: visible;", panel_rule)
        self.assertIn("z-index: 2147483000;", hover_rule)
        self.assertIn("overflow: visible;", hover_rule)
        self.assertIn("z-index: 2147483000;", dot_rule)
        self.assertIn("z-index: 2147483647;", tooltip_rule)

    def test_collector_overview_cards_use_v3_light_glass_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-v3-card-focus",
                    platform="xiaohongshu",
                    keyword="人工处理",
                    profile="default",
                    status="manual_action_required",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-v3-card-color",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-v3-running-chip",
                    platform="xiaohongshu",
                    keyword="ai氛围感女",
                    profile="default",
                    status="running",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector")
            css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
                encoding="utf-8"
            )
            marker = "/* v3 collector card light overrides keep overview cards off the old slate palette. */"

            self.assertEqual(response.status_code, 200)
            for html_class in (
                "status-cell",
                "recent-run-item",
                "platform-card",
                "health-metrics",
                "running-attention-list",
            ):
                self.assertIn(html_class, response.text)
            self.assertNotIn("focus-item", response.text)
            self.assertIn(marker, css)
            override = css[css.index(marker) :]
            self.assertGreater(css.index(marker), css.index(".recent-run-item {"))
            for selector in (
                ".status-cell",
                ".focus-item",
                ".recent-run-item",
                ".running-attention-list a",
                ".platform-card",
                ".health-metrics div",
                ".health-action",
            ):
                self.assertIn(selector, override)
            self.assertIn("rgba(239, 247, 246", override)
            self.assertIn("rgba(10, 166, 194", override)
            for legacy_slate in (
                "rgba(35, 50, 59",
                "rgba(28, 40, 48",
                "rgba(29, 43, 51",
                "rgba(26, 39, 46",
            ):
                self.assertNotIn(legacy_slate, override)

    def test_v3_light_overrides_cover_split_workbench_pages(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )
        marker = "/* v3 workbench light overrides neutralize legacy slate page components. */"

        self.assertIn(marker, css)
        override = css[css.index(marker) :]
        self.assertGreater(css.index(marker), css.index(".intent-run-picker {"))
        for selector in (
            ".page .queue-filters",
            ".page .queue-wrap",
            ".page .status-strip",
            ".page .account-summary-strip",
            ".page .account-platform-section",
            ".page .account-create-toolbar",
            ".page .environment-head",
            ".page .environment-row.header",
            ".page .intent-run-picker",
            ".page .intent-run-option",
            ".page input:not([type=\"checkbox\"]):not([type=\"radio\"])",
            ".page .queue-wrap thead th",
        ):
            self.assertIn(selector, override)
        self.assertIn("--v3-workbench-surface", override)
        self.assertIn("rgba(239, 247, 246", override)
        self.assertIn("rgba(247, 252, 253", override)
        self.assertIn("rgba(221, 237, 236", override)
        for legacy_slate in (
            "rgba(35, 50, 59",
            "rgba(28, 40, 48",
            "rgba(29, 43, 51",
            "rgba(26, 39, 46",
            "#2d404a",
            "#20303a",
            "#22323b",
        ):
            self.assertNotIn(legacy_slate, override)

    def test_v3_workspace_balance_uses_wide_operational_layouts(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )
        marker = "/* v3 workspace balance keeps operational pages from hugging the left on wide displays. */"

        self.assertIn(marker, css)
        override = css[css.index(marker) :]
        self.assertIn("width: min(1560px, 100%);", override)
        self.assertIn("margin-inline: auto;", override[override.index(".page {") : override.index(".page.doc {")])
        self.assertIn(".page[data-view=\"collector\"] .overview-grid", override)
        self.assertIn("grid-template-columns: minmax(0, 1.06fr) minmax(520px, 0.94fr);", override)
        self.assertIn(".page[data-view=\"collector\"] .health-metrics", override)
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr));", override)
        self.assertIn(".page[data-view=\"collector\"] .health-actions", override)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", override)
        self.assertIn(".collector-create-layout", override)
        self.assertIn("max-width: none;", override)
        self.assertIn("height: 89px;", override)
        self.assertIn("min-height: 89px;", override)
        self.assertIn(".page-header p {", css)
        header_copy_rule = css[css.index(".page-header p {") : css.index(".page-header h1,")]
        self.assertIn("white-space: nowrap;", header_copy_rule)
        self.assertIn("text-overflow: ellipsis;", header_copy_rule)
        self.assertNotIn(".family-inspector .page-header", css)
        self.assertIn(".report-reader", css)
        report_reader_rule = css[css.index(".report-reader") : css.index(".report-meta")]
        self.assertIn("width: min(860px, 100%);", report_reader_rule)
        self.assertIn("margin-inline: auto;", override)
        account_block = override[
            override.index(".page[data-view=\"collector_accounts\"] {") : override.index(
                ".page[data-view=\"collector_accounts\"]::before"
            )
        ]
        self.assertNotIn("width:", account_block)
        self.assertNotIn("margin-inline:", account_block)

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
            self.assertIn('class="panel recent-status-panel queue-health-panel"', response.text)
            self.assertIn('class="recent-status-body"', response.text)
            self.assertIn('class="health-metrics"', response.text)
            self.assertIn('class="health-actions"', response.text)
            self.assertIn("最近状态", response.text)
            self.assertIn("平台入口", response.text)
            self.assertNotIn('class="panel rhythm-panel"', response.text)
            self.assertNotIn("采集节奏", response.text)
            self.assertIn("运行中", response.text)
            self.assertIn("待人工", response.text)
            self.assertIn("待启动", response.text)
            self.assertIn('href="/collector/create"', response.text)
            self.assertIn('action="/collector/queue/start"', response.text)
            self.assertIn(".recent-status-panel.queue-health-panel", css)
            self.assertIn(".recent-status-body", css)
            self.assertIn(".health-metrics", css)
            self.assertIn("align-items: stretch", css)
            self.assertIn("min-height: 560px;", css)
            self.assertIn("max-height: clamp(420px, calc(100vh - 360px), 620px);", css)
            self.assertIn(".recent-run-list {\n  min-height: 0;", css)
            self.assertIn("overflow-y: auto;", css)

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
                    keyword="内容表现",
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
            self.assertIn('id="queue-create-task-open"', queue.text)
            self.assertIn('id="queue-create-task-dialog"', queue.text)
            self.assertIn('id="collector-create-form"', queue.text)
            self.assertIn('action="/collector/create"', queue.text)
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
                    keyword="内容表现",
                    source_type="post",
                    title="Need better content performance",
                    content="How can I improve content click-through?",
                    url="https://example.test/post/analysis-samples",
                )
            )
            repo.save_analysis(
                raw_id,
                AnalysisResult(
                    scene_tag="content_performance",
                    intent_score=91,
                    content_value_score=84,
                    pain_point="content click-through is low",
                    suggested_topic="Content performance checklist",
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
            self.assertIn("Need better content performance", samples_response.text)
            self.assertIn("Content performance checklist", samples_response.text)

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
            self.assertIn('href="/settings"', response.text)
            self.assertIn('class="settings-nav-link ', response.text)
            self.assertNotIn('<div class="nav-title"><span>基础</span>', response.text)
            nav_block = response.text[
                response.text.index('<nav class="nav-section-wrap">') : response.text.index('<div class="rail-settings"')
            ]
            self.assertNotIn('href="/collector/create"', nav_block)
            self.assertNotIn("任务创建", nav_block)

    def test_settings_page_groups_foundation_tools_as_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/settings")

            self.assertEqual(response.status_code, 200)
            self.assertIn("<h1>设置</h1>", response.text)
            self.assertIn('class="settings-card-grid"', response.text)
            self.assertIn('href="/keywords"', response.text)
            self.assertIn('href="/report"', response.text)
            self.assertIn('href="/settings/gpt"', response.text)
            self.assertIn("关键词池", response.text)
            self.assertIn("日报", response.text)
            self.assertIn("模型配置", response.text)

    def test_gpt_settings_page_reads_and_saves_local_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_keys = [
                "FALCON_GPT_BASE_URL",
                "FALCON_GPT_ENDPOINT",
                "FALCON_GPT_API_KEY",
                "FALCON_GPT_MODEL",
                "FALCON_GPT_TIMEOUT",
            ]
            previous_env = {key: os.environ.get(key) for key in env_keys}
            project_root = Path(tmp)
            db_path = project_root / "data" / "falcon.sqlite3"
            db_path.parent.mkdir()
            env_path = project_root / ".env"
            env_path.write_text(
                "FALCON_IMAGE2_MODEL=gpt-image-2\n"
                "FALCON_GPT_BASE_URL=https://old.example.com\n"
                "FALCON_GPT_API_KEY=old-secret-key\n",
                encoding="utf-8",
            )
            app = create_app(db_path)
            app.state.env_path = env_path
            client = TestClient(app)

            try:
                for key in env_keys:
                    os.environ.pop(key, None)
                page = client.get("/settings/gpt")
                saved = client.post(
                    "/settings/gpt",
                    data={
                        "base_url": "https://relay.example.com/",
                        "api_key": "sk-live-secret",
                    },
                    follow_redirects=False,
                )
                saved_page = client.get(saved.headers["location"])

                self.assertEqual(page.status_code, 200)
                self.assertIn("模型配置", page.text)
                self.assertIn('href="/settings"', page.text)
                self.assertIn('action="/settings/gpt"', page.text)
                self.assertIn('id="gpt-api-key-toggle"', page.text)
                self.assertIn("old-...-key", page.text)
                self.assertNotIn(">old-secret-key<", page.text)
                self.assertEqual(saved.status_code, 303)
                self.assertIn("GPT-5.5 配置已保存", saved_page.text)
                content = env_path.read_text(encoding="utf-8")
                self.assertIn("FALCON_IMAGE2_MODEL=gpt-image-2", content)
                self.assertIn("FALCON_GPT_BASE_URL=https://relay.example.com", content)
                self.assertIn("FALCON_GPT_ENDPOINT=/v1/responses", content)
                self.assertIn("FALCON_GPT_API_KEY=sk-live-secret", content)
                self.assertIn("FALCON_GPT_MODEL=gpt-5.5", content)
                self.assertIn("FALCON_GPT_TIMEOUT=60", content)
            finally:
                for key, value in previous_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_gpt_settings_page_reports_invalid_url_without_writing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            db_path = project_root / "data" / "falcon.sqlite3"
            db_path.parent.mkdir()
            env_path = project_root / ".env"
            env_path.write_text("FALCON_IMAGE2_MODEL=gpt-image-2\n", encoding="utf-8")
            app = create_app(db_path)
            app.state.env_path = env_path
            client = TestClient(app)

            response = client.post(
                "/settings/gpt",
                data={"base_url": "relay.example.com", "api_key": "secret"},
                follow_redirects=False,
            )
            page = client.get(response.headers["location"])

            self.assertEqual(response.status_code, 303)
            self.assertIn("GPT base URL must start with http", page.text)
            content = env_path.read_text(encoding="utf-8")
            self.assertIn("FALCON_IMAGE2_MODEL=gpt-image-2", content)
            self.assertNotIn("FALCON_GPT_API_KEY", content)

    def test_dashboard_uses_compact_v3_status_header_and_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="prototype-shell"', response.text)
            self.assertIn('class="topbar"', response.text)
            self.assertIn('class="rail-summary"', response.text)
            self.assertIn('class="nav-section-wrap"', response.text)
            self.assertIn('class="nav-group current"', response.text)
            self.assertIn('<main class="main"><div class="page family-overview" data-view="dashboard">', response.text)
            self.assertIn('<div class="eyebrow">workspace entry</div>', response.text)
            self.assertIn("<h1>仪表盘</h1>", response.text)
            self.assertIn("只作为工作台入口和关键待办，不再铺满一屏空面板。", response.text)
            self.assertIn("初始化数据库", response.text)
            self.assertIn("整理采集计划", response.text)

    def test_layout_redesign_applies_workbench_keywords_and_report_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            keyword_path = tmp_path / "keywords.csv"
            keyword_path.write_text(
                "theme,keyword,scene,weight,daily_limit\n"
                "账号增长,增长工具,growth,5,20\n",
                encoding="utf-8",
            )
            report_path = tmp_path / "daily-report.md"
            report_path.write_text("# Falcon 日报\n\n今日样本。", encoding="utf-8")
            client = TestClient(create_app(db_path))

            dashboard = client.get("/")
            keywords = client.get("/keywords", params={"path": str(keyword_path)})
            report = client.get("/report", params={"path": str(report_path)})

            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("仪表盘", dashboard.text)
            self.assertIn("只作为工作台入口和关键待办", dashboard.text)
            self.assertIn("今日待办", dashboard.text)
            self.assertIn("链路入口", dashboard.text)
            self.assertIn('href="/collector/create"', dashboard.text)
            self.assertIn('href="/analysis/samples"', dashboard.text)
            self.assertIn('href="/tasks"', dashboard.text)
            self.assertEqual(keywords.status_code, 200)
            self.assertIn("关键词配置", keywords.text)
            self.assertIn("关键词表", keywords.text)
            self.assertIn('class="keyword-layout"', keywords.text)
            self.assertIn("增长工具", keywords.text)
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
                    keyword="内容表现",
                    source_type="post",
                    title="Review operations candidate",
                    content="Need a reply",
                    url="https://example.test/post/review-execution",
                )
            )
            analysis = AnalysisResult(
                scene_tag="content_performance",
                intent_score=91,
                content_value_score=86,
                pain_point="content click-through is low",
                suggested_topic="Content performance checklist",
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
                [Draft(kind="comment_reply", text="Try a clearer title and one action.")],
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
            self.assertIn("Review operations candidate", review.text)
            self.assertNotIn('class="row-form"', review.text)
            self.assertEqual(execution.status_code, 200)
            self.assertIn("执行首页", execution.text)
            self.assertIn("待确认草稿队列", execution.text)
            self.assertIn("优先级概览", execution.text)
            self.assertIn('href="/tasks"', execution.text)
            self.assertIn("Try a clearer title", execution.text)
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
                    keyword="内容表现",
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
                    keyword="内容表现",
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

    def test_collector_overview_removes_actionable_focus_panel(self):
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
            self.assertNotIn('class="panel focus-panel"', response.text)
            self.assertNotIn("待处理焦点", response.text)
            self.assertNotIn('action="/collector/runs/xhs-focus-manual/open-manual-action"', response.text)
            self.assertNotIn('action="/collector/runs/xhs-focus-failed/rerun"', response.text)
            self.assertNotIn('action="/collector/runs/xhs-focus-queued/start"', response.text)
            self.assertIn("失败任务", response.text)
            self.assertIn('href="/collector/runs?status=failed"', response.text)

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
                    keyword="内容表现",
                    profile="default",
                    status="running",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="dy-queued",
                    platform="douyin",
                    keyword="内容表现",
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
            self.assertIn("平台是卡片", accounts.text)
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
                    keyword="内容表现",
                    profile="creator",
                    status="manual_action_required",
                )
            )
            client = TestClient(create_app(db_path, profile_root=profile_root))

            response = client.get("/collector/accounts")

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="page-header" aria-labelledby="account-redesign-title"', response.text)
            self.assertIn('<div class="eyebrow">profile control</div>', response.text)
            self.assertNotIn("account-redesign-hero", response.text)
            self.assertIn("account-platform-card", response.text)
            self.assertIn("account-redesign-list", response.text)
            self.assertIn("account-redesign-row", response.text)
            self.assertIn("account-redesign-create", response.text)
            self.assertIn("account-redesign-row-actions", response.text)
            self.assertIn("平台账号列表", response.text)
            self.assertNotIn("xiaohongshu/default", response.text)
            self.assertIn("xiaohongshu/backup", response.text)
            self.assertIn("xiaohongshu/creator", response.text)
            self.assertIn("等待人工", response.text)
            self.assertIn("登录", response.text)
            self.assertIn("检查", response.text)
            self.assertIn("退出", response.text)
            self.assertIn("新建 Profile", response.text)
            self.assertIn("英文、数字、点、下划线或短横线。", response.text)
            self.assertIn('action="/collector/profiles/logout"', response.text)
            self.assertNotIn("<select", response.text)
            css_path = Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css"
            css_text = css_path.read_text(encoding="utf-8")
            self.assertIn(".account-redesign-row-actions", css_text)
            self.assertIn(".account-redesign-create", css_text)
            self.assertIn(".account-platform-card", css_text)
            self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", css_text)
            self.assertIn("width: auto", css_text)
            self.assertNotIn(".account-actions", css_text)
            self.assertNotIn(".account-redesign-hero", css_text)

    def test_collector_accounts_redesign_route_redirects_to_accounts_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            client = TestClient(create_app(db_path, profile_root=profile_root))

            response = client.get(
                "/collector/accounts/redesign?profile_action=opened&profile_platform=xiaohongshu&profile_name=default",
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertEqual(
                response.headers["location"],
                "/collector/accounts?profile_action=opened&profile_platform=xiaohongshu&profile_name=default",
            )

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
                    keyword="内容表现",
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

    def test_desktop_shell_uses_sticky_topbar_and_sidebar_with_scrollable_nav(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        topbar_rule = css[css.index(".topbar {") : css.index(".brand {")]
        workspace_rule = css[css.index(".workspace-frame {") : css.index(".sidebar {")]
        sidebar_rule = css[css.index(".sidebar {") : css.index(".sidebar::-webkit-scrollbar")]
        nav_rule = css[css.index(".nav-section-wrap {") : css.index(".nav-section {")]
        main_rule = css[css.index(".main {") : css.index(".page {")]

        self.assertIn("position: sticky", topbar_rule)
        self.assertIn("top: 0", topbar_rule)
        self.assertIn("grid-template-columns: 224px minmax(0, 1fr)", workspace_rule)
        self.assertIn("position: sticky", sidebar_rule)
        self.assertIn("top: 64px", sidebar_rule)
        self.assertIn("height: calc(100vh - 64px)", sidebar_rule)
        self.assertIn("overflow-y: auto", sidebar_rule)
        self.assertIn("display: grid", nav_rule)
        self.assertIn("min-width: 0", main_rule)
        self.assertNotIn("margin-left: 232px", main_rule)

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
            ".settings-directory",
            ".settings-card-grid",
            ".settings-nav-link",
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
            invalid = client.post(
                "/collector/profiles/open-login",
                data={"platform": "xiaohongshu", "profile": "176扫码登录"},
                follow_redirects=False,
            )

            self.assertEqual(unsupported.status_code, 400)
            self.assertEqual(unsafe.status_code, 303)
            self.assertIn("profile_action=invalid", unsafe.headers["location"])
            self.assertEqual(invalid.status_code, 303)
            self.assertIn("profile_action=invalid", invalid.headers["location"])
            self.assertEqual(launches, [])
            self.assertFalse((tmp_path / "outside").exists())

            notice = client.get(invalid.headers["location"])
            self.assertEqual(notice.status_code, 200)
            self.assertIn("Profile 名称只能使用英文字母、数字", notice.text)
            self.assertIn('class="account-redesign-create is-invalid"', notice.text)
            self.assertIn('value="176扫码登录"', notice.text)
            self.assertIn("data-profile-error", notice.text)
            self.assertIn("data-profile-form", notice.text)
            self.assertIn('pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"', notice.text)

    def test_collector_create_get_renders_task_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertIn("创建任务", response.text)
            self.assertIn('name="keyword"', response.text)
            self.assertIn('name="max_posts"', response.text)
            self.assertIn('name="max_posts" type="number" min="1" max="30" value="8"', response.text)
            self.assertIn('name="max_comments_per_post" type="number" min="0" max="50" value="5"', response.text)
            self.assertIn("保存已加载图片", response.text)
            self.assertIn("截图回退", response.text)
            assert_no_legacy_collection_markers(self, response.text)

    def test_collector_create_get_renders_huashu_keyword_group_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.get("/collector/create")

            self.assertEqual(response.status_code, 200)
            self.assertIn("创建任务", response.text)
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
            self.assertNotIn('data-keyword="内容表现"', response.text)
            self.assertNotIn('data-keyword="增长案例"', response.text)
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

    def test_collector_safety_locked_profile_is_hidden_blocked_and_clearable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            profile_root = tmp_path / "browser-profiles"
            (profile_root / "xiaohongshu" / "default").mkdir(parents=True)
            safety_path = tmp_path / "runtime" / "collector" / "profile-safety" / "xiaohongshu" / "default.json"
            safety_path.parent.mkdir(parents=True)
            safety_path.write_text(
                json.dumps(
                    {
                        "platform": "xiaohongshu",
                        "profile": "default",
                        "locked": True,
                        "reason": "account_risk_warning",
                        "run_id": "risk-run",
                        "message": "账号违规预警",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(db_path, profile_root=profile_root))

            create_page = client.get("/collector/create")
            accounts_page = client.get("/collector/accounts")
            blocked_create = client.post(
                "/collector/create",
                data={
                    "platform": "xiaohongshu",
                    "profile": "default",
                    "keyword": "内容表现",
                    "max_posts": "5",
                    "max_comments_per_post": "1",
                },
                follow_redirects=False,
            )
            cleared = client.post(
                "/collector/profiles/clear-safety-lock",
                data={"platform": "xiaohongshu", "profile": "default"},
                follow_redirects=False,
            )
            create_after_clear = client.get("/collector/create")

            self.assertEqual(create_page.status_code, 200)
            self.assertNotIn('<option value="default"', create_page.text)
            self.assertIn("请先在账号管理创建 Profile", create_page.text)
            self.assertEqual(accounts_page.status_code, 200)
            self.assertIn("账号风控熔断", accounts_page.text)
            self.assertIn("解除熔断", accounts_page.text)
            self.assertEqual(blocked_create.status_code, 303)
            self.assertIn("profile_action=safety_locked", blocked_create.headers["location"])
            blocked_notice = client.get(blocked_create.headers["location"])
            self.assertIn("账号风控熔断锁正在保护 xiaohongshu/default", blocked_notice.text)
            self.assertIn("解除熔断", blocked_notice.text)
            self.assertEqual(cleared.status_code, 303)
            cleared_state = json.loads(safety_path.read_text(encoding="utf-8"))
            self.assertFalse(cleared_state["locked"])
            self.assertIn("profile_action=safety_cleared", cleared.headers["location"])
            self.assertIn('<option value="default" selected>', create_after_clear.text)

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
                    keyword="内容表现",
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
                    "keyword": "内容表现",
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
            self.assertEqual(runs[0].keyword, "内容表现")
            self.assertEqual(runs[0].profile, "creator")
            self.assertEqual(runs[0].max_posts, 7)
            self.assertEqual(response.headers["location"], "/collector/runs?status=queued&created=1")
            request_path = tmp_path / "runtime" / "collector" / runs[0].run_id / "request.json"
            self.assertTrue(request_path.exists())
            self.assertIn('"platform": "xiaohongshu"', request_path.read_text(encoding="utf-8"))

    def test_collector_create_post_clamps_comments_to_fifty(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            client = TestClient(create_app(db_path))

            response = client.post(
                "/collector/create",
                data={
                    "platform": "xiaohongshu",
                    "profile": "creator",
                    "keyword": "内容表现",
                    "max_posts": "7",
                    "max_comments_per_post": "80",
                },
                follow_redirects=False,
            )

            repo = FalconRepository(db_path)
            repo.init_schema()
            runs = repo.list_collection_runs()
            self.assertEqual(response.status_code, 303)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].max_comments_per_post, 50)
            request_path = tmp_path / "runtime" / "collector" / runs[0].run_id / "request.json"
            request_payload = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request_payload["max_comments_per_post"], 50)

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
                    "keywords": "内容表现\n增长案例，副业",
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
            self.assertEqual([run.keyword for run in runs], ["内容表现", "副业", "增长案例"])
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
                    "keyword": "内容表现",
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
                    "keyword": "内容表现",
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
                    keyword="内容表现",
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
                    keyword="内容表现",
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
            self.assertIn('data-visible-rows="4"', response.text)
            self.assertIn("显示 4 条", response.text)
            self.assertLess(response.text.index("采集样本"), response.text.index("事件链"))
            assert_no_legacy_collection_markers(self, response.text)

    def test_collector_run_detail_uses_compact_premium_information_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-compact-detail",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                    progress=100,
                    current_step="采集完成",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-compact-detail",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    title="高级感任务详情样本",
                    content="Useful notes",
                    url="https://example.test/post/compact",
                    author="creator",
                    detail_fingerprint="fp-compact",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-compact-detail",
                    sequence=1,
                    scope="search",
                    event="open_search",
                    message="Opened keyword search",
                )
            )
            repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-compact-detail",
                    post_id=post_id,
                    path="runtime/collector/xhs-compact-detail/assets/cover.jpg",
                    asset_type="image",
                    sha256="abc123",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs/xhs-compact-detail")

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="panel run-overview-card status-completed"', response.text)
            self.assertIn("任务运行概览", response.text)
            self.assertIn('class="run-overview-metrics"', response.text)
            self.assertIn('class="sample-title-link"', response.text)
            self.assertIn(f'href="/collector/runs/xhs-compact-detail/posts/{post_id}"', response.text)
            self.assertNotIn("<th>操作</th>", response.text)
            self.assertNotIn(">查看</a>", response.text)
            self.assertIn('class="panel evidence-switch-panel"', response.text)
            self.assertIn('class="evidence-tab-input"', response.text)
            self.assertIn('id="detail-tab-events"', response.text)
            self.assertIn('id="detail-tab-assets"', response.text)
            self.assertLess(response.text.index("事件链"), response.text.index("资产 / 证据摘要"))

    def test_collector_run_detail_shows_evidence_payload_summary_without_platform_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-evidence-summary",
                    platform="xiaohongshu",
                    keyword="content ops",
                    profile="default",
                    status="manual_action_required",
                )
            )
            repo.save_evidence(
                Evidence(
                    run_id="xhs-evidence-summary",
                    evidence_type="manual_action_snapshot",
                    scope="manual_action_snapshot",
                    path="runtime/collector/xhs-evidence-summary/assets/manual-action.json",
                    payload_json=json.dumps(
                        {
                            "reason": "account_risk_warning",
                            "url": "https://www.xiaohongshu.com/explore",
                            "title": "Account risk warning",
                            "matched_signals": ["risk control", "captcha"],
                        }
                    ),
                )
            )
            repo.save_evidence(
                Evidence(
                    run_id="xhs-evidence-summary",
                    evidence_type="manual_action_screenshot",
                    scope="manual_action_screenshot",
                    path="runtime/collector/xhs-evidence-summary/assets/manual-action.png",
                    payload_json=json.dumps({"reason": "account_risk_warning"}),
                )
            )
            repo.save_evidence(
                Evidence(
                    run_id="xhs-evidence-summary",
                    evidence_type="failure_snapshot",
                    scope="failure_snapshot",
                    path="runtime/collector/xhs-evidence-summary/assets/failure.json",
                    payload_json=json.dumps(
                        {
                            "reason": "SEARCH_NOT_CONFIRMED",
                            "url": "https://www.xiaohongshu.com/search_result",
                            "title": "Search confirmation failed",
                            "matched_signals": ["keyword not visible"],
                        }
                    ),
                )
            )
            repo.save_evidence(
                Evidence(
                    run_id="xhs-evidence-summary",
                    evidence_type="failure_screenshot",
                    scope="failure_screenshot",
                    path="runtime/collector/xhs-evidence-summary/assets/failure-search_not_confirmed.png",
                    payload_json=json.dumps({"reason": "SEARCH_NOT_CONFIRMED"}),
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs/xhs-evidence-summary")

            self.assertEqual(response.status_code, 200)
            self.assertIn("manual_action_snapshot", response.text)
            self.assertIn("manual_action_screenshot", response.text)
            self.assertIn("failure_snapshot", response.text)
            self.assertIn("failure_screenshot", response.text)
            self.assertIn("失败快照", response.text)
            self.assertIn("失败截图", response.text)
            self.assertIn("manual-action.json", response.text)
            self.assertIn("manual-action.png", response.text)
            self.assertIn("failure.json", response.text)
            self.assertIn("failure-search_not_confirmed.png", response.text)
            self.assertIn("account_risk_warning", response.text)
            self.assertIn("SEARCH_NOT_CONFIRMED", response.text)
            self.assertIn("https://www.xiaohongshu.com/explore", response.text)
            self.assertIn("Account risk warning", response.text)
            self.assertIn("risk control", response.text)
            self.assertNotIn('href="https://www.xiaohongshu.com/explore"', response.text)

    def test_collector_run_detail_previews_manual_action_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            evidence_root = Path(tmp) / "runtime" / "collector" / "xhs-manual-preview" / "assets"
            evidence_root.mkdir(parents=True)
            (evidence_root / "target-missing.png").write_bytes(b"fake screenshot")
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual-preview",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    profile="default",
                    status="manual_action_required",
                    progress=50,
                    current_step="瀑布流定位失败",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-manual-preview",
                    sequence=1,
                    scope="xiaohongshu",
                    event="manual_action_required",
                    message="target missing",
                    payload_json=(
                        '{"reason": "waterfall_target_missing", '
                        '"manual_action_url": "https://www.xiaohongshu.com/search_result/65abc123", '
                        '"url": "https://www.xiaohongshu.com/explore/65abc123"}'
                    ),
                )
            )
            evidence_id = repo.save_evidence(
                Evidence(
                    run_id="xhs-manual-preview",
                    evidence_type="detail_error_screenshot",
                    scope="detail_error_screenshot",
                    path="runtime/collector/xhs-manual-preview/assets/target-missing.png",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs/xhs-manual-preview")

            self.assertEqual(response.status_code, 200)
            self.assertIn('class="panel manual-action-context-panel"', response.text)
            self.assertIn(f'src="/collector/runs/xhs-manual-preview/evidences/{evidence_id}"', response.text)
            self.assertIn("waterfall_target_missing", response.text)
            self.assertIn("search_result?keyword=", response.text)
            self.assertIn(
                "source=web_search_result_notes",
                response.text,
            )
            self.assertNotIn("https://www.xiaohongshu.com/explore/65abc123", response.text)

    def test_collector_waterfall_target_missing_opens_search_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            profile_root = Path(tmp) / "browser-profiles"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-waterfall-scene",
                    platform="xiaohongshu",
                    keyword="ai氛围感女",
                    profile="default",
                    status="manual_action_required",
                    progress=50,
                    current_step="瀑布流定位第 17/30 条时未能找回目标卡片。",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-waterfall-scene",
                    sequence=1,
                    scope="xiaohongshu",
                    event="manual_action_required",
                    message="target missing",
                    payload_json=json.dumps(
                        {
                            "reason": "waterfall_target_missing",
                            "url": "https://www.xiaohongshu.com/search_result?keyword=ai%25E6%25B0%259B%25E5%259B%25B4%25E6%2584%259F%25E5%25A5%25B3&source=web_explore_feed",
                            "matched_signals": [
                                {
                                    "target_url": "https://www.xiaohongshu.com/explore/68ece859000000000302fdf7",
                                    "search_url": "https://www.xiaohongshu.com/search_result?keyword=ai%25E6%25B0%259B%25E5%259B%25B4%25E6%2584%259F%25E5%25A5%25B3&source=web_explore_feed",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            launches = []

            def fake_launcher(**kwargs):
                launches.append(kwargs)

            client = TestClient(create_app(db_path, profile_root=profile_root, profile_login_launcher=fake_launcher))

            detail = client.get("/collector/runs/xhs-waterfall-scene")
            response = client.post("/collector/runs/xhs-waterfall-scene/open-manual-action", follow_redirects=False)

            self.assertEqual(detail.status_code, 200)
            self.assertIn(
                "https://www.xiaohongshu.com/search_result?keyword=ai%25E6%25B0%259B%25E5%259B%25B4%25E6%2584%259F%25E5%25A5%25B3",
                detail.text,
            )
            self.assertNotIn("https://www.xiaohongshu.com/explore/68ece859000000000302fdf7", detail.text)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(len(launches), 1)
            self.assertEqual(
                launches[0]["url"],
                "https://www.xiaohongshu.com/search_result?keyword=ai%25E6%25B0%259B%25E5%259B%25B4%25E6%2584%259F%25E5%25A5%25B3&source=web_explore_feed",
            )

    def test_collector_run_detail_shows_waterfall_recovery_report_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-waterfall-report",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                    progress=100,
                    current_step="采集完成",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-waterfall-report",
                    sequence=1,
                    scope="xiaohongshu",
                    event="waterfall_target_skipped",
                    message="target missing",
                    payload_json='{"skipped_cards": 3, "recovery_threshold": 5}',
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-waterfall-report",
                    sequence=2,
                    scope="xiaohongshu",
                    event="waterfall_missing_threshold_recovery",
                    message="threshold recovery",
                    payload_json='{"skipped_cards": 5, "threshold_triggers": 1, "recovery_threshold": 5}',
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs/xhs-waterfall-report")

            self.assertEqual(response.status_code, 200)
            self.assertIn("跳过卡片数", response.text)
            self.assertIn("触发阈值数", response.text)
            self.assertIn("<strong>5</strong>", response.text)
            self.assertIn("<strong>1 / 5</strong>", response.text)

    def test_collector_run_detail_ledger_css_limits_panels_to_four_scrollable_rows(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        ledger_body_rule = css[css.index(".run-ledger-body {") : css.index(".run-ledger-body::-webkit-scrollbar {")]

        self.assertIn("max-height: calc(4 * 64px)", ledger_body_rule)
        self.assertIn("overflow-y: auto", ledger_body_rule)

    def test_collector_run_detail_sample_table_limits_to_four_scrollable_rows(self):
        css = (Path(__file__).resolve().parents[1] / "falcon" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        sample_table_rule = css[css.index(".sample-table-wrap {") : css.index(".sample-table-wrap thead th {")]

        self.assertIn("max-height: calc(43px + (4 * 56px))", sample_table_rule)
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
                    keyword="内容表现",
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
                    keyword="内容表现",
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
            self.assertIn('class="panel run-overview-card status-queued"', detail.text)
            self.assertIn("任务运行概览", detail.text)
            self.assertIn('action="/collector/runs/xhs-queued/start"', detail.text)

    def test_collector_failed_status_filter_is_defaulted_from_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-failed-filter",
                    platform="xiaohongshu",
                    keyword="失败复查",
                    profile="default",
                    status="failed",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector/runs?status=failed")

            self.assertEqual(response.status_code, 200)
            self.assertIn('data-status-filter="all" aria-pressed="false"', response.text)
            self.assertIn('data-status-filter="failed" aria-pressed="true"', response.text)
            self.assertIn('data-status="failed"', response.text)

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
                        keyword="内容表现",
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
                    keyword="内容表现",
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
                    keyword="内容表现",
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

    def test_collector_start_redirects_stale_failed_run_to_detail_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-stale-failed-start",
                    platform="xiaohongshu",
                    keyword="content ops",
                    profile="default",
                    status="failed",
                    progress=15,
                    current_step="采集器失败",
                    failed_reason="page.waitForTimeout: Target page, context or browser has been closed",
                )
            )
            launches = []
            client = TestClient(create_app(db_path, collector_run_launcher=lambda run_id: launches.append(run_id)))

            response = client.post("/collector/runs/xhs-stale-failed-start/start", follow_redirects=False)
            detail = client.get(response.headers["location"])

            repo = FalconRepository(db_path)
            repo.init_schema()
            run = repo.get_collection_run("xhs-stale-failed-start")
            self.assertEqual(response.status_code, 303)
            self.assertEqual(
                response.headers["location"],
                "/collector/runs/xhs-stale-failed-start?run_notice=start_stale_failed",
            )
            self.assertEqual(run.status, "failed")
            self.assertEqual(launches, [])
            self.assertIn("采集任务已经失败", detail.text)
            self.assertIn("page.waitForTimeout", detail.text)
            self.assertIn('action="/collector/runs/xhs-stale-failed-start/rerun"', detail.text)

    def test_collector_start_and_resume_redirect_safety_locked_profile_to_friendly_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-locked-start",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    profile="default",
                    status="queued",
                    current_step="等待浏览器采集调度",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-locked-resume",
                    platform="xiaohongshu",
                    keyword="增长案例",
                    profile="creator",
                    status="manual_action_required",
                    current_step="等待人工处理",
                )
            )
            safety_root = tmp_path / "runtime" / "collector" / "profile-safety" / "xiaohongshu"
            safety_root.mkdir(parents=True)
            for profile in ["default", "creator"]:
                (safety_root / f"{profile}.json").write_text(
                    json.dumps(
                        {
                            "platform": "xiaohongshu",
                            "profile": profile,
                            "locked": True,
                            "reason": "account_risk_warning",
                            "run_id": "risk-run",
                            "message": "账号违规预警",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            launches = []
            client = TestClient(create_app(db_path, collector_run_launcher=lambda run_id: launches.append(run_id)))

            start = client.post("/collector/runs/xhs-locked-start/start", follow_redirects=False)
            resume = client.post("/collector/runs/xhs-locked-resume/resume", follow_redirects=False)
            start_notice = client.get(start.headers["location"])
            resume_notice = client.get(resume.headers["location"])

            repo = FalconRepository(db_path)
            repo.init_schema()
            self.assertEqual(start.status_code, 303)
            self.assertEqual(resume.status_code, 303)
            self.assertIn("run_notice=safety_locked", start.headers["location"])
            self.assertIn("run_notice=safety_locked", resume.headers["location"])
            self.assertIn("账号风控熔断锁正在保护 xiaohongshu/default", start_notice.text)
            self.assertIn("账号风控熔断锁正在保护 xiaohongshu/creator", resume_notice.text)
            self.assertIn("去账号管理解除熔断", start_notice.text)
            self.assertIn("去账号管理解除熔断", resume_notice.text)
            self.assertNotIn("Collector profile is safety locked", start_notice.text)
            self.assertNotIn("Collector profile is safety locked", resume_notice.text)
            self.assertEqual(repo.get_collection_run("xhs-locked-start").status, "queued")
            self.assertEqual(repo.get_collection_run("xhs-locked-resume").status, "manual_action_required")
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
                    keyword="内容表现",
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
                    keyword="增长案例",
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
                    keyword="内容表现",
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
            self.assertEqual(
                launches[0]["url"],
                "https://www.xiaohongshu.com/search_result?keyword=%E5%86%85%E5%AE%B9%E8%A1%A8%E7%8E%B0&source=web_search_result_notes",
            )
            self.assertIn("manual_action_window_opened", {event.event for event in events})

    def test_collector_profile_busy_manual_action_does_not_open_another_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            profile_root = Path(tmp) / "browser-profiles"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-profile-busy",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    profile="default",
                    status="manual_action_required",
                    progress=5,
                    current_step="浏览器 Profile 正在被其他窗口占用。",
                )
            )
            repo.append_collection_event(
                CollectionEvent(
                    run_id="xhs-profile-busy",
                    sequence=1,
                    scope="xiaohongshu",
                    event="manual_action_required",
                    message="profile busy",
                    payload_json='{"reason": "profile_window_busy"}',
                )
            )
            launches = []

            def fake_launcher(**kwargs):
                launches.append(kwargs)

            client = TestClient(create_app(db_path, profile_root=profile_root, profile_login_launcher=fake_launcher))

            detail = client.get("/collector/runs/xhs-profile-busy")
            response = client.post("/collector/runs/xhs-profile-busy/open-manual-action", follow_redirects=False)

            self.assertEqual(detail.status_code, 200)
            self.assertNotIn('action="/collector/runs/xhs-profile-busy/open-manual-action"', detail.text)
            self.assertIn("关闭已打开的 xiaohongshu/default 浏览器窗口", detail.text)
            self.assertEqual(response.status_code, 400)
            self.assertIn("close the existing profile window", response.text)
            self.assertEqual(launches, [])

    def test_collector_manual_action_window_rejects_post_url_for_target_missing_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            profile_root = Path(tmp) / "browser-profiles"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual-post-url",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    payload_json='{"reason": "waterfall_target_missing", "url": "https://www.xiaohongshu.com/explore/65abc123"}',
                )
            )
            launches = []

            def fake_launcher(**kwargs):
                launches.append(kwargs)

            client = TestClient(create_app(db_path, profile_root=profile_root, profile_login_launcher=fake_launcher))

            response = client.post("/collector/runs/xhs-manual-post-url/open-manual-action", follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertEqual(len(launches), 1)
            self.assertEqual(
                launches[0]["url"],
                "https://www.xiaohongshu.com/search_result?keyword=%E5%86%85%E5%AE%B9%E8%A1%A8%E7%8E%B0&source=web_search_result_notes",
            )
            self.assertNotEqual(launches[0]["url"], "https://www.xiaohongshu.com/explore/65abc123")
            self.assertNotEqual(launches[0]["url"], "https://www.xiaohongshu.com/search_result/65abc123")

    def test_collector_manual_action_can_resume_same_run_after_user_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-manual-resume",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
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
                        keyword="内容表现",
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
            self.assertEqual(new_run.keyword, "内容表现")
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
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-preview",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-assets",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-readable-preview",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-fallback",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-project-runtime",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-json-placeholder",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_1_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-detail-match",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
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
                    payload_json='{"keyword": "内容表现"}',
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-detail-first",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-preview-dedupe",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-untrusted-media",
                    platform="xiaohongshu",
                    keyword="内容表现",
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
                    keyword="内容表现",
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
                    keyword="内容表现",
                    source_type="post",
                    title="Need better content performance",
                    content="How can I improve content click-through?",
                    url="https://example.test/post/analysis",
                )
            )
            repo.save_analysis(
                raw_id,
                AnalysisResult(
                    scene_tag="content_performance",
                    intent_score=91,
                    content_value_score=84,
                    pain_point="content click-through is low",
                    suggested_topic="Content performance checklist",
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
            self.assertIn("Content performance checklist", response.text)
            self.assertIn('href="/analysis/samples"', response.text)
            assert_no_legacy_collection_markers(self, response.text)

    def test_analysis_home_groups_runs_by_platform_and_creates_intent_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            for index, (run_id, keyword) in enumerate([("xhs-market-1", "生图软件"), ("xhs-market-2", "AI 工具")], start=1):
                repo.create_collection_run(
                    CollectionRun(
                        run_id=run_id,
                        platform="xiaohongshu",
                        keyword=keyword,
                        profile="default",
                        status="completed",
                        created_at=f"2026-05-25T0{index}:00:00+00:00",
                    )
                )
                post_id = repo.save_collected_post(
                    CollectedPost(
                        run_id=run_id,
                        platform="xiaohongshu",
                        keyword=keyword,
                        title=f"{keyword}帖子",
                        content=f"{keyword}正文",
                        url=f"local://{run_id}/post",
                        like_count=str(10 * index),
                        collect_count=str(5 * index),
                        comment_count="3",
                        detail_fingerprint=f"{run_id}-post",
                    )
                )
                repo.save_collected_comment(
                    CollectedComment(
                        post_id=post_id,
                        run_id=run_id,
                        commenter="reader",
                        content=f"{keyword}评论",
                        like_count=str(index),
                    )
                )
            repo.create_collection_run(
                CollectionRun(
                    run_id="douyin-market-1",
                    platform="douyin",
                    keyword="生图软件",
                    profile="default",
                    status="completed",
                )
            )
            client = TestClient(create_app(db_path))

            home = client.get("/analysis?platform=xiaohongshu")
            response = client.post(
                "/analysis/tasks",
                data={
                    "platform": "xiaohongshu",
                    "run_ids": ["xhs-market-1", "xhs-market-2"],
                    "user_intent": "我想分析生图软件的市场",
                },
                follow_redirects=False,
            )

            self.assertEqual(home.status_code, 200)
            self.assertIn("小红书", home.text)
            self.assertIn("抖音", home.text)
            self.assertIn('action="/analysis/tasks"', home.text)
            self.assertIn('class="analysis-command-shell"', home.text)
            self.assertIn('class="panel analysis-workbench"', home.text)
            self.assertIn('class="intent-run-list"', home.text)
            self.assertIn("生图软件 · 2026-05-25 09:00:00", home.text)
            self.assertIn("AI 工具 · 2026-05-25 10:00:00", home.text)
            self.assertIn("xhs-market-1", home.text)
            self.assertIn('data-posts="1"', home.text)
            self.assertIn('data-comments="3"', home.text)
            self.assertIn('data-likes="11"', home.text)
            self.assertIn('data-collects="5"', home.text)
            self.assertIn("质 未评", home.text)
            self.assertNotIn('value="douyin-market-1"', home.text)
            self.assertIn('action="/analysis/promote"', home.text)
            self.assertEqual(response.status_code, 303)
            task_id = int(response.headers["location"].rsplit("/", 1)[-1])
            task = repo.get_intent_analysis_task(task_id)
            self.assertEqual(task.platform, "xiaohongshu")
            self.assertEqual(task.user_intent, "我想分析生图软件的市场")
            self.assertEqual([source.run_id for source in repo.list_intent_analysis_sources(task_id)], ["xhs-market-1", "xhs-market-2"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="求推荐",
                    description="识别求推荐需求",
                    positive_signals="推荐",
                    negative_signals="无",
                    sort_order=1,
                )
            )
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-2",
                    title="纯展示",
                    description="识别纯展示",
                    positive_signals="展示",
                    negative_signals="需求",
                    sort_order=2,
                    enabled=False,
                )
            )

            history = client.get(f"/analysis?platform=xiaohongshu&reuse_task_id={task_id}")
            self.assertEqual(history.status_code, 200)
            self.assertIn('value="xhs-market-1" checked', history.text)
            self.assertIn('value="xhs-market-2" checked', history.text)
            self.assertIn("我想分析生图软件的市场", history.text)
            self.assertIn("2 个任务 · 2 篇帖子 · 2 条评论 · 1/2 个探针", history.text)
            self.assertIn(f'href="/analysis/tasks/{task_id}"', history.text)
            self.assertIn("继续编辑", history.text)
            self.assertIn("复用组合", history.text)
            self.assertIn(f'action="/analysis/tasks/{task_id}/delete"', history.text)
            self.assertIn("已采集的数据不会删除", history.text)
            self.assertIn("删除", history.text)
            self.assertIn("data-tip=", history.text)
            self.assertNotIn("复选", history.text)

            deleted = client.post(f"/analysis/tasks/{task_id}/delete", follow_redirects=False)
            self.assertEqual(deleted.status_code, 303)
            self.assertEqual(deleted.headers["location"], "/analysis?platform=xiaohongshu")
            self.assertIsNone(repo.get_intent_analysis_task(task_id))
            self.assertEqual(repo.list_intent_analysis_sources(task_id), [])
            self.assertEqual(repo.list_intent_analysis_probes(task_id), [])
            self.assertEqual(repo.get_collection_run("xhs-market-1").status, "completed")

    def test_analysis_task_detail_generates_edits_and_executes_probes(self):
        class FakeIntentService:
            def __init__(self, repository):
                self.repository = repository

            def generate_probes(self, task_id):
                probe_id = self.repository.save_intent_analysis_probe(
                    IntentAnalysisProbe(
                        task_id=task_id,
                        probe_key="probe-1",
                        title="求推荐生图工具",
                        description="识别正在寻找生图软件的人",
                        positive_signals="跪求\n推荐",
                        negative_signals="纯展示作品",
                        sort_order=1,
                    )
                )
                return [self.repository.get_intent_analysis_probe(probe_id)]

            def generate_probes_stream(self, task_id):
                yield {"type": "status", "message": "正在生成", "status": "generating_probes"}
                yield {"type": "delta", "text": '{"probes":'}
                probes = self.generate_probes(task_id)
                yield {"type": "done", "message": "探针已生成", "count": len(probes), "probes": probes}

            def execute_task(self, task_id):
                package = self.repository.build_intent_analysis_package(task_id)
                probe = self.repository.list_intent_analysis_probes(task_id)[0]
                post_id = int(package[0]["post_id"])
                comment_id = int(package[0]["comments"][0]["comment_id"])
                match = IntentAnalysisMatch(
                    task_id=task_id,
                    probe_id=probe.probe_id or 0,
                    probe_key=probe.probe_key,
                    post_id=post_id,
                    comment_id=comment_id,
                    level="comment",
                    score=94,
                    reason="评论直接求推荐",
                    excerpt="跪求好用的 image2 生图软件",
                )
                self.repository.save_intent_analysis_match(match)
                self.repository.update_intent_analysis_task(task_id, status="completed", completed_at="2026-05-25T00:00:00Z")
                return [match]

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-intent-detail",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-intent-detail",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    title="生图软件对比",
                    content="想知道哪些人需要生图软件。",
                    url="local://intent-detail/post-1",
                    detail_fingerprint="intent-detail-1",
                )
            )
            repo.save_collected_comment(
                CollectedComment(
                    post_id=post_id,
                    run_id="xhs-intent-detail",
                    commenter="reader",
                    content="跪求好用的 image2 生图软件推荐。",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想知道哪些人需要生图软件")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-intent-detail"])
            client = TestClient(create_app(db_path, intent_analysis_service_factory=FakeIntentService))

            detail = client.get(f"/analysis/tasks/{task_id}")
            streamed = client.post(f"/analysis/tasks/{task_id}/probes/generate/stream")
            generated = client.post(f"/analysis/tasks/{task_id}/probes/generate", follow_redirects=False)
            edited = client.post(
                f"/analysis/tasks/{task_id}/probes",
                data={
                    "probe_ids": "1",
                    "probe_key_1": "probe-1",
                    "title_1": "避雷生图工具",
                    "description_1": "识别正在吐槽或避雷生图软件的人",
                    "positive_signals_1": "避雷\n踩坑",
                    "negative_signals_1": "求推荐",
                    "enabled_1": "on",
                    "sort_order_1": "1",
                    "next_action": "execute",
                },
                follow_redirects=False,
            )
            final_detail = client.get(f"/analysis/tasks/{task_id}")

            self.assertEqual(detail.status_code, 200)
            self.assertIn("我想知道哪些人需要生图软件", detail.text)
            self.assertIn("xhs-intent-detail", detail.text)
            self.assertIn('action="/analysis/tasks/%d/probes/generate"' % task_id, detail.text)
            self.assertIn('data-stream-url="/analysis/tasks/%d/probes/generate/stream"' % task_id, detail.text)
            self.assertIn('id="probe-stream-panel"', detail.text)
            self.assertIn('class="probe-card-top"', detail.text)
            self.assertIn('class="probe-signal positive"', detail.text)
            self.assertIn('id="probe-create-dialog"', detail.text)
            self.assertIn("data-probe-modal-open", detail.text)
            self.assertIn('form="probe-editor-form"', detail.text)
            self.assertEqual(streamed.status_code, 200)
            self.assertIn("text/event-stream", streamed.headers["content-type"])
            self.assertIn("event: delta", streamed.text)
            self.assertIn("event: done", streamed.text)
            self.assertIn("redirect_url", streamed.text)
            self.assertEqual(generated.status_code, 303)
            self.assertEqual(edited.status_code, 303)
            self.assertEqual(repo.list_intent_analysis_probes(task_id)[0].title, "避雷生图工具")
            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "completed")
            self.assertIn("双层证据", final_detail.text)
            self.assertIn("生图软件对比", final_detail.text)
            self.assertIn("跪求好用的 image2 生图软件", final_detail.text)
            self.assertIn("评论直接求推荐", final_detail.text)

    def test_analysis_task_probe_edit_cannot_mutate_other_task_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            task_one = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="任务一")
            )
            task_two = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="任务二")
            )
            other_probe_id = repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_two,
                    probe_key="probe-1",
                    title="原始探针",
                    description="不能被任务一修改",
                    positive_signals="原始",
                    negative_signals="排除",
                    sort_order=1,
                )
            )
            client = TestClient(create_app(db_path))

            response = client.post(
                f"/analysis/tasks/{task_one}/probes",
                data={
                    "probe_ids": str(other_probe_id),
                    f"probe_key_{other_probe_id}": "probe-1",
                    f"title_{other_probe_id}": "被篡改",
                    f"description_{other_probe_id}": "跨任务修改",
                    f"positive_signals_{other_probe_id}": "篡改",
                    f"negative_signals_{other_probe_id}": "篡改",
                    f"enabled_{other_probe_id}": "on",
                    f"sort_order_{other_probe_id}": "1",
                },
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertEqual(repo.get_intent_analysis_probe(other_probe_id).title, "原始探针")

    def test_analysis_task_probe_edit_ignores_malformed_sort_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="任务")
            )
            probe_id = repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="原始探针",
                    description="原始描述",
                    positive_signals="原始",
                    negative_signals="排除",
                    sort_order=3,
                )
            )
            client = TestClient(create_app(db_path))

            response = client.post(
                f"/analysis/tasks/{task_id}/probes",
                data={
                    "probe_ids": str(probe_id),
                    f"probe_key_{probe_id}": "probe-1",
                    f"title_{probe_id}": "更新探针",
                    f"description_{probe_id}": "更新描述",
                    f"positive_signals_{probe_id}": "更新",
                    f"negative_signals_{probe_id}": "排除",
                    f"enabled_{probe_id}": "on",
                    f"sort_order_{probe_id}": "abc",
                },
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            probe = repo.get_intent_analysis_probe(probe_id)
            self.assertEqual(probe.title, "更新探针")
            self.assertEqual(probe.sort_order, 3)

    def test_analysis_promote_collected_posts_creates_raw_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-promote",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    profile="default",
                    status="completed",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-promote",
                    platform="xiaohongshu",
                    keyword="内容表现",
                    title="Promote this sample",
                    content="Need a reusable content workflow.",
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
                    keyword="账号增长",
                    profile="default",
                    status="completed",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-quality-gate",
                    platform="xiaohongshu",
                    keyword="账号增长",
                    title="账号增长工具测评",
                    content="这篇笔记完整对比了账号增长工具的功能、价格和使用场景。",
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
                    keyword="账号增长",
                    title="账号增长案例整理",
                    content="整理一些增长动作和关键词，可作为选题参考。",
                    url="local://quality/2",
                    author="creator",
                    detail_fingerprint="quality-2",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-quality-gate",
                    platform="xiaohongshu",
                    keyword="账号增长",
                    title="周末随手拍真的太好看了",
                    content="收藏一些星空壁纸，完全没有运营分析或增长需求。",
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
                    keyword="账号增长",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-post-relevance",
                    platform="xiaohongshu",
                    keyword="账号增长",
                    title="账号增长工具测评",
                    content="这篇笔记完整对比了账号增长工具的功能、价格和使用场景。",
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
                    keyword="账号增长",
                    profile="default",
                    status="completed",
                )
            )
            for title, content, fingerprint in [
                (
                    "账号增长工具测评",
                    "这篇笔记完整对比了账号增长工具的功能、价格和使用场景。",
                    "analysis-quality-1",
                ),
                ("账号增长案例整理", "整理一些增长动作和关键词，可作为选题参考。", "analysis-quality-2"),
                ("周末随手拍真的太好看了", "收藏一些星空壁纸，完全没有运营分析或增长需求。", "analysis-quality-3"),
            ]:
                repo.save_collected_post(
                    CollectedPost(
                        run_id="xhs-analysis-quality",
                        platform="xiaohongshu",
                        keyword="账号增长",
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
                    keyword="内容表现",
                    source_type="post",
                    title="Execution candidate",
                    content="Need a reply",
                    url="https://example.test/post/execution",
                )
            )
            analysis = AnalysisResult(
                scene_tag="content_performance",
                intent_score=88,
                content_value_score=79,
                pain_point="needs content advice",
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
                [Draft(kind="comment_reply", text="Try a shorter title and clearer action.")],
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
