#!/usr/bin/env python3
import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
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


def log_file_path(project_root: Path) -> Path:
    return Path(project_root) / "runtime" / "falcon-web.log"


def url_file_path(project_root: Path) -> Path:
    return Path(project_root) / "runtime" / "falcon-web.url"


def _remove_pid_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_pid(path: Path) -> Optional[int]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not text.isdigit():
        return None
    return int(text)


def _tail(path: Path, lines: int = 30) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    return "\n".join(content[-lines:])


def _wait_for_http(url: str, process: subprocess.Popen, log_file: Path, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        returncode = process.poll()
        if returncode is not None:
            log_tail = _tail(log_file)
            detail = f"\nRecent log:\n{log_tail}" if log_tail else ""
            raise RuntimeError(f"Falcon web process exited early with code {returncode}.{detail}")
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 500:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    log_tail = _tail(log_file)
    detail = f"\nRecent log:\n{log_tail}" if log_tail else ""
    raise TimeoutError(f"Falcon web did not respond at {url} within {timeout:.0f}s. {last_error}{detail}")


def _http_responds(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def _background_creationflags() -> int:
    if os.name != "nt":
        return 0
    flags = 0
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    return flags


def _start_background_process(step: BootstrapStep, pid_file: Path, log_file: Path, url_file: Path, url: str) -> None:
    resolved_args = resolve_step_args(step.args)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("ab") as log:
        process = subprocess.Popen(
            resolved_args,
            cwd=str(step.cwd),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
            creationflags=_background_creationflags(),
        )
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    url_file.write_text(f"{url}\n", encoding="utf-8")
    try:
        _wait_for_http(url, process, log_file)
    except Exception:
        if process.poll() is None:
            process.terminate()
        _remove_pid_file(pid_file)
        raise
    print(f"Falcon web started in background.")
    print(f"PID: {process.pid}")
    print(f"URL: {url}")
    print(f"Log: {log_file}")


def _run_step(
    step: BootstrapStep,
    pid_file: Optional[Path] = None,
    log_file: Optional[Path] = None,
    url_file: Optional[Path] = None,
    url: str = "",
    foreground: bool = True,
) -> None:
    command = " ".join(step.args)
    print(f"\n==> {step.label}")
    print(f"cwd: {step.cwd}")
    print(command)
    resolved_args = resolve_step_args(step.args)
    if step.blocking and pid_file is not None:
        if not foreground:
            if log_file is None or url_file is None or not url:
                raise ValueError("Background Falcon web startup requires log_file, url_file, and url")
            _start_background_process(step, pid_file=pid_file, log_file=log_file, url_file=url_file, url=url)
            return
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


def run_steps(
    steps: list[BootstrapStep],
    dry_run: bool = False,
    foreground: bool = False,
    project_root: Optional[Path] = None,
    url: str = "",
) -> None:
    pid_file = Path(os.environ["FALCON_WEB_PID_FILE"]) if os.environ.get("FALCON_WEB_PID_FILE") else None
    root = project_root or Path.cwd()
    log_file = log_file_path(root)
    url_file = url_file_path(root)
    for step in steps:
        if dry_run:
            command = " ".join(step.args)
            print(f"\n==> {step.label}")
            print(f"cwd: {step.cwd}")
            print(command)
            continue
        _run_step(
            step,
            pid_file=pid_file,
            log_file=log_file,
            url_file=url_file,
            url=url,
            foreground=foreground,
        )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap and start the Falcon local workbench")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--db", default="data/falcon.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--skip-install", action="store_true", help="Skip pip/npm/Playwright install steps")
    parser.add_argument("--doctor-only", action="store_true", help="Run dependency checks without starting the web app")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them")
    parser.add_argument("--open", dest="open_browser", action="store_true", help="Open the workbench in the system browser")
    parser.add_argument("--no-open", dest="open_browser", action="store_false", help="Do not open the browser automatically")
    parser.add_argument("--foreground", action="store_true", help="Run the web app in the current terminal")
    parser.add_argument("-SkipInstall", dest="skip_install", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-DoctorOnly", dest="doctor_only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-DryRun", dest="dry_run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-Open", dest="open_browser", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-NoOpen", dest="open_browser", action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("-Foreground", dest="foreground", action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(open_browser=False)
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = project_root / db_path
    for path in [project_root / "data", project_root / "runtime" / "collector", project_root / "browser-profiles"]:
        path.mkdir(parents=True, exist_ok=True)
    pid_path = pid_file_path(project_root)
    url_path = url_file_path(project_root)
    os.environ["FALCON_WEB_PID_FILE"] = str(pid_path)

    if not args.doctor_only and not args.dry_run and not args.foreground:
        existing_pid = _read_pid(pid_path)
        existing_url = ""
        try:
            existing_url = url_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            existing_url = f"http://{args.host}:{args.port}"
        if existing_pid and _process_is_running(existing_pid) and _http_responds(existing_url):
            print(f"Falcon web is already running.")
            print(f"PID: {existing_pid}")
            print(f"URL: {existing_url}")
            print(f"Log: {log_file_path(project_root)}")
            if args.open_browser:
                webbrowser.open(existing_url)
            return 0
        if existing_pid and not _process_is_running(existing_pid):
            _remove_pid_file(pid_path)

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

    url = f"http://{args.host}:{selected_port}"
    if args.open_browser and not args.dry_run and not args.doctor_only:
        print(f"\nFalcon workbench will open at {url}")
        if args.foreground:
            threading.Timer(2.0, lambda: webbrowser.open(url)).start()

    run_steps(steps, dry_run=args.dry_run, foreground=args.foreground, project_root=project_root, url=url)
    if args.open_browser and not args.dry_run and not args.doctor_only and not args.foreground:
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
