#!/usr/bin/env python3
import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import NamedTuple, Optional


class BootstrapStep(NamedTuple):
    label: str
    args: list[str]
    cwd: Path
    blocking: bool = False


def resolve_step_args(args: list[str], which=shutil.which) -> list[str]:
    resolved = list(args)
    if not resolved:
        return resolved
    executable = which(resolved[0])
    if executable:
        resolved[0] = executable
    return resolved


def can_bind_port(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def choose_available_port(host: str, preferred_port: int, can_bind=can_bind_port, attempts: int = 20) -> int:
    for offset in range(attempts):
        candidate = preferred_port + offset
        if can_bind(host, candidate):
            return candidate
    raise RuntimeError(f"No available port found from {preferred_port} to {preferred_port + attempts - 1}")


def build_bootstrap_steps(
    project_root: Path,
    python_executable: str,
    db_path: Path,
    host: str,
    port: int,
    skip_install: bool = False,
) -> list[BootstrapStep]:
    root = Path(project_root)
    sidecar_root = root / "sidecar" / "collector"
    db_arg = str(db_path)
    steps: list[BootstrapStep] = []
    if not skip_install:
        steps.extend(
            [
                BootstrapStep(
                    "Upgrade Python packaging tools",
                    [python_executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
                    root,
                ),
                BootstrapStep("Install Python package", [python_executable, "-m", "pip", "install", "-e", "."], root),
                BootstrapStep("Install collector sidecar dependencies", ["npm", "install"], sidecar_root),
                BootstrapStep("Install Playwright Chromium", ["npx", "playwright", "install", "chromium"], sidecar_root),
            ]
        )
    steps.extend(
        [
            BootstrapStep("Initialize local database", [python_executable, "-m", "falcon", "--db", db_arg, "init-db"], root),
            BootstrapStep(
                "Run Falcon doctor",
                [python_executable, "-m", "falcon", "doctor", "--project-root", str(root), "--ensure-dirs"],
                root,
            ),
            BootstrapStep(
                "Start Falcon web workbench",
                [python_executable, "-m", "falcon", "--db", db_arg, "web", "--host", host, "--port", str(port)],
                root,
                True,
            ),
        ]
    )
    return steps


def pid_file_path(project_root: Path) -> Path:
    return Path(project_root) / "runtime" / "falcon-web.pid"


def _remove_pid_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _run_step(step: BootstrapStep, pid_file: Optional[Path] = None) -> None:
    command = " ".join(step.args)
    print(f"\n==> {step.label}")
    print(f"cwd: {step.cwd}")
    print(command)
    resolved_args = resolve_step_args(step.args)
    if step.blocking and pid_file is not None:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(resolved_args, cwd=str(step.cwd))
        pid_file.write_text(str(process.pid), encoding="utf-8")
        try:
            process.wait()
        except KeyboardInterrupt:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    process.kill()
            raise SystemExit(130)
        finally:
            _remove_pid_file(pid_file)
        if process.returncode in {-15, 143}:
            return
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, resolved_args)
        return
    subprocess.run(resolved_args, cwd=str(step.cwd), check=True)


def run_steps(steps: list[BootstrapStep], dry_run: bool = False) -> None:
    pid_file = Path(os.environ["FALCON_WEB_PID_FILE"]) if os.environ.get("FALCON_WEB_PID_FILE") else None
    for step in steps:
        if dry_run:
            command = " ".join(step.args)
            print(f"\n==> {step.label}")
            print(f"cwd: {step.cwd}")
            print(command)
            continue
        _run_step(step, pid_file=pid_file)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap and start the Falcon local workbench")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--db", default="data/falcon.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--skip-install", action="store_true", help="Skip pip/npm/Playwright install steps")
    parser.add_argument("--doctor-only", action="store_true", help="Run dependency checks without starting the web app")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = project_root / db_path
    for path in [project_root / "data", project_root / "runtime" / "collector", project_root / "browser-profiles"]:
        path.mkdir(parents=True, exist_ok=True)
    os.environ["FALCON_WEB_PID_FILE"] = str(pid_file_path(project_root))

    selected_port = args.port if args.doctor_only else choose_available_port(args.host, args.port)
    if selected_port != args.port:
        print(f"Port {args.port} is busy; using http://{args.host}:{selected_port} instead.")

    if args.doctor_only:
        steps = [
            BootstrapStep(
                "Run Falcon doctor",
                [sys.executable, "-m", "falcon", "doctor", "--project-root", str(project_root), "--ensure-dirs"],
                project_root,
            )
        ]
    else:
        steps = build_bootstrap_steps(
            project_root,
            python_executable=sys.executable,
            db_path=db_path,
            host=args.host,
            port=selected_port,
            skip_install=args.skip_install,
        )

    if not args.no_open and not args.dry_run and not args.doctor_only:
        url = f"http://{args.host}:{selected_port}"
        print(f"\nFalcon workbench will open at {url}")
        threading.Timer(2.0, lambda: webbrowser.open(url)).start()

    run_steps(steps, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
