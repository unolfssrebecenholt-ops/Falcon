import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "sidecar" / "collector" / "index.mjs"
SIDECAR_PACKAGE = ROOT / "sidecar" / "collector" / "package.json"


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class SidecarContractTests(unittest.TestCase):
    def test_sidecar_package_documents_playwright_dependency(self):
        package = json.loads(SIDECAR_PACKAGE.read_text(encoding="utf-8"))

        self.assertEqual(package["type"], "module")
        self.assertIn("playwright", package["dependencies"])
        self.assertIn("dry-run", package["scripts"])

    def run_sidecar(self, request, env=None):
        temp_root = Path(self.temp_dir.name)
        run_dir = temp_root / "runtime" / "collector" / request["run_id"]
        assets_dir = run_dir / "assets"
        profile_dir = (
            temp_root
            / "browser-profiles"
            / request["platform"]
            / request["profile"]
        )
        request_path = run_dir / "request.json"
        events_path = run_dir / "events.jsonl"
        records_path = run_dir / "records.jsonl"

        run_dir.mkdir(parents=True)
        request_path.write_text(
            json.dumps(request, ensure_ascii=False),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "node",
                str(SIDECAR),
                "--request",
                str(request_path),
                "--events",
                str(events_path),
                "--output",
                str(records_path),
                "--assets",
                str(assets_dir),
                "--profile",
                str(profile_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        return result, events_path, records_path, assets_dir

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_xiaohongshu_dry_run_writes_events_records_and_assets(self):
        result, events_path, records_path, assets_dir = self.run_sidecar(
            {
                "schema_version": 1,
                "run_id": "run-dry-xhs",
                "platform": "xiaohongshu",
                "profile": "default",
                "keyword": "AI出图助手",
                "max_posts": 2,
                "max_comments_per_post": 1,
                "headed": False,
                "dry_run": True,
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(assets_dir.is_dir())

        events = read_jsonl(events_path)
        self.assertGreaterEqual(len(events), 4)
        for index, event in enumerate(events, start=1):
            self.assertEqual(event["sequence"], index)
            self.assertIsInstance(event["time"], str)
            for field in [
                "level",
                "scope",
                "event",
                "message",
                "payload",
            ]:
                self.assertIn(field, event)

        event_types = {event["event"] for event in events}
        self.assertTrue(
            {
                "run_started",
                "profile_loaded",
                "record_collected",
                "run_completed",
            }.issubset(event_types)
        )

        records = read_jsonl(records_path)
        record_types = {record["type"] for record in records}
        self.assertTrue(
            {"post", "comment", "evidence", "media_asset"}.issubset(record_types)
        )
        for record in records:
            self.assertEqual(record.get("run_id"), "run-dry-xhs")
            if record["type"] != "evidence":
                self.assertEqual(record.get("platform"), "xiaohongshu")
            if record["type"] == "media_asset":
                self.assertTrue(Path(record["path"]).is_file())

    def test_unsupported_platform_writes_failure_event_and_exits_nonzero(self):
        result, events_path, records_path, assets_dir = self.run_sidecar(
            {
                "schema_version": 1,
                "run_id": "run-bad-platform",
                "platform": "unsupported",
                "profile": "default",
                "keyword": "AI出图助手",
                "max_posts": 1,
                "max_comments_per_post": 1,
                "headed": False,
                "dry_run": True,
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(assets_dir.is_dir())
        self.assertFalse(records_path.exists())

        events = read_jsonl(events_path)
        self.assertEqual(events[-1]["event"], "run_failed")
        self.assertEqual(events[-1]["payload"]["platform"], "unsupported")

    def test_xiaohongshu_real_mode_missing_playwright_is_clear_failure(self):
        env = {
            **dict(os.environ),
            "FALCON_COLLECTOR_FORCE_PLAYWRIGHT_MISSING": "1",
        }
        result, events_path, records_path, assets_dir = self.run_sidecar(
            {
                "schema_version": 1,
                "run_id": "run-real-missing-playwright",
                "platform": "xiaohongshu",
                "profile": "default",
                "keyword": "AI鍑哄浘鍔╂墜",
                "max_posts": 1,
                "max_comments_per_post": 0,
                "headed": True,
                "dry_run": False,
            },
            env=env,
        )

        self.assertEqual(result.returncode, 1)
        self.assertTrue(assets_dir.is_dir())
        self.assertFalse(records_path.exists())

        events = read_jsonl(events_path)
        self.assertEqual(events[-1]["event"], "run_failed")
        self.assertIn("Playwright is required", events[-1]["message"])
        self.assertIn("sidecar", events[-1]["message"])
        self.assertEqual(events[-1]["payload"]["code"], "PLAYWRIGHT_MISSING")


if __name__ == "__main__":
    unittest.main()
