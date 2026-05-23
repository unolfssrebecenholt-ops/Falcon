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
                    run_id="xhs-queued",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                )
            )
            client = TestClient(create_app(db_path))

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn("采集总览", response.text)
            self.assertIn("平台入口", response.text)
            self.assertIn("三层流转", response.text)
            self.assertIn("xhs-queued", response.text)
            assert_no_legacy_collection_markers(self, response.text)

    def test_collector_overview_shows_environment_doctor_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            report = DoctorReport(
                [
                    DoctorCheck("python", "Python", "ok", "3.11", True),
                    DoctorCheck("node", "Node.js", "missing", "not found", True, "node --version"),
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

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn('<details class="panel environment-panel" open>', response.text)
            self.assertIn("<summary", response.text)
            self.assertIn("展开明细", response.text)
            self.assertIn("收起明细", response.text)
            self.assertIn("环境自检", response.text)
            self.assertIn("状态", response.text)
            self.assertIn("作用", response.text)
            self.assertIn("路径 / 版本", response.text)
            self.assertIn("处理命令", response.text)
            self.assertIn("Node.js", response.text)
            self.assertIn("Playwright Chromium", response.text)
            self.assertIn("运行 Node Playwright sidecar", response.text)
            self.assertIn("node --version", response.text)

    def test_collector_environment_doctor_collapses_when_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "falcon.sqlite3"
            report = DoctorReport(
                [
                    DoctorCheck("python", "Python", "ok", "3.11", True),
                    DoctorCheck("node", "Node.js", "ok", "v24.14.0", True, "node --version"),
                ]
            )
            client = TestClient(create_app(db_path, doctor_report_builder=lambda _root: report))

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn('<details class="panel environment-panel">', response.text)
            self.assertNotIn('<details class="panel environment-panel" open>', response.text)
            self.assertIn("2/2 项就绪", response.text)

    def test_collector_overview_shows_profile_workspace_by_platform_account(self):
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

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn('action="/collector/profiles/open-login"', response.text)
            self.assertIn("platform/profile", response.text)
            self.assertIn("xiaohongshu/default", response.text)
            self.assertIn("xiaohongshu/backup", response.text)
            self.assertIn("douyin/creator", response.text)
            self.assertIn("browser-profiles", response.text)

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
            self.assertTrue(response.headers["location"].startswith("/collector?profile_action=opened"))
            self.assertEqual(len(launches), 1)
            self.assertEqual(launches[0]["platform"], "xiaohongshu")
            self.assertEqual(launches[0]["profile"], "creator")
            self.assertEqual(launches[0]["profile_path"], profile_root / "xiaohongshu" / "creator")

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
            self.assertIn("创建任务", response.text)
            self.assertIn('name="keyword"', response.text)
            self.assertIn('name="max_posts"', response.text)
            assert_no_legacy_collection_markers(self, response.text)

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
            self.assertTrue(response.headers["location"].endswith(f"/collector/runs/{runs[0].run_id}"))
            request_path = tmp_path / "runtime" / "collector" / runs[0].run_id / "request.json"
            self.assertTrue(request_path.exists())
            self.assertIn('"platform": "xiaohongshu"', request_path.read_text(encoding="utf-8"))

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
            assert_no_legacy_collection_markers(self, response.text)

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

            response = client.get("/collector")

            self.assertEqual(response.status_code, 200)
            self.assertIn("开启时间", response.text)
            self.assertIn("运行时长", response.text)
            self.assertIn("资源占用", response.text)
            self.assertIn("操作", response.text)
            self.assertIn("需人工处理", response.text)
            self.assertIn("已暂停", response.text)
            self.assertIn("无占用", response.text)
            self.assertIn("2026-05-23 16:14:07", response.text)
            self.assertIn("20 秒", response.text)
            self.assertIn('action="/collector/runs/xhs-manual/rerun"', response.text)
            self.assertIn('action="/collector/runs/xhs-manual/mark-failed"', response.text)
            self.assertIn('action="/collector/runs/xhs-manual/archive"', response.text)

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
            self.assertIn("Need better covers", response.text)
            self.assertIn("Cover upgrade checklist", response.text)
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

            response = client.post("/analysis/promote", follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            raw_items = repo.list_raw_items()
            self.assertEqual(len(raw_items), 1)
            self.assertEqual(raw_items[0].title, "Promote this sample")

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
