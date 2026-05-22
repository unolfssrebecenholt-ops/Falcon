import json
import os
import tempfile
import unittest
from pathlib import Path

from falcon.cli import build_parser, main
from falcon.collector import CollectorService
from falcon.db import FalconRepository
from falcon.models import CollectionRun


class CollectorServiceTest(unittest.TestCase):
    def test_cli_accepts_collector_commands(self):
        dry_run_args = build_parser().parse_args(
            [
                "--db",
                "data/falcon.sqlite3",
                "collector-dry-run",
                "--platform",
                "xiaohongshu",
                "--profile",
                "default",
                "--keyword",
                "AI出图助手",
                "--max-posts",
                "5",
            ]
        )
        run_args = build_parser().parse_args(
            [
                "--db",
                "data/falcon.sqlite3",
                "collector-run",
                "--platform",
                "xiaohongshu",
                "--profile",
                "default",
                "--keyword",
                "AI cover",
                "--max-posts",
                "5",
            ]
        )
        ingest_args = build_parser().parse_args(
            [
                "--db",
                "data/falcon.sqlite3",
                "collector-ingest",
                "--run-id",
                "xhs-run",
                "--events",
                "runtime/collector/xhs-run/events.jsonl",
                "--records",
                "runtime/collector/xhs-run/records.jsonl",
            ]
        )

        self.assertEqual(dry_run_args.command, "collector-dry-run")
        self.assertEqual(dry_run_args.platform, "xiaohongshu")
        self.assertEqual(dry_run_args.max_posts, 5)
        self.assertEqual(run_args.command, "collector-run")
        self.assertTrue(run_args.headed)
        self.assertEqual(ingest_args.command, "collector-ingest")
        self.assertEqual(ingest_args.run_id, "xhs-run")

    def test_cli_collector_dry_run_writes_database_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"

            exit_code = main(
                [
                    "--db",
                    str(db_path),
                    "collector-dry-run",
                    "--platform",
                    "xiaohongshu",
                    "--profile",
                    "default",
                    "--keyword",
                    "AI出图助手",
                    "--run-id",
                    "cli-dry-run",
                    "--runtime-root",
                    str(tmp_path / "runtime" / "collector"),
                    "--profile-root",
                    str(tmp_path / "browser-profiles"),
                ]
            )

            repo = FalconRepository(db_path)
            repo.init_schema()
            self.assertEqual(exit_code, 0)
            self.assertEqual(repo.get_collection_run("cli-dry-run").status, "completed")
            self.assertEqual(len(repo.list_collected_posts("cli-dry-run")), 1)

    def test_cli_collector_run_records_real_mode_dependency_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            old_value = os.environ.get("FALCON_COLLECTOR_FORCE_PLAYWRIGHT_MISSING")
            os.environ["FALCON_COLLECTOR_FORCE_PLAYWRIGHT_MISSING"] = "1"
            try:
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "collector-run",
                        "--platform",
                        "xiaohongshu",
                        "--profile",
                        "default",
                        "--keyword",
                        "AI cover",
                        "--run-id",
                        "cli-real-missing",
                        "--runtime-root",
                        str(tmp_path / "runtime" / "collector"),
                        "--profile-root",
                        str(tmp_path / "browser-profiles"),
                    ]
                )
            finally:
                if old_value is None:
                    os.environ.pop("FALCON_COLLECTOR_FORCE_PLAYWRIGHT_MISSING", None)
                else:
                    os.environ["FALCON_COLLECTOR_FORCE_PLAYWRIGHT_MISSING"] = old_value

            repo = FalconRepository(db_path)
            repo.init_schema()
            run = repo.get_collection_run("cli-real-missing")
            self.assertEqual(exit_code, 1)
            self.assertEqual(run.status, "failed")
            self.assertIn("Playwright is required", run.failed_reason)

    def test_dry_run_creates_request_runs_sidecar_and_ingests_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = FalconRepository(tmp_path / "falcon.sqlite3")
            repo.init_schema()
            service = CollectorService(
                repo,
                runtime_root=tmp_path / "runtime" / "collector",
                profile_root=tmp_path / "browser-profiles",
            )

            run = service.run_dry_run(
                platform="xiaohongshu",
                profile="default",
                keyword="AI出图助手",
                max_posts=2,
                max_comments_per_post=1,
                headed=False,
                run_id="xhs-dry-run",
            )

            run_dir = tmp_path / "runtime" / "collector" / "xhs-dry-run"
            request_path = run_dir / "request.json"

            self.assertEqual(run.run_id, "xhs-dry-run")
            self.assertEqual(repo.get_collection_run("xhs-dry-run").status, "completed")
            self.assertTrue(request_path.exists())
            self.assertTrue((run_dir / "events.jsonl").exists())
            self.assertTrue((run_dir / "records.jsonl").exists())
            self.assertTrue((run_dir / "assets" / "dry-run-xiaohongshu-placeholder.txt").exists())

            events = repo.list_collection_events("xhs-dry-run")
            posts = repo.list_collected_posts("xhs-dry-run")
            assets = repo.list_media_assets("xhs-dry-run")
            evidences = repo.list_evidences("xhs-dry-run")

            self.assertIn("run_started", {event.event for event in events})
            self.assertIn("run_completed", {event.event for event in events})
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0].platform, "xiaohongshu")
            self.assertEqual(posts[0].keyword, "AI出图助手")
            self.assertEqual(posts[0].comment_count, "1")
            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0].post_id, posts[0].post_id)
            self.assertEqual(len(evidences), 1)

    def test_collector_paths_reject_path_escape_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = FalconRepository(tmp_path / "falcon.sqlite3")
            repo.init_schema()
            service = CollectorService(
                repo,
                runtime_root=tmp_path / "runtime" / "collector",
                profile_root=tmp_path / "browser-profiles",
            )

            for run_id, platform, profile in [
                ("../outside", "xiaohongshu", "default"),
                ("xhs-run", "../platform", "default"),
                ("xhs-run", "xiaohongshu", "..\\outside"),
                ("C:/outside", "xiaohongshu", "default"),
            ]:
                with self.subTest(run_id=run_id, platform=platform, profile=profile):
                    with self.assertRaises(ValueError):
                        service.paths_for(run_id, platform, profile)

    def test_collector_generated_run_ids_include_entropy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = FalconRepository(tmp_path / "falcon.sqlite3")
            repo.init_schema()
            service = CollectorService(repo)

            first = service._new_run_id("xiaohongshu")
            second = service._new_run_id("xiaohongshu")

            self.assertNotEqual(first, second)
            self.assertTrue(first.startswith("xiaohongshu-"))
            service.paths_for(first, "xiaohongshu", "default")

    def test_ingest_failure_events_marks_run_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = FalconRepository(tmp_path / "falcon.sqlite3")
            repo.init_schema()
            service = CollectorService(
                repo,
                runtime_root=tmp_path / "runtime" / "collector",
                profile_root=tmp_path / "browser-profiles",
            )

            run = service.run_dry_run(
                platform="unsupported",
                profile="default",
                keyword="AI出图助手",
                run_id="bad-platform",
            )

            self.assertEqual(run.status, "failed")
            self.assertIn("Unsupported platform", run.failed_reason)
            events = repo.list_collection_events("bad-platform")
            self.assertEqual(events[-1].event, "run_failed")

    def test_cli_collector_ingest_updates_run_status_from_sidecar_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="ingest-run",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                    status="queued",
                )
            )
            run_dir = tmp_path / "runtime" / "collector" / "ingest-run"
            run_dir.mkdir(parents=True)
            events_path = run_dir / "events.jsonl"
            records_path = run_dir / "records.jsonl"
            events_path.write_text(
                "\n".join(
                    json.dumps(event)
                    for event in [
                        {
                            "sequence": 1,
                            "time": "2026-05-23T00:00:00+00:00",
                            "level": "info",
                            "scope": "collector",
                            "event": "run_started",
                            "message": "started",
                            "payload": {},
                        },
                        {
                            "sequence": 2,
                            "time": "2026-05-23T00:01:00+00:00",
                            "level": "info",
                            "scope": "collector",
                            "event": "run_completed",
                            "message": "completed",
                            "payload": {},
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            records_path.write_text(
                json.dumps(
                    {
                        "type": "post",
                        "run_id": "ingest-run",
                        "platform": "xiaohongshu",
                        "post_id": "post-1",
                        "keyword": "AI cover",
                        "title": "Ingested post",
                        "body": "Collected by external sidecar run.",
                        "url": "https://example.test/post/ingested",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "--db",
                    str(db_path),
                    "collector-ingest",
                    "--run-id",
                    "ingest-run",
                    "--events",
                    str(events_path),
                    "--records",
                    str(records_path),
                ]
            )

            run = repo.get_collection_run("ingest-run")
            self.assertEqual(exit_code, 0)
            self.assertEqual(run.status, "completed")
            self.assertEqual(run.progress, 100)
            self.assertEqual(len(repo.list_collected_posts("ingest-run")), 1)

    def test_collector_ingest_is_idempotent_for_repeated_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="repeat-run",
                    platform="xiaohongshu",
                    keyword="AI cover",
                    profile="default",
                )
            )
            service = CollectorService(repo)
            run_dir = tmp_path / "runtime" / "collector" / "repeat-run"
            run_dir.mkdir(parents=True)
            events_path = run_dir / "events.jsonl"
            records_path = run_dir / "records.jsonl"
            events_path.write_text(
                "\n".join(
                    json.dumps(event)
                    for event in [
                        {
                            "sequence": 1,
                            "time": "2026-05-23T00:00:00+00:00",
                            "level": "info",
                            "scope": "collector",
                            "event": "run_started",
                            "message": "started",
                            "payload": {},
                        },
                        {
                            "sequence": 2,
                            "time": "2026-05-23T00:01:00+00:00",
                            "level": "info",
                            "scope": "collector",
                            "event": "run_completed",
                            "message": "completed",
                            "payload": {},
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            records_path.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        {
                            "type": "post",
                            "run_id": "repeat-run",
                            "platform": "xiaohongshu",
                            "post_id": "post-1",
                            "keyword": "AI cover",
                            "title": "Repeat post",
                            "body": "Collected once.",
                            "url": "https://example.test/post/repeat",
                        },
                        {
                            "type": "comment",
                            "run_id": "repeat-run",
                            "platform": "xiaohongshu",
                            "comment_id": "comment-1",
                            "post_id": "post-1",
                            "body": "Repeat comment",
                            "author": {"display_name": "reader"},
                        },
                        {
                            "type": "media_asset",
                            "run_id": "repeat-run",
                            "platform": "xiaohongshu",
                            "asset_id": "asset-1",
                            "post_id": "post-1",
                            "media_type": "image",
                            "path": "runtime/collector/repeat-run/assets/asset-1.json",
                        },
                        {
                            "type": "evidence",
                            "run_id": "repeat-run",
                            "platform": "xiaohongshu",
                            "evidence_id": "evidence-1",
                            "scope": "field_snapshot",
                            "path": "runtime/collector/repeat-run/assets/evidence-1.json",
                            "payload": {"ok": True},
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            service.ingest_outputs("repeat-run", events_path, records_path)
            service.ingest_outputs("repeat-run", events_path, records_path)

            self.assertEqual(len(repo.list_collection_events("repeat-run")), 2)
            self.assertEqual(len(repo.list_collected_posts("repeat-run")), 1)
            self.assertEqual(self._count_rows(db_path, "collected_comments"), 1)
            self.assertEqual(len(repo.list_media_assets("repeat-run")), 1)
            self.assertEqual(len(repo.list_evidences("repeat-run")), 1)

    def _count_rows(self, db_path: Path, table: str) -> int:
        import sqlite3
        from contextlib import closing

        with closing(sqlite3.connect(db_path)) as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0])


if __name__ == "__main__":
    unittest.main()
