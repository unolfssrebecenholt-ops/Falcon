import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from .db import FalconRepository
from .models import (
    CollectedComment,
    CollectedPost,
    CollectionEvent,
    CollectionRun,
    Evidence,
    MediaAsset,
    utc_now_iso,
)


COLLECTOR_STATUSES = {
    "queued",
    "running",
    "manual_action_required",
    "failed",
    "completed",
    "cancelled",
}
COLLECTOR_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
METRIC_NUMBER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*([万萬wW千kK]?)")
TERMINAL_EVENTS = {"run_failed", "manual_action_required", "run_completed"}
PROGRESS_EVENTS = {
    "records_collected",
    "record_collected",
    "detail_collected",
    "detail_screenshot_captured",
    "detail_opening",
    "browser_launching",
    "profile_loaded",
    "run_started",
}
DEFAULT_COLLECTOR_PACE = {
    "detail_delay_range_seconds": [8, 18],
    "scroll_delay_range_seconds": [5, 12],
    "scroll_distance_viewport_range": [0.45, 0.85],
    "batch_rest_after_cards_range": [5, 11],
    "batch_rest_seconds_range": [6, 10],
    "comment_scroll_delay_range_seconds": [4, 9],
    "reply_expand_delay_range_seconds": [5, 8],
}
DEFAULT_COLLECTOR_ACCESS_POLICY = {
    "js_access": False,
    "direct_url_access": False,
    "network_api_access": False,
}
PROFILE_SAFETY_LOCK_REASONS = {
    "account_risk_warning",
    "platform_risk_circuit_breaker",
    "risk_control",
}


def safe_collector_identifier(value: str, field_name: str) -> str:
    candidate = str(value or "").strip()
    if not COLLECTOR_IDENTIFIER_PATTERN.fullmatch(candidate):
        raise ValueError(f"Invalid collector {field_name}: {value!r}")
    return candidate


