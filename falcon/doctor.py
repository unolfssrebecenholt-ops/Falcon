import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence


PLAYWRIGHT_CHROMIUM_CHECK = (
    "const { chromium } = require('playwright'); "
    "const fs = require('fs'); "
    "const path = chromium.executablePath(); "
    "console.log(path); "
    "process.exit(fs.existsSync(path) ? 0 : 2);"
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class DoctorCheck:
    key: str
    label: str
    status: str
    message: str
    required: bool = True
    command: str = ""


@dataclass(frozen=True)
class DoctorReport:
    checks: list[DoctorCheck]

    @property
    def required_ok(self) -> bool:
        return all(check.status == "ok" for check in self.checks if check.required)

    @property
    def status_counts(self) -> Counter:
        return Counter(check.status for check in self.checks)


CommandRunner = Callable[[Sequence[str], Optional[Path], int], CommandResult]


def resolve_command_args(args: Sequence[str], which: Callable[[str], Optional[str]] = shutil.which) -> list[str]:
    resolved = list(args)
    if not resolved:
        return resolved
    executable = which(resolved[0])
    if executable:
        resolved[0] = executable
    return resolved


def default_command_runner(args: Sequence[str], cwd: Optional[Path] = None, timeout: int = 10) -> CommandResult:
    try:
        resolved_args = resolve_command_args(args)
        completed = subprocess.run(
            resolved_args,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return CommandResult(returncode=127, stdout="", stderr=str(exc))
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def project_root_from_package() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_project_directories(project_root: Path) -> list[Path]:
    paths = [
        project_root / "data",
        project_root / "runtime" / "collector",
        project_root / "browser-profiles",
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    return paths


def build_doctor_report(
    project_root: Optional[Path] = None,
    runner: CommandRunner = default_command_runner,
    env: Optional[Mapping[str, str]] = None,
) -> DoctorReport:
    root = Path(project_root) if project_root is not None else project_root_from_package()
    environment = env if env is not None else os.environ
    checks = [
        _python_check(),
        _command_check("node", "Node.js", ("node", "--version"), runner=runner),
        _command_check("npm", "npm", ("npm", "--version"), runner=runner),
        _sidecar_package_check(root),
        _node_playwright_check(root),
        _playwright_chromium_check(root, runner),
        *_directory_checks(root),
        _gpt55_config_check(environment),
        _image2_config_check(environment),
    ]
    return DoctorReport(checks=checks)


def format_doctor_report(report: DoctorReport) -> str:
    lines = ["Falcon environment doctor", ""]
    for check in report.checks:
        required = "required" if check.required else "optional"
        command = f" [{check.command}]" if check.command else ""
        lines.append(f"- {check.status.upper()} {check.label} ({required}){command}: {check.message}")
    lines.append("")
    lines.append(f"Required checks: {'OK' if report.required_ok else 'ACTION NEEDED'}")
    return "\n".join(lines)


def checks_for_web(report: DoctorReport) -> list[dict[str, object]]:
    return [
        {
            "key": check.key,
            "label": check.label,
            "status": check.status,
            "status_label": _status_label(check.status),
            "message": check.message,
            "purpose": _check_purpose(check.key),
            "required": check.required,
            "command": check.command,
        }
        for check in report.checks
    ]


def _status_label(status: str) -> str:
    return {
        "ok": "正常",
        "warning": "可选",
        "missing": "缺失",
        "failed": "失败",
    }.get(status, status)


def _check_purpose(key: str) -> str:
    purposes = {
        "python": "运行 Falcon CLI、Web 工作台和本地 SQLite 调度。",
        "node": "运行 Node Playwright sidecar，承接真实浏览器采集动作。",
        "npm": "安装并锁定 sidecar 的 Node 依赖。",
        "sidecar_package": "定义采集 sidecar 的入口、依赖和采集合同。",
        "node_playwright": "提供浏览器自动化能力，用于打开、搜索、滚动和读取页面。",
        "playwright_chromium": "提供受控 Chromium 浏览器实例，承载小红书采集会话。",
        "data_dir": "保存本地 SQLite 数据库和项目运行数据。",
        "collector_runtime_dir": "保存每次采集的 request、events、records、assets 和证据。",
        "browser_profiles_dir": "保存平台账号 profile，用于复用人工登录状态。",
        "gpt55_config": "启用采集后的分析、briefing 和草稿生成。",
        "image2_config": "启用封面图和配图生成能力。",
    }
    return purposes.get(key, "支撑 Falcon 本地工作台运行。")


def _python_check() -> DoctorCheck:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info >= (3, 9)
    return DoctorCheck(
        key="python",
        label="Python",
        status="ok" if ok else "missing",
        message=f"{version} via {sys.executable}" if ok else f"{version}; Python 3.9+ is required",
        command="python --version",
    )


def _command_check(
    key: str,
    label: str,
    args: Sequence[str],
    runner: CommandRunner,
    cwd: Optional[Path] = None,
    required: bool = True,
) -> DoctorCheck:
    result = runner(args, cwd, 10)
    command = " ".join(args)
    if result.returncode == 0:
        version = (result.stdout or result.stderr).strip().splitlines()
        message = version[0] if version else "available"
        return DoctorCheck(key=key, label=label, status="ok", message=message, required=required, command=command)
    message = (result.stderr or result.stdout or "not found").strip().splitlines()
    return DoctorCheck(
        key=key,
        label=label,
        status="missing",
        message=message[0] if message else "not found",
        required=required,
        command=command,
    )


def _sidecar_package_check(root: Path) -> DoctorCheck:
    package_path = root / "sidecar" / "collector" / "package.json"
    if package_path.exists():
        return DoctorCheck(
            key="sidecar_package",
            label="Collector sidecar package",
            status="ok",
            message=str(package_path),
            command="sidecar/collector/package.json",
        )
    return DoctorCheck(
        key="sidecar_package",
        label="Collector sidecar package",
        status="missing",
        message="sidecar/collector/package.json was not found",
        command="sidecar/collector/package.json",
    )


def _node_playwright_check(root: Path) -> DoctorCheck:
    package_path = root / "sidecar" / "collector" / "node_modules" / "playwright" / "package.json"
    if package_path.exists() or package_path.parent.exists():
        return DoctorCheck(
            key="node_playwright",
            label="Node Playwright package",
            status="ok",
            message=str(package_path.parent),
            command="npm install",
        )
    return DoctorCheck(
        key="node_playwright",
        label="Node Playwright package",
        status="missing",
        message="run npm install in sidecar/collector",
        command="npm install",
    )


def _playwright_chromium_check(root: Path, runner: CommandRunner) -> DoctorCheck:
    sidecar_root = root / "sidecar" / "collector"
    args = ("node", "-e", PLAYWRIGHT_CHROMIUM_CHECK)
    result = runner(args, sidecar_root, 10)
    if result.returncode == 0:
        path = (result.stdout or "").strip().splitlines()
        return DoctorCheck(
            key="playwright_chromium",
            label="Playwright Chromium",
            status="ok",
            message=path[0] if path else "installed",
            command="npx playwright install chromium",
        )
    message = (result.stderr or result.stdout or "Chromium is not installed").strip().splitlines()
    return DoctorCheck(
        key="playwright_chromium",
        label="Playwright Chromium",
        status="missing",
        message=message[0] if message else "Chromium is not installed",
        command="npx playwright install chromium",
    )


def _directory_checks(root: Path) -> list[DoctorCheck]:
    directories = [
        ("data_dir", "Data directory", root / "data"),
        ("collector_runtime_dir", "Collector runtime directory", root / "runtime" / "collector"),
        ("browser_profiles_dir", "Browser profiles directory", root / "browser-profiles"),
    ]
    checks = []
    for key, label, path in directories:
        if path.is_dir():
            checks.append(DoctorCheck(key=key, label=label, status="ok", message=str(path), required=False))
        else:
            checks.append(
                DoctorCheck(
                    key=key,
                    label=label,
                    status="warning",
                    message=f"will be created by scripts/start or falcon doctor --ensure-dirs: {path}",
                    required=False,
                )
            )
    return checks


def _gpt55_config_check(env: Mapping[str, str]) -> DoctorCheck:
    configured = bool(env.get("FALCON_GPT_BASE_URL") and env.get("FALCON_GPT_API_KEY"))
    model = env.get("FALCON_GPT_MODEL", "gpt-5.5")
    if configured:
        return DoctorCheck(
            key="gpt55_config",
            label="GPT-5.5 relay config",
            status="ok",
            message=f"configured; model={model}",
            required=False,
        )
    return DoctorCheck(
        key="gpt55_config",
        label="GPT-5.5 relay config",
        status="warning",
        message="optional until GPT analysis/drafting is used",
        required=False,
    )


def _image2_config_check(env: Mapping[str, str]) -> DoctorCheck:
    primary = bool(env.get("FALCON_IMAGE2_PRIMARY_BASE_URL") and env.get("FALCON_IMAGE2_PRIMARY_API_KEY"))
    fallback = bool(env.get("FALCON_IMAGE2_FALLBACK_BASE_URL") and env.get("FALCON_IMAGE2_FALLBACK_API_KEY"))
    if primary or fallback:
        provider = "primary+fallback" if primary and fallback else "primary" if primary else "fallback"
        return DoctorCheck(
            key="image2_config",
            label="Image2 relay config",
            status="ok",
            message=f"configured provider={provider}",
            required=False,
        )
    return DoctorCheck(
        key="image2_config",
        label="Image2 relay config",
        status="warning",
        message="optional until image generation is used",
        required=False,
    )
