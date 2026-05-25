from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from .collector import safe_collector_identifier


SUPPORTED_PROFILE_LOGIN_PLATFORMS = {
    "xiaohongshu": "https://www.xiaohongshu.com/",
}

@dataclass
class ProfileEntry:
    platform: str
    profile: str
    key: str
    profile_path: Path
    display_path: str
    path_exists: bool
    login_supported: bool
    status_label: str
    status_kind: str
    queue_label: str
    total_runs: int
    running_runs: int
    queued_runs: int
    manual_runs: int
    can_logout: bool
    safety_locked: bool = False
    safety_reason: str = ""
    safety_message: str = ""


def list_profile_entries(profile_root: Path, runs, platform_keys, safety_states=None) -> list[ProfileEntry]:
    profile_root = Path(profile_root)
    allowed_platforms = set(platform_keys)
    safety_states = safety_states or {}
    pairs = set()
    run_list = list(runs)

    for run in run_list:
        pairs.add((run.platform, run.profile))

    if profile_root.exists():
        for platform_dir in profile_root.iterdir():
            if not platform_dir.is_dir():
                continue
            try:
                platform = safe_collector_identifier(platform_dir.name, "platform")
            except ValueError:
                continue
            for profile_dir in platform_dir.iterdir():
                if not profile_dir.is_dir():
                    continue
                try:
                    profile = safe_collector_identifier(profile_dir.name, "profile")
                except ValueError:
                    continue
                pairs.add((platform, profile))

    counts = Counter((run.platform, run.profile, run.status) for run in run_list)
    totals = Counter((run.platform, run.profile) for run in run_list)
    entries = []
    for platform, profile in sorted(pairs):
        if platform not in allowed_platforms:
            continue
        profile_path = profile_root / platform / profile
        running = counts.get((platform, profile, "running"), 0)
        queued = counts.get((platform, profile, "queued"), 0)
        manual = counts.get((platform, profile, "manual_action_required"), 0)
        path_exists = profile_path.exists()
        safety_state = safety_states.get((platform, profile), {})
        safety_locked = bool(safety_state.get("locked"))
        entries.append(
            ProfileEntry(
                platform=platform,
                profile=profile,
                key=f"{platform}/{profile}",
                profile_path=profile_path,
                display_path=str(Path("browser-profiles") / platform / profile),
                path_exists=path_exists,
                login_supported=platform in SUPPORTED_PROFILE_LOGIN_PLATFORMS,
                status_label="账号风控熔断" if safety_locked else _profile_status_label(path_exists, running, queued, manual),
                status_kind="safety_locked" if safety_locked else _profile_status_kind(path_exists, running, queued, manual),
                queue_label=f"运行 {running} / 排队 {queued} / 人工 {manual}",
                total_runs=totals.get((platform, profile), 0),
                running_runs=running,
                queued_runs=queued,
                manual_runs=manual,
                can_logout=path_exists and running == 0 and queued == 0 and manual == 0 and not safety_locked,
                safety_locked=safety_locked,
                safety_reason=str(safety_state.get("reason") or ""),
                safety_message=str(safety_state.get("message") or ""),
            )
        )
    return entries


def launch_profile_login(
    *,
    platform: str,
    profile: str,
    profile_root: Path,
    profile_path: Path,
    project_root: Path,
    url: str = "",
    node_executable: str = "node",
):
    platform = safe_collector_identifier(platform, "platform")
    profile = safe_collector_identifier(profile, "profile")
    if platform not in SUPPORTED_PROFILE_LOGIN_PLATFORMS:
        raise ValueError(f"Profile login is not supported for platform: {platform}")

    profile_root = Path(profile_root)
    profile_path = Path(profile_path)
    resolved_root = profile_root.resolve()
    resolved_profile_path = profile_path.resolve()
    if resolved_profile_path != resolved_root and resolved_root not in resolved_profile_path.parents:
        raise ValueError("Profile path must stay inside the configured profile root")
    profile_path.mkdir(parents=True, exist_ok=True)
    project_root = Path(project_root)
    script_path = project_root / "sidecar" / "collector" / "profile-login.mjs"
    if not script_path.exists():
        raise FileNotFoundError(script_path)
    command = [
        node_executable,
        str(script_path),
        "--platform",
        platform,
        "--profile",
        profile,
        "--profile-path",
        str(profile_path),
    ]
    target_url = url or SUPPORTED_PROFILE_LOGIN_PLATFORMS[platform]
    if target_url:
        command.extend(["--url", target_url])
    process = subprocess.Popen(
        command,
        cwd=str(project_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {
        "pid": process.pid,
        "platform": platform,
        "profile": profile,
        "profile_path": profile_path,
        "url": target_url,
        "command": command,
    }


def clear_profile_directory(*, platform: str, profile: str, profile_root: Path, profile_path: Path) -> Path:
    platform = safe_collector_identifier(platform, "platform")
    profile = safe_collector_identifier(profile, "profile")
    profile_root = Path(profile_root)
    profile_path = Path(profile_path)
    resolved_root = profile_root.resolve()
    resolved_profile_path = profile_path.resolve()
    if resolved_profile_path == resolved_root or resolved_root not in resolved_profile_path.parents:
        raise ValueError("Profile path must stay inside the configured profile root")
    expected_path = profile_root / platform / profile
    if resolved_profile_path != expected_path.resolve():
        raise ValueError("Profile path does not match platform/profile")
    if not profile_path.exists():
        return profile_path
    if not profile_path.is_dir():
        raise ValueError("Profile path must be a directory")
    shutil.rmtree(profile_path)
    return profile_path


def _profile_status_label(path_exists: bool, running: int, queued: int, manual: int) -> str:
    if running:
        return "运行中"
    if manual:
        return "等待人工"
    if queued:
        return "排队中"
    if path_exists:
        return "本地已创建"
    return "未创建"


def _profile_status_kind(path_exists: bool, running: int, queued: int, manual: int) -> str:
    if running:
        return "running"
    if manual:
        return "manual"
    if queued:
        return "queued"
    if path_exists:
        return "ready"
    return "empty"
