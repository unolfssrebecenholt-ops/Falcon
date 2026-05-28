import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_bootstrap_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "falcon_bootstrap.py"
    spec = importlib.util.spec_from_file_location("falcon_bootstrap", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapScriptsTest(unittest.TestCase):
    def test_choose_available_port_returns_preferred_when_free(self):
        bootstrap = load_bootstrap_module()

        port = bootstrap.choose_available_port("127.0.0.1", 8765, can_bind=lambda _host, candidate: candidate == 8765)

        self.assertEqual(port, 8765)

    def test_choose_available_port_moves_to_next_free_port(self):
        bootstrap = load_bootstrap_module()

        port = bootstrap.choose_available_port("127.0.0.1", 8765, can_bind=lambda _host, candidate: candidate == 8767)

        self.assertEqual(port, 8767)

    def test_resolve_step_args_uses_platform_launcher_path(self):
        bootstrap = load_bootstrap_module()

        resolved = bootstrap.resolve_step_args(
            ["npx", "playwright", "--version"],
            which=lambda name: "C:/Program Files/nodejs/npx.cmd" if name == "npx" else None,
        )

        self.assertEqual(resolved, ["C:/Program Files/nodejs/npx.cmd", "playwright", "--version"])

    def test_build_bootstrap_steps_installs_deps_checks_environment_and_starts_web(self):
        bootstrap = load_bootstrap_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            steps = bootstrap.build_bootstrap_steps(
                root,
                python_executable="python-test",
                db_path=root / "data" / "falcon.sqlite3",
                host="127.0.0.1",
                port=8765,
                skip_install=False,
            )

            self.assertEqual(
                [step.label for step in steps],
                [
                    "Upgrade Python packaging tools",
                    "Install Python package",
                    "Install collector sidecar dependencies",
                    "Install Playwright Chromium",
                    "Initialize local database",
                    "Run Falcon doctor",
                    "Start Falcon web workbench",
                ],
            )
            self.assertEqual(
                steps[0].args,
                ["python-test", "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            )
            self.assertEqual(steps[1].args, ["python-test", "-m", "pip", "install", "-e", "."])
            self.assertEqual(steps[2].args, ["npm", "install"])
            self.assertEqual(steps[3].args, ["npx", "playwright", "install", "chromium"])
            self.assertIn("web", steps[-1].args)
            self.assertTrue(steps[-1].blocking)

    def test_build_bootstrap_steps_can_skip_install_for_fast_restart(self):
        bootstrap = load_bootstrap_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            steps = bootstrap.build_bootstrap_steps(
                root,
                python_executable="python-test",
                db_path=root / "data" / "falcon.sqlite3",
                host="127.0.0.1",
                port=8765,
                skip_install=True,
            )

            self.assertEqual(
                [step.label for step in steps],
                ["Initialize local database", "Run Falcon doctor", "Start Falcon web workbench"],
            )


if __name__ == "__main__":
    unittest.main()
