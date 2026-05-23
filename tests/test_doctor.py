import os
import tempfile
import unittest
from pathlib import Path

from falcon.cli import build_parser
from falcon.doctor import (
    CommandResult,
    build_doctor_report,
    ensure_project_directories,
    format_doctor_report,
    resolve_command_args,
)


class FakeRunner:
    def __init__(self, results):
        self.results = {tuple(key): value for key, value in results.items()}
        self.calls = []

    def __call__(self, args, cwd=None, timeout=10):
        key = tuple(args)
        self.calls.append((key, cwd, timeout))
        return self.results.get(key, CommandResult(returncode=1, stdout="", stderr="missing"))


class DoctorTest(unittest.TestCase):
    def test_cli_accepts_doctor_command(self):
        args = build_parser().parse_args(["doctor", "--project-root", "F:/projects/Falcon", "--ensure-dirs"])

        self.assertEqual(args.command, "doctor")
        self.assertEqual(args.project_root, "F:/projects/Falcon")
        self.assertTrue(args.ensure_dirs)

    def test_resolve_command_args_uses_platform_launcher_path(self):
        resolved = resolve_command_args(
            ["npm", "--version"],
            which=lambda name: "C:/Program Files/nodejs/npm.cmd" if name == "npm" else None,
        )

        self.assertEqual(resolved, ["C:/Program Files/nodejs/npm.cmd", "--version"])

    def test_doctor_report_marks_ready_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_project_directories(root)
            (root / "sidecar" / "collector" / "node_modules" / "playwright").mkdir(parents=True)
            (root / "sidecar" / "collector" / "package.json").write_text("{}", encoding="utf-8")
            runner = FakeRunner(
                {
                    ("node", "--version"): CommandResult(0, "v22.16.0\n", ""),
                    ("npm", "--version"): CommandResult(0, "10.9.2\n", ""),
                    (
                        "node",
                        "-e",
                        "const { chromium } = require('playwright'); const fs = require('fs'); const path = chromium.executablePath(); console.log(path); process.exit(fs.existsSync(path) ? 0 : 2);",
                    ): CommandResult(0, "C:/ms-playwright/chromium/chrome.exe\n", ""),
                }
            )
            env = {
                "FALCON_GPT_BASE_URL": "https://example.test",
                "FALCON_GPT_API_KEY": "secret",
                "FALCON_GPT_MODEL": "gpt-5.5",
                "FALCON_IMAGE2_PRIMARY_BASE_URL": "https://image.test",
                "FALCON_IMAGE2_PRIMARY_API_KEY": "secret",
            }

            report = build_doctor_report(root, runner=runner, env=env)

            self.assertTrue(report.required_ok)
            self.assertEqual(report.status_counts["ok"], len(report.checks))
            self.assertIn("node --version", [check.command for check in report.checks])

    def test_doctor_report_includes_local_runtime_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_project_directories(root)
            report = build_doctor_report(root, runner=FakeRunner({}), env={})

            labels = [check.label for check in report.checks]

            self.assertIn("Data directory", labels)
            self.assertIn("Collector runtime directory", labels)
            self.assertIn("Browser profiles directory", labels)

    def test_doctor_report_distinguishes_required_and_optional_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sidecar" / "collector" / "package.json").parent.mkdir(parents=True)
            (root / "sidecar" / "collector" / "package.json").write_text("{}", encoding="utf-8")
            runner = FakeRunner({})

            report = build_doctor_report(root, runner=runner, env={})

            self.assertFalse(report.required_ok)
            required_missing = [check.key for check in report.checks if check.required and check.status != "ok"]
            optional_missing = [check.key for check in report.checks if not check.required and check.status != "ok"]
            self.assertIn("node", required_missing)
            self.assertIn("npm", required_missing)
            self.assertIn("gpt55_config", optional_missing)
            self.assertIn("image2_config", optional_missing)

    def test_ensure_project_directories_creates_local_runtime_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            created = ensure_project_directories(root)

            self.assertEqual(
                sorted(path.relative_to(root).as_posix() for path in created),
                ["browser-profiles", "data", "runtime/collector"],
            )
            for path in created:
                self.assertTrue(path.is_dir())

    def test_format_doctor_report_hides_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = FakeRunner({})
            env = {
                "FALCON_GPT_BASE_URL": "https://example.test",
                "FALCON_GPT_API_KEY": "super-secret-key",
                "FALCON_IMAGE2_PRIMARY_API_KEY": "image-secret-key",
            }

            text = format_doctor_report(build_doctor_report(root, runner=runner, env=env))

            self.assertIn("Falcon environment doctor", text)
            self.assertNotIn("super-secret-key", text)
            self.assertNotIn("image-secret-key", text)


if __name__ == "__main__":
    unittest.main()