def clean_metric_count(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace(",", "").strip()
    if not text:
        return ""
    match = METRIC_NUMBER_PATTERN.search(text)
    if not match:
        return ""
    number = float(match.group(1))
    suffix = match.group(2)
    multiplier = 1
    if suffix in {"万", "萬", "w", "W"}:
        multiplier = 10_000
    elif suffix in {"千", "k", "K"}:
        multiplier = 1_000
    return str(int(round(number * multiplier)))


def metric_value(metrics: Dict[str, object], *names: str) -> str:
    for name in names:
        if name in metrics:
            cleaned = clean_metric_count(metrics.get(name))
            if cleaned:
                return cleaned
    return ""


def _event_order_key(event: CollectionEvent) -> tuple[int, str, int]:
    return (event.event_id or 0, event.created_at or "", event.sequence)


def _latest_event(events: List[CollectionEvent], names: Optional[set[str]] = None) -> Optional[CollectionEvent]:
    candidates = [event for event in events if names is None or event.event in names]
    if not candidates:
        return None
    return max(candidates, key=_event_order_key)


@dataclass
class CollectorPaths:
    run_dir: Path
    request_path: Path
    events_path: Path
    records_path: Path
    assets_dir: Path
    profile_dir: Path


class CollectorService:
    def __init__(
        self,
        repo: FalconRepository,
        runtime_root: Path = Path("runtime") / "collector",
        profile_root: Path = Path("browser-profiles"),
        sidecar_script: Optional[Path] = None,
        node_executable: str = "node",
    ):
        self.repo = repo
        self.runtime_root = Path(runtime_root)
        self.profile_root = Path(profile_root)
        self.sidecar_script = Path(sidecar_script) if sidecar_script else self._project_root() / "sidecar" / "collector" / "index.mjs"
        self.node_executable = node_executable

    def run_dry_run(
        self,
        platform: str,
        profile: str,
        keyword: str,
        max_posts: int = 8,
        max_comments_per_post: int = 5,
        headed: bool = False,
        run_id: str = "",
    ) -> CollectionRun:
        return self.run_sidecar(
            platform=platform,
            profile=profile,
            keyword=keyword,
            max_posts=max_posts,
            max_comments_per_post=max_comments_per_post,
            headed=headed,
            dry_run=True,
            run_id=run_id,
        )

    def run_sidecar(
        self,
        platform: str,
        profile: str,
        keyword: str,
        max_posts: int = 8,
        max_comments_per_post: int = 5,
        headed: bool = True,
        dry_run: bool = False,
        run_id: str = "",
    ) -> CollectionRun:
        platform = safe_collector_identifier(platform, "platform")
        profile = safe_collector_identifier(profile, "profile")
        run_id = safe_collector_identifier(run_id, "run_id") if run_id else self._new_run_id(platform)
        run = CollectionRun(
            run_id=run_id,
            platform=platform,
            keyword=keyword,
            profile=profile,
            status="queued",
            max_posts=max_posts,
            max_comments_per_post=max_comments_per_post,
        )
        self.repo.create_collection_run(run)
        if not dry_run and self.is_profile_safety_locked(platform, profile):
            return self._pause_run_for_profile_safety(run)
        paths = self.prepare_run_request(run, headed=headed, dry_run=dry_run)
        self.repo.update_collection_run(run_id, status="running", progress=5, current_step="采集器已启动")

        result = subprocess.run(
            [
                self.node_executable,
                str(self.sidecar_script),
                "--request",
                str(paths.request_path),
                "--events",
                str(paths.events_path),
                "--output",
                str(paths.records_path),
                "--assets",
                str(paths.assets_dir),
                "--profile",
                str(paths.profile_dir),
            ],
            cwd=self._project_root(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.ingest_outputs(run_id, paths.events_path, paths.records_path)
        events = self.repo.list_collection_events(run_id)
        latest_terminal = _latest_event(events, TERMINAL_EVENTS)

        if latest_terminal and latest_terminal.event == "manual_action_required":
            self.repo.update_collection_run(
                run_id,
                status="manual_action_required",
                progress=50,
                current_step=latest_terminal.message,
            )
        elif result.returncode == 0 and (latest_terminal is None or latest_terminal.event == "run_completed"):
            self.repo.update_collection_run(
                run_id,
                status="completed",
                progress=100,
                current_step="采集器已完成",
                completed_at=utc_now_iso(),
            )
        else:
            reason = (
                latest_terminal.message
                if latest_terminal and latest_terminal.event == "run_failed"
                else (result.stderr.strip() or f"sidecar exited {result.returncode}")
            )
            self.repo.update_collection_run(
                run_id,
                status="failed",
                current_step="采集器失败",
                failed_reason=reason,
            )
        current = self.repo.get_collection_run(run_id)
        if current is None:
            raise RuntimeError(f"Collector run disappeared: {run_id}")
        return current

    def start_prepared_run(self, run_id: str, headed: bool = True, dry_run: bool = False) -> CollectionRun:
        run_id = safe_collector_identifier(run_id, "run_id")
        run = self.repo.get_collection_run(run_id)
        if run is None:
            raise ValueError(f"Unknown collector run: {run_id}")
        if run.status in {"completed", "cancelled"}:
            raise ValueError(f"Collector run cannot be started from status: {run.status}")
        if not dry_run and self.is_profile_safety_locked(run.platform, run.profile):
            return self._pause_run_for_profile_safety(run)

        paths = self.prepare_run_request(run, headed=headed, dry_run=dry_run)
        self.repo.update_collection_run(
            run_id,
            status="running",
            progress=max(run.progress, 5),
            current_step="采集器已启动",
        )

        result = subprocess.run(
            [
                self.node_executable,
                str(self.sidecar_script),
                "--request",
                str(paths.request_path),
                "--events",
                str(paths.events_path),
                "--output",
                str(paths.records_path),
                "--assets",
                str(paths.assets_dir),
                "--profile",
                str(paths.profile_dir),
            ],
            cwd=self._project_root(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.ingest_outputs(run_id, paths.events_path, paths.records_path)
        events = self.repo.list_collection_events(run_id)
        latest_terminal = _latest_event(events, TERMINAL_EVENTS)

        if latest_terminal and latest_terminal.event == "manual_action_required":
            self.repo.update_collection_run(
                run_id,
                status="manual_action_required",
                progress=50,
                current_step=latest_terminal.message,
            )
        elif result.returncode == 0 and (latest_terminal is None or latest_terminal.event == "run_completed"):
            self.repo.update_collection_run(
                run_id,
                status="completed",
                progress=100,
                current_step="采集器已完成",
                completed_at=utc_now_iso(),
            )
        else:
            reason = (
                latest_terminal.message
                if latest_terminal and latest_terminal.event == "run_failed"
                else (result.stderr.strip() or f"sidecar exited {result.returncode}")
            )
            self.repo.update_collection_run(
                run_id,
                status="failed",
                current_step="采集器失败",
                failed_reason=reason,
            )
        current = self.repo.get_collection_run(run_id)
        if current is None:
            raise RuntimeError(f"Collector run disappeared: {run_id}")
        return current

    def prepare_run_request(self, run: CollectionRun, headed: bool, dry_run: bool) -> CollectorPaths:
        paths = self.paths_for(run.run_id, run.platform, run.profile)
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        paths.assets_dir.mkdir(parents=True, exist_ok=True)
        request = {
            "schema_version": 1,
            "run_id": run.run_id,
            "platform": run.platform,
            "profile": run.profile,
            "keyword": run.keyword,
            "max_posts": run.max_posts,
            "max_comments_per_post": run.max_comments_per_post,
            "headed": headed,
            "dry_run": dry_run,
            "safety_profile": "respectful_human",
            "automation_boundary": "browser_control",
            "access_policy": DEFAULT_COLLECTOR_ACCESS_POLICY,
            "media_policy": "browser_loaded_image",
            "pace": DEFAULT_COLLECTOR_PACE,
            "checkpoint_enabled": True,
        }
        paths.request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        return paths

    def paths_for(self, run_id: str, platform: str, profile: str) -> CollectorPaths:
        run_id = safe_collector_identifier(run_id, "run_id")
        platform = safe_collector_identifier(platform, "platform")
        profile = safe_collector_identifier(profile, "profile")
        run_dir = self.runtime_root / run_id
        profile_dir = self.profile_root / platform / profile
        self._ensure_child_path(self.runtime_root, run_dir)
        self._ensure_child_path(self.profile_root, profile_dir)
        return CollectorPaths(
            run_dir=run_dir,
            request_path=run_dir / "request.json",
            events_path=run_dir / "events.jsonl",
            records_path=run_dir / "records.jsonl",
            assets_dir=run_dir / "assets",
            profile_dir=profile_dir,
        )

    def profile_safety_path(self, platform: str, profile: str) -> Path:
        platform = safe_collector_identifier(platform, "platform")
        profile = safe_collector_identifier(profile, "profile")
        safety_dir = self.runtime_root / "profile-safety" / platform
        safety_path = safety_dir / f"{profile}.json"
        self._ensure_child_path(self.runtime_root, safety_path)
        return safety_path

    def profile_safety_state(self, platform: str, profile: str) -> Dict[str, object]:
        path = self.profile_safety_path(platform, profile)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def is_profile_safety_locked(self, platform: str, profile: str) -> bool:
        return bool(self.profile_safety_state(platform, profile).get("locked"))

    def clear_profile_safety_lock(self, platform: str, profile: str) -> None:
        path = self.profile_safety_path(platform, profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "platform": platform,
            "profile": profile,
            "locked": False,
            "cleared_at": utc_now_iso(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def lock_profile_safety(
        self,
        platform: str,
        profile: str,
        *,
        reason: str,
        run_id: str,
        message: str,
    ) -> None:
        path = self.profile_safety_path(platform, profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "platform": platform,
            "profile": profile,
            "locked": True,
            "reason": reason,
            "run_id": run_id,
            "message": message,
            "locked_at": utc_now_iso(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _pause_run_for_profile_safety(self, run: CollectionRun) -> CollectionRun:
        state = self.profile_safety_state(run.platform, run.profile)
        raw_message = str(state.get("message") or "").strip()
        message = (
            f"账号风控熔断 / 需人工确认后再继续采集：{raw_message}"
            if raw_message
            else "账号风控熔断 / 需人工确认后再继续采集"
        )
        events = self.repo.list_collection_events(run.run_id)
        self.repo.append_collection_event(
            CollectionEvent(
                run_id=run.run_id,
                sequence=(events[-1].sequence if events else 0) + 1,
                scope="collector",
                event="manual_action_required",
                message=message,
                level="warning",
                payload_json=json.dumps(
                    {
                        "reason": "profile_safety_locked",
                        "platform": run.platform,
                        "profile": run.profile,
                        "safety_state": state,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        self.repo.update_collection_run(
            run.run_id,
            status="manual_action_required",
            progress=max(run.progress, 50),
            current_step=message,
        )
        current = self.repo.get_collection_run(run.run_id)
        if current is None:
            raise RuntimeError(f"Collector run disappeared: {run.run_id}")
        return current

    def ingest_outputs(self, run_id: str, events_path: Path, records_path: Path) -> None:
        for event in self._read_jsonl(events_path):
            payload = event.get("payload", {})
            self.repo.append_collection_event(
                CollectionEvent(
                    run_id=run_id,
                    sequence=int(event["sequence"]),
                    scope=str(event.get("scope", "")),
                    event=str(event.get("event", "")),
                    message=str(event.get("message", "")),
                    level=str(event.get("level", "info")),
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    created_at=str(event.get("time") or utc_now_iso()),
                )
            )

        if records_path.exists():
            self._ingest_records(run_id, self._read_jsonl(records_path))
        self._sync_run_status_from_events(run_id)
        self._lock_profile_from_risk_events(run_id)

    def _ingest_records(self, run_id: str, records: Iterable[Dict[str, object]]) -> None:
        post_ids: Dict[str, int] = {}
        pending_comments: List[Dict[str, object]] = []
        pending_assets: List[Dict[str, object]] = []

        for record in records:
            record_type = record.get("type")
            if record_type == "post":
                external_id = str(record.get("post_id") or record.get("id") or "")
                metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
                author = record.get("author") if isinstance(record.get("author"), dict) else {}
                post_id = self.repo.save_collected_post(
                    CollectedPost(
                        run_id=run_id,
                        platform=str(record.get("platform", "")),
                        keyword=str(record.get("keyword", "")),
                        title=str(record.get("title", "")),
                        content=str(record.get("content") or record.get("body") or ""),
                        url=str(record.get("url") or f"local://collector/{run_id}/{external_id}"),
                        author=str(author.get("display_name", "")),
                        published_at=str(record.get("published_at", "")),
                        like_count=metric_value(metrics, "likes", "like_count", "likes_text", "like_text")
                        or clean_metric_count(record.get("like_count") or record.get("likes")),
                        collect_count=metric_value(
                            metrics,
                            "collects",
                            "collect_count",
                            "collects_text",
                            "collect_text",
                            "favorites",
                            "favorite_count",
                            "favorite_text",
                            "stars",
                            "saves",
                            "save_count",
                        )
                        or clean_metric_count(
                            record.get("collect_count")
                            or record.get("collects")
                            or record.get("favorite_count")
                            or record.get("favorites")
                        ),
                        comment_count=metric_value(metrics, "comments", "comment_count", "comments_text", "comment_text")
                        or clean_metric_count(record.get("comment_count") or record.get("comments")),
                        detail_fingerprint=str(record.get("detail_fingerprint") or external_id),
                    )
                )
                if external_id:
                    post_ids[external_id] = post_id
            elif record_type == "comment":
                pending_comments.append(record)
            elif record_type == "media_asset":
                pending_assets.append(record)
            elif record_type == "evidence":
                self.repo.save_evidence(
                    Evidence(
                        run_id=run_id,
                        evidence_type=str(record.get("evidence_type") or record.get("scope") or "field_snapshot"),
                        path=str(record.get("path") or f"runtime/collector/{run_id}/records.jsonl"),
                        scope=str(record.get("scope", "")),
                        payload_json=json.dumps(record.get("payload", {}), ensure_ascii=False),
                    )
                )

        for record in pending_comments:
            external_post_id = str(record.get("post_id") or "")
            post_id = post_ids.get(external_post_id)
            if post_id is None:
                continue
            author = record.get("author") if isinstance(record.get("author"), dict) else {}
            metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
            self.repo.save_collected_comment(
                CollectedComment(
                    post_id=post_id,
                    run_id=run_id,
                    commenter=str(author.get("display_name", "")),
                    content=str(record.get("content") or record.get("body") or ""),
                    like_count=clean_metric_count(record.get("like_count") or record.get("likes"))
                    or metric_value(metrics, "likes", "like_count", "likes_text", "like_text"),
                    comment_rank=clean_metric_count(record.get("comment_rank")) or str(record.get("comment_rank", "")),
                    comment_type=str(record.get("comment_type") or "comment"),
                    reply_to=str(record.get("reply_to") or ""),
                )
            )

        for record in pending_assets:
            external_post_id = str(record.get("post_id") or "")
            self.repo.save_media_asset(
                MediaAsset(
                    run_id=run_id,
                    post_id=post_ids.get(external_post_id),
                    path=str(record.get("path", "")),
                    asset_type=str(record.get("media_type") or record.get("asset_type") or "asset"),
                    url=str(record.get("url", "")),
                    sha256=str(record.get("sha256", "")),
                )
            )

    def _read_jsonl(self, path: Path) -> List[Dict[str, object]]:
        if not path.exists():
            return []
        lines = []
        for raw_line in path.read_text(encoding="utf-8").split("\n"):
            line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
            if line.strip():
                lines.append(json.loads(line))
        return lines

    def _sync_run_status_from_events(self, run_id: str) -> None:
        run = self.repo.get_collection_run(run_id)
        if run is None:
            return
        events = self.repo.list_collection_events(run_id)
        if not events:
            return

        latest_event = _latest_event(events)
        latest_progress_event = _latest_event(events, PROGRESS_EVENTS)

        if latest_event and latest_event.event == "run_failed":
            progress = run.progress
            if latest_progress_event:
                progress = max(progress, _progress_for_event(latest_progress_event, run))
            self.repo.update_collection_run(
                run_id,
                status="failed",
                progress=progress,
                current_step=latest_event.message,
                failed_reason=latest_event.message,
            )
        elif latest_event and latest_event.event == "manual_action_required":
            progress = run.progress
            if latest_progress_event:
                progress = max(progress, _progress_for_event(latest_progress_event, run))
            self.repo.update_collection_run(
                run_id,
                status="manual_action_required",
                progress=max(progress, 50),
                current_step=latest_event.message,
            )
        elif latest_event and latest_event.event == "run_completed":
            self.repo.update_collection_run(
                run_id,
                status="completed",
                progress=100,
                current_step="采集器已完成",
                completed_at=run.completed_at or utc_now_iso(),
            )
        elif latest_progress_event:
            self.repo.update_collection_run(
                run_id,
                status="running",
                progress=max(run.progress, _progress_for_event(latest_progress_event, run)),
                current_step=latest_progress_event.message or "采集器已启动",
            )

    def _lock_profile_from_risk_events(self, run_id: str) -> None:
        run = self.repo.get_collection_run(run_id)
        if run is None:
            return
        events = self.repo.list_collection_events(run_id)
        for event in reversed(events):
            if event.event != "manual_action_required":
                continue
            payload = _payload_for_event(event)
            reason = str(payload.get("reason") or "")
            if reason not in PROFILE_SAFETY_LOCK_REASONS:
                return
            self.lock_profile_safety(
                run.platform,
                run.profile,
                reason=reason,
                run_id=run_id,
                message=event.message,
            )
            return

    def _new_run_id(self, platform: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{platform}-{stamp}-{uuid4().hex[:6]}"

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def _ensure_child_path(self, root: Path, child: Path) -> None:
        root_resolved = Path(root).resolve()
        child_resolved = Path(child).resolve()
        if child_resolved != root_resolved and root_resolved not in child_resolved.parents:
            raise ValueError(f"Collector path escapes root: {child}")


def _progress_for_event(event: object, run: Optional[CollectionRun] = None) -> int:
    event_name = getattr(event, "event", str(event))
    payload = _payload_for_event(event)
    if event_name in {"detail_opening", "detail_collected"}:
        post_progress = _post_progress_for_payload(
            payload,
            fallback_total=run.max_posts if run else 0,
            collected=event_name == "detail_collected",
        )
        if post_progress is not None:
            return post_progress
    return {
        "run_started": 5,
        "profile_loaded": 10,
        "browser_launching": 15,
        "detail_opening": 35,
        "detail_collected": 65,
        "detail_screenshot_captured": 55,
        "record_collected": 65,
        "records_collected": 95,
    }.get(event_name, 5)


def _payload_for_event(event: object) -> Dict[str, object]:
    payload_json = getattr(event, "payload_json", "")
    if not payload_json:
        return {}
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _post_progress_for_payload(
    payload: Dict[str, object],
    fallback_total: int = 0,
    collected: bool = False,
) -> Optional[int]:
    try:
        post_index = int(payload.get("post_index") or 0)
    except (TypeError, ValueError):
        post_index = 0
    try:
        post_total = int(payload.get("post_total") or fallback_total or 0)
    except (TypeError, ValueError):
        post_total = 0
    if post_index <= 0 or post_total <= 0:
        return None
    post_index = min(post_index, post_total)
    completed_posts = post_index if collected else max(0, post_index - 1)
    progress = 15 + round((completed_posts / post_total) * 75)
    return max(15, min(90, progress))
