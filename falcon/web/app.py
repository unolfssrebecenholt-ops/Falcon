import json
import mimetypes
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from typing import List, Optional
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..collector import CollectorService, safe_collector_identifier
from ..config import load_gpt_config_view, save_gpt_config
from ..db import FalconRepository
from ..doctor import build_doctor_report, checks_for_web
from ..intent_analysis import IntentAnalysisService
from ..keyword_pool import load_keyword_tasks, write_default_keyword_pool
from ..models import CollectionEvent, CollectionRun, IntentAnalysisProbe, IntentAnalysisTask
from ..profiles import (
    SUPPORTED_PROFILE_LOGIN_PLATFORMS,
    clear_profile_directory,
    launch_profile_login,
    list_profile_entries,
)
from ..relevance import (
    LEVEL_LABELS,
    ROLE_LABELS,
    effective_relevance_level,
    effective_relevance_role,
    relevance_label,
    role_label,
)
from ..workflows import promote_collected_posts, score_collected_posts


WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

COLLECTOR_STATUS_LABELS = {
    "queued": "待启动",
    "running": "运行中",
    "manual_action_required": "需人工处理",
    "failed": "失败",
    "completed": "已完成",
    "cancelled": "已归档",
}
COLLECTOR_LEVEL_LABELS = {
    "info": "信息",
    "warning": "提醒",
    "error": "错误",
}
COLLECTOR_SCOPE_LABELS = {
    "collector": "采集器",
    "xiaohongshu": "小红书",
    "core": "核心调度",
    "search": "搜索页",
    "dry_run_fixture": "采集合同",
    "manual_action_required": "人工处理",
}
COLLECTOR_EVENT_LABELS = {
    "request_prepared": "请求已准备",
    "run_started": "任务启动",
    "profile_loaded": "账号环境已加载",
    "browser_launching": "浏览器启动",
    "detail_opening": "打开详情",
    "detail_collected": "单帖采集完成",
    "record_collected": "记录生成",
    "records_collected": "记录生成",
    "media_download_failed": "图片下载失败",
    "manual_action_required": "等待人工处理",
    "run_completed": "任务完成",
    "run_failed": "任务失败",
    "rerun_created": "已创建重跑",
    "run_marked_failed": "人工标记失败",
    "run_archived": "任务归档",
    "manual_action_window_opened": "已打开处理窗口",
    "manual_action_resumed": "继续采集",
    "queue_worker_dispatched": "队列启动",
}
COLLECTOR_MESSAGE_LABELS = {
    "Collector run started": "采集任务已启动",
    "Browser profile path resolved": "账号环境已加载",
    "Launching Xiaohongshu browser flow": "小红书浏览器采集已启动",
    "Collected Xiaohongshu visible search records": "已生成小红书采集记录",
    "Collector run completed": "采集任务已完成",
    "Sidecar request prepared; waiting for manual start.": "采集请求已准备，等待启动。",
    "sidecar started": "采集器已启动",
    "sidecar completed": "采集器已完成",
    "sidecar failed": "采集器失败",
    "queued for browser collector": "等待浏览器采集调度",
    "started": "采集任务已启动",
    "completed": "采集任务已完成",
}
PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "weibo": "微博",
    "xianyu": "闲鱼",
}
ASSET_TYPE_LABELS = {
    "image": "图片",
    "video": "视频",
    "screenshot": "截图",
    "asset": "素材",
}
EVIDENCE_SCOPE_LABELS = {
    "dry_run_fixture": "采集合同",
    "search_results_screenshot": "搜索页截图",
    "field_snapshot": "字段快照",
    "detail_screenshot": "详情页截图",
    "detail_error_screenshot": "详情异常截图",
    "screenshot": "截图",
    "manual_action_required": "人工处理",
    "manual_action_snapshot": "人工处理快照",
    "manual_action_screenshot": "人工处理截图",
    "failure_snapshot": "失败快照",
    "failure_screenshot": "失败截图",
    "search_not_confirmed": "搜索未确认",
}


def collector_status_label(value: str) -> str:
    return COLLECTOR_STATUS_LABELS.get(str(value or ""), str(value or "-"))


def collector_level_label(value: str) -> str:
    return COLLECTOR_LEVEL_LABELS.get(str(value or ""), str(value or "-"))


def collector_scope_label(value: str) -> str:
    return COLLECTOR_SCOPE_LABELS.get(str(value or ""), PLATFORM_LABELS.get(str(value or ""), str(value or "-")))


def collector_event_label(value: str) -> str:
    return COLLECTOR_EVENT_LABELS.get(str(value or ""), str(value or "-"))


def collector_message_label(value: str, event: str = "") -> str:
    text = str(value or "")
    if text in COLLECTOR_MESSAGE_LABELS:
        return COLLECTOR_MESSAGE_LABELS[text]
    if text.startswith("Detected ") and "Xiaohongshu" in text:
        return "小红书需要人工处理，请查看截图和任务步骤。"
    if text.startswith("Collected ") and "fixture" in text:
        return "已生成采集合同记录"
    if not text and event:
        return collector_event_label(event)
    return text or "-"


def collector_step_label(value: str) -> str:
    return COLLECTOR_MESSAGE_LABELS.get(str(value or ""), str(value or "等待调度"))


def platform_label(value: str) -> str:
    return PLATFORM_LABELS.get(str(value or ""), str(value or "-"))


def asset_type_label(value: str) -> str:
    return ASSET_TYPE_LABELS.get(str(value or ""), str(value or "-"))


def evidence_scope_label(value: str) -> str:
    return EVIDENCE_SCOPE_LABELS.get(str(value or ""), str(value or "-"))


def basename_label(value: str) -> str:
    return Path(value or "").name or "-"


templates.env.filters["collector_status"] = collector_status_label
templates.env.filters["collector_level"] = collector_level_label
templates.env.filters["collector_scope"] = collector_scope_label
templates.env.filters["collector_event"] = collector_event_label
templates.env.filters["collector_message"] = collector_message_label
templates.env.filters["collector_step"] = collector_step_label
templates.env.filters["platform_label"] = platform_label
templates.env.filters["asset_type"] = asset_type_label
templates.env.filters["evidence_scope"] = evidence_scope_label
templates.env.filters["basename"] = basename_label
templates.env.filters["relevance_label"] = relevance_label
templates.env.filters["relevance_role_label"] = role_label
SHANGHAI_TZ = timezone(timedelta(hours=8))


def readable_time(value: str) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "-"
    return parsed.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def readable_day(value: str) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return ""
    return parsed.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d")


def readable_clock(value: str) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "-"
    return parsed.astimezone(SHANGHAI_TZ).strftime("%H:%M:%S")


def run_duration_label(run: CollectionRun) -> str:
    start = _parse_time(run.created_at)
    if start is None:
        return "-"
    end = None
    if run.status == "running":
        end = datetime.now(timezone.utc)
    elif run.completed_at:
        end = _parse_time(run.completed_at)
    else:
        end = _parse_time(run.updated_at)
    if end is None:
        return "-"
    seconds = max(0, int((end - start).total_seconds()))
    return _duration_label(seconds)


def run_progress_stage(run: CollectionRun) -> str:
    if run.status == "manual_action_required":
        return "已暂停"
    if run.status == "failed":
        return "已停止"
    if run.status == "cancelled":
        return "已归档"
    if run.status == "queued":
        return "待启动"
    if run.status == "completed":
        return "100%"
    return f"{run.progress}%"


def run_resource_label(run: CollectionRun) -> str:
    if run.status == "running":
        return f"运行中，占用 {platform_label(run.platform)}/{run.profile}"
    if run.status == "queued":
        return "未启动，不占用资源"
    if run.status == "manual_action_required":
        return "等待人工处理，不占用采集器"
    if run.status == "failed":
        return "已失败，不占用资源"
    if run.status == "completed":
        return "已完成，不占用资源"
    if run.status == "cancelled":
        return "已归档，不占用资源"
    return "未占用"


def run_state_title(run: CollectionRun) -> str:
    titles = {
        "queued": "待启动：任务已创建，采集器尚未运行",
        "running": "运行中：浏览器采集正在执行",
        "manual_action_required": "需人工处理：请查看浏览器窗口",
        "failed": "失败：采集器已退出",
        "completed": "完成：采集结果已入库",
        "cancelled": "已归档：任务不再执行",
    }
    return titles.get(run.status, collector_status_label(run.status))


def run_state_detail(run: CollectionRun) -> str:
    details = {
        "queued": "未启动，不占用资源。点击“启动采集”后会打开浏览器并占用对应 profile。",
        "running": f"运行中，占用 {platform_label(run.platform)}/{run.profile}，请保持浏览器窗口可用。",
        "manual_action_required": "请打开同一账号 Profile 处理扫码、登录或验证；处理完成后点击“继续采集”复用当前 run。",
        "failed": "已失败，不占用资源。可重新运行生成新任务。",
        "completed": "已完成，不占用资源。可以查看采集样本和证据链。",
        "cancelled": "已归档，不占用资源。",
    }
    return details.get(run.status, run.current_step or "-")


def run_can_start(run: CollectionRun) -> bool:
    return run.status == "queued"


def latest_manual_action_reason(events: list[CollectionEvent]) -> str:
    payload = latest_manual_action_payload(events)
    return str(payload.get("reason") or "")


def latest_manual_action_payload(events: list[CollectionEvent]) -> dict:
    for event in reversed(events):
        if event.event != "manual_action_required":
            continue
        try:
            payload = json.loads(event.payload_json or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _event_payload(event: CollectionEvent) -> dict:
    try:
        payload = json.loads(event.payload_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_int(payload: dict, key: str) -> Optional[int]:
    try:
        value = int(payload.get(key))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def waterfall_recovery_report(events: list[CollectionEvent]) -> dict:
    skipped_cards = 0
    threshold_triggers = 0
    recovery_threshold = 5
    skipped_events = 0
    threshold_events = 0
    for event in events:
        payload = _event_payload(event)
        threshold_value = _payload_int(payload, "recovery_threshold")
        if threshold_value:
            recovery_threshold = threshold_value
        if event.event == "waterfall_target_skipped":
            skipped_events += 1
            skipped_cards = max(skipped_cards, skipped_events, _payload_int(payload, "skipped_cards") or 0)
        if event.event == "waterfall_missing_threshold_recovery":
            threshold_events += 1
            threshold_triggers = max(
                threshold_triggers,
                threshold_events,
                _payload_int(payload, "threshold_triggers") or 0,
            )
            skipped_cards = max(skipped_cards, _payload_int(payload, "skipped_cards") or 0)
    return {
        "skipped_cards": skipped_cards,
        "threshold_triggers": threshold_triggers,
        "recovery_threshold": recovery_threshold,
    }


def collector_search_context_url(run: CollectionRun) -> str:
    if run.platform == "xiaohongshu" and run.keyword:
        query = urlencode({"keyword": run.keyword, "source": "web_search_result_notes"})
        return f"https://www.xiaohongshu.com/search_result?{query}"
    return SUPPORTED_PROFILE_LOGIN_PLATFORMS.get(run.platform, "")


def reopenable_manual_action_url(candidate: str, run: CollectionRun) -> str:
    if not candidate:
        return ""
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    if run.platform == "xiaohongshu":
        host = parsed.netloc.lower()
        if host not in {"xiaohongshu.com", "www.xiaohongshu.com"}:
            return ""
        path = parsed.path.rstrip("/")
        if re.fullmatch(r"/(?:explore|search_result)/[A-Za-z0-9_-]{6,}", path or ""):
            return ""
        if run.keyword and path in {"", "/", "/explore"}:
            return ""
    return candidate


def manual_action_payload_url_candidates(payload: dict) -> list[str]:
    candidates = [str(payload.get("manual_action_url") or "")]
    matched_signals = payload.get("matched_signals")
    target_signal_candidates = []
    search_signal_candidates = []
    if isinstance(matched_signals, list):
        for signal in matched_signals:
            if not isinstance(signal, dict):
                continue
            target_signal_candidates.append(str(signal.get("target_url") or ""))
            search_signal_candidates.append(str(signal.get("search_url") or ""))
    candidates.extend([str(payload.get("search_url") or ""), str(payload.get("url") or "")])
    candidates.extend(search_signal_candidates)
    candidates.extend(target_signal_candidates)
    return [candidate for candidate in candidates if candidate]


def _parse_time(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _duration_label(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if minutes:
        parts.append(f"{minutes} 分")
    if seconds or not parts:
        parts.append(f"{seconds} 秒")
    return " ".join(parts)


templates.env.filters["readable_time"] = readable_time
templates.env.filters["readable_day"] = readable_day
templates.env.filters["readable_clock"] = readable_clock
templates.env.filters["run_duration"] = run_duration_label
templates.env.filters["run_progress_stage"] = run_progress_stage
templates.env.filters["run_resource"] = run_resource_label
templates.env.filters["run_state_title"] = run_state_title
templates.env.filters["run_state_detail"] = run_state_detail
templates.env.filters["run_can_start"] = run_can_start


def create_app(
    db_path: Path,
    doctor_report_builder=None,
    profile_root=None,
    profile_login_launcher=None,
    collector_run_launcher=None,
    intent_analysis_service_factory=None,
) -> FastAPI:
    app = FastAPI(title="Falcon 控制台")
    app.state.db_path = Path(db_path)
    app.state.last_run = None
    app.state.runtime_root = Path(db_path).parent / "runtime" / "collector"
    app.state.profile_root = Path(profile_root) if profile_root is not None else Path("browser-profiles")
    app.state.project_root = Path(__file__).resolve().parents[2]
    app.state.env_path = app.state.project_root / ".env"
    app.state.doctor_report_builder = doctor_report_builder or build_doctor_report
    app.state.profile_login_launcher = profile_login_launcher or launch_profile_login
    app.state.intent_analysis_service_factory = intent_analysis_service_factory

    def default_collector_run_launcher(run_id: str) -> None:
        repository = FalconRepository(app.state.db_path)
        repository.init_schema()
        service = CollectorService(
            repository,
            runtime_root=app.state.runtime_root,
            profile_root=app.state.profile_root,
        )
        finished_run = service.start_prepared_run(run_id, headed=True, dry_run=False)
        if finished_run.status == "completed":
            dispatch_queued_runs(repository, only_profile=(finished_run.platform, finished_run.profile))

    app.state.collector_run_launcher = collector_run_launcher or default_collector_run_launcher
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def repo() -> FalconRepository:
        repository = FalconRepository(app.state.db_path)
        repository.init_schema()
        return repository

    def collector_service(repository: FalconRepository) -> CollectorService:
        return CollectorService(
            repository,
            runtime_root=app.state.runtime_root,
            profile_root=app.state.profile_root,
        )

    def intent_analysis_service(repository: FalconRepository):
        if app.state.intent_analysis_service_factory is not None:
            return app.state.intent_analysis_service_factory(repository)
        return IntentAnalysisService(repository)

    def profile_safety_states(repository: FalconRepository) -> dict[tuple[str, str], dict]:
        service = collector_service(repository)
        states: dict[tuple[str, str], dict] = {}
        safety_root = app.state.runtime_root / "profile-safety"
        if safety_root.exists():
            for path in safety_root.glob("*/*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                platform = str(payload.get("platform") or path.parent.name)
                profile = str(payload.get("profile") or path.stem)
                try:
                    safe_collector_identifier(platform, "platform")
                    safe_collector_identifier(profile, "profile")
                except ValueError:
                    continue
                states[(platform, profile)] = payload
        for run in repository.list_collection_runs(limit=1000):
            state = service.profile_safety_state(run.platform, run.profile)
            if state:
                states[(run.platform, run.profile)] = state
        return states

    def collector_create_context(repository: FalconRepository):
        profile_entries = [
            entry
            for entry in list_profile_entries(
                app.state.profile_root,
                repository.list_collection_runs(limit=1000),
                [item["key"] for item in _collector_platforms()],
                profile_safety_states(repository),
            )
            if entry.platform == "xiaohongshu" and entry.path_exists and not entry.safety_locked
        ]
        default_profile = next((entry.profile for entry in profile_entries if entry.profile == "default"), "")
        if not default_profile and profile_entries:
            default_profile = profile_entries[0].profile
        return {
            "profile_options": profile_entries,
            "defaults": {
                "platform": "xiaohongshu",
                "profile": default_profile,
                "max_posts": 8,
                "max_comments_per_post": 5,
            },
        }

    def refresh_running_run(repository: FalconRepository, run: CollectionRun) -> CollectionRun:
        if run.status != "running":
            return run
        service = collector_service(repository)
        paths = service.paths_for(run.run_id, run.platform, run.profile)
        if paths.events_path.exists() or paths.records_path.exists():
            service.ingest_outputs(run.run_id, paths.events_path, paths.records_path)
        return repository.get_collection_run(run.run_id) or run

    def append_run_event(
        repository: FalconRepository,
        run_id: str,
        event: str,
        message: str,
        level: str = "info",
        scope: str = "core",
    ) -> None:
        events = repository.list_collection_events(run_id)
        sequence = (events[-1].sequence if events else 0) + 1
        repository.append_collection_event(
            CollectionEvent(
                run_id=run_id,
                sequence=sequence,
                scope=scope,
                event=event,
                message=message,
                level=level,
            )
        )

    def busy_profile_keys(repository: FalconRepository, ignore_run_id: str = "") -> set[tuple[str, str]]:
        return {
            (item.platform, item.profile)
            for item in repository.list_collection_runs(limit=1000)
            if item.run_id != ignore_run_id and item.status in {"running", "manual_action_required"}
        }

    def profile_is_busy(repository: FalconRepository, run: CollectionRun) -> bool:
        return (run.platform, run.profile) in busy_profile_keys(repository, ignore_run_id=run.run_id)

    def profile_is_safety_locked(repository: FalconRepository, run: CollectionRun) -> bool:
        return collector_service(repository).is_profile_safety_locked(run.platform, run.profile)

    def safety_lock_accounts_url(platform: str, profile: str) -> str:
        return (
            "/collector/accounts?"
            f"profile_action=safety_locked&profile_platform={platform}&profile_name={profile}"
        )

    def safety_lock_run_url(run: CollectionRun) -> str:
        return f"/collector/runs/{run.run_id}?run_notice=safety_locked"

    def run_notice_title(action: str) -> str:
        if action == "safety_locked":
            return "采集启动已被账号保护拦截"
        if action == "start_stale_failed":
            return "采集任务已经失败"
        return ""

    def run_notice_message(action: str, run: CollectionRun) -> str:
        if action == "safety_locked":
            return (
                f"账号风控熔断锁正在保护 {run.platform}/{run.profile}，Falcon 已停止启动采集。"
                "请先在账号管理确认账号状态，必要时打开登录窗口处理平台提示，再手动解除熔断。"
            )
        if action == "start_stale_failed":
            return (
                "这个任务在页面提交启动前已经由队列 worker 启动过，并且采集器已返回失败。"
                "请查看下方失败原因；需要继续采集时，请使用“重新运行”创建新的任务。"
            )
        return ""

    def dispatch_queued_runs(
        repository: FalconRepository,
        background_tasks: Optional[BackgroundTasks] = None,
        only_profile: Optional[tuple[str, str]] = None,
    ) -> list[str]:
        service = collector_service(repository)
        runs = repository.list_collection_runs(limit=1000)
        busy = busy_profile_keys(repository)
        dispatched: list[str] = []
        queued = sorted(
            (item for item in runs if item.status == "queued"),
            key=lambda item: (item.created_at, item.run_id),
        )
        for run in queued:
            profile_key = (run.platform, run.profile)
            if only_profile is not None and profile_key != only_profile:
                continue
            if profile_key in busy:
                continue
            if service.is_profile_safety_locked(run.platform, run.profile):
                continue
            service.prepare_run_request(run, headed=True, dry_run=False)
            repository.update_collection_run(
                run.run_id,
                status="running",
                progress=max(run.progress, 5),
                current_step="队列 worker 已启动采集器",
            )
            append_run_event(
                repository,
                run.run_id,
                event="queue_worker_dispatched",
                message=f"队列 worker 已确认 {run.platform}/{run.profile} 空闲，启动采集器。",
            )
            busy.add(profile_key)
            dispatched.append(run.run_id)
            if background_tasks is None:
                app.state.collector_run_launcher(run.run_id)
                break
            background_tasks.add_task(app.state.collector_run_launcher, run.run_id)
        return dispatched

    def manual_action_target_url(repository: FalconRepository, run: CollectionRun) -> str:
        payload = latest_manual_action_payload(repository.list_collection_events(run.run_id))
        for candidate in manual_action_payload_url_candidates(payload):
            target_url = reopenable_manual_action_url(candidate, run)
            if target_url:
                return target_url
        return collector_search_context_url(run)

    def local_asset_path(stored_path: str) -> Optional[Path]:
        if not stored_path:
            return None
        allowed_roots = {
            app.state.runtime_root.resolve(),
            (app.state.db_path.parent / "runtime" / "collector").resolve(),
            (app.state.project_root / "runtime" / "collector").resolve(),
        }
        raw_path = Path(stored_path)
        candidates = []
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.extend(
                [
                    app.state.db_path.parent / raw_path,
                    app.state.runtime_root / raw_path,
                    app.state.project_root / raw_path,
                ]
            )
        allowed_candidate = None
        for candidate in candidates:
            resolved = candidate.resolve()
            if any(resolved == root or root in resolved.parents for root in allowed_roots):
                if resolved.exists():
                    return resolved
                if allowed_candidate is None:
                    allowed_candidate = resolved
        return allowed_candidate

    def local_media_response(stored_path: str):
        path = local_asset_path(stored_path)
        if path is None:
            raise HTTPException(status_code=404, detail="Asset path is not allowed")
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Asset file not found")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    def media_item_from_asset(asset):
        path = local_asset_path(asset.path)
        exists = bool(path and path.exists() and path.is_file())
        mime_type = mimetypes.guess_type(asset.path)[0] or ""
        asset_type = str(asset.asset_type or "asset").lower()
        is_video = mime_type.startswith("video/") or (asset_type == "video" and not mime_type)
        is_image = mime_type.startswith("image/") or (asset_type == "image" and not mime_type)
        status = "缺失/未下载"
        if exists:
            status = "可播放" if is_video else "可下载" if is_image else "已下载"
        size_label = f"{path.stat().st_size} bytes" if exists and path else "-"
        return {
            "id": asset.asset_id,
            "kind": "video" if is_video else "image" if is_image else "asset",
            "type_label": asset_type_label(asset.asset_type),
            "path": asset.path,
            "url": asset.url,
            "sha256": asset.sha256 or "-",
            "mime_type": mime_type or "-",
            "size_label": size_label,
            "exists": exists,
            "status": status,
            "src": f"/collector/runs/{asset.run_id}/assets/{asset.asset_id}" if exists else "",
        }

    def media_item_from_evidence(evidence):
        path = local_asset_path(evidence.path)
        exists = bool(path and path.exists() and path.is_file())
        mime_type = mimetypes.guess_type(evidence.path)[0] or "image/png"
        return {
            "id": evidence.evidence_id,
            "kind": "image",
            "type_label": evidence_scope_label(evidence.evidence_type),
            "path": evidence.path,
            "url": "",
            "sha256": "-",
            "mime_type": mime_type,
            "size_label": f"{path.stat().st_size} bytes" if exists and path else "-",
            "exists": exists,
            "status": "详情页截图" if exists else "缺失/未下载",
            "src": f"/collector/runs/{evidence.run_id}/evidences/{evidence.evidence_id}" if exists else "",
            "is_evidence": True,
        }

    def run_evidence_previews(evidences):
        preferred_scopes = {
            "manual_action_screenshot",
            "detail_error_screenshot",
            "failure_screenshot",
            "search_results_screenshot",
        }
        previews = []
        for evidence in reversed(evidences):
            if evidence.evidence_type not in preferred_scopes and evidence.scope not in preferred_scopes:
                continue
            item = media_item_from_evidence(evidence)
            if not item["exists"] or not str(item["mime_type"]).startswith("image/"):
                continue
            previews.append(item)
            if len(previews) >= 3:
                break
        return previews

    def manual_action_context(repository: FalconRepository, run: CollectionRun, events, evidences):
        if run.status != "manual_action_required":
            return None
        payload = latest_manual_action_payload(events)
        return {
            "reason": str(payload.get("reason") or latest_manual_action_reason(events) or "-"),
            "target_url": manual_action_target_url(repository, run),
            "previews": run_evidence_previews(evidences),
        }

    def detail_screenshot_fallback(evidences, post):
        post_keys = {
            str(post.detail_fingerprint or ""),
            str(post.url or ""),
        }
        post_keys = {value for value in post_keys if value}
        for evidence in evidences:
            if evidence.evidence_type != "detail_screenshot" and evidence.scope != "detail_screenshot":
                continue
            try:
                payload = json.loads(evidence.payload_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            evidence_keys = {
                str(payload.get("post_id") or ""),
                str(payload.get("url") or ""),
            }
            evidence_keys = {value for value in evidence_keys if value}
            if not evidence_keys.intersection(post_keys):
                continue
            item = media_item_from_evidence(evidence)
            if item["exists"]:
                return item
        return None

    def detail_media_is_trusted(evidences, post) -> bool:
        post_keys = {
            str(post.detail_fingerprint or ""),
            str(post.url or ""),
        }
        post_keys = {value for value in post_keys if value}
        for evidence in evidences:
            if evidence.evidence_type != "field_snapshot" and evidence.scope != "field_snapshot":
                continue
            try:
                payload = json.loads(evidence.payload_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            if payload.get("media_scope") != "detail_container":
                continue
            evidence_keys = {
                str(payload.get("post_id") or ""),
                str(payload.get("url") or ""),
            }
            evidence_keys = {value for value in evidence_keys if value}
            if evidence_keys.intersection(post_keys):
                return True
        return False

    def canonical_media_url_key(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if text.startswith("data:image/"):
            return f"data:{hash(text)}"
        try:
            from urllib.parse import urlparse, unquote

            parsed = urlparse(text)
            path = unquote(parsed.path or "")
        except ValueError:
            return text
        filename = next((part for part in reversed(path.split("/")) if part), path)
        image_id = filename.split("!")[0]
        if image_id and len(image_id) >= 10:
            return f"image:{image_id}"
        return f"{parsed.netloc}{path.split('!')[0]}"

    def dedupe_preview_items(items):
        seen = set()
        deduped = []
        for item in items:
            if item.get("is_evidence"):
                key = f"evidence:{item['id']}"
            else:
                key = canonical_media_url_key(item.get("url", ""))
                if not key:
                    key = f"sha:{item.get('sha256')}" if item.get("sha256") not in {"", "-"} else f"src:{item.get('src')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def relevance_breakdown(post):
        labels = {
            "default_quality": "默认质量",
            "manual_override": "人工校准",
        }
        try:
            payload = json.loads(post.relevance_breakdown_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        return [
            {"key": key, "label": label, "value": int(payload.get(key) or 0)}
            for key, label in labels.items()
        ]

    def post_relevance_view(post):
        level = effective_relevance_level(post)
        role = effective_relevance_role(post)
        return {
            "score": post.relevance_score,
            "default_level": post.relevance_level or "unscored",
            "effective_level": level,
            "effective_label": relevance_label(level),
            "role": role,
            "role_label": role_label(role),
            "reason": post.relevance_reason or "等待评分",
            "breakdown": relevance_breakdown(post),
            "manual_level": post.manual_relevance_level,
            "manual_note": post.manual_relevance_note,
            "has_manual": bool(post.manual_relevance_level),
        }

    def relevance_summary(posts):
        counts = {level: 0 for level in LEVEL_LABELS}
        role_counts = {role: 0 for role in ROLE_LABELS}
        for post in posts:
            level = effective_relevance_level(post)
            role = effective_relevance_role(post)
            counts[level] = counts.get(level, 0) + 1
            role_counts[role] = role_counts.get(role, 0) + 1
        return {
            "counts": counts,
            "roles": role_counts,
            "promotable": role_counts.get("primary", 0) + role_counts.get("reference", 0),
        }

    def posts_with_relevance(posts):
        order = {"excellent": 0, "medium": 1, "poor": 2, "unscored": 3}
        enriched = [{"post": post, "relevance": post_relevance_view(post)} for post in posts]
        return sorted(
            enriched,
            key=lambda item: (
                order.get(item["relevance"]["effective_level"], 9),
                -(item["relevance"]["score"] or -1),
                item["post"].post_id or 0,
            ),
        )

    def all_collected_relevance(repository: FalconRepository):
        return relevance_summary(repository.list_collected_posts(limit=1000))

    def analysis_platform_context(repository: FalconRepository, platform: str, reuse_task_id: Optional[int] = None):
        allowed = {item["key"] for item in _collector_platforms()}
        selected = platform if platform in allowed else "xiaohongshu"
        runs = [
            run
            for run in repository.list_collection_runs(limit=1000)
            if run.platform == selected and run.status == "completed"
        ]
        tasks = repository.list_intent_analysis_tasks(platform=selected, limit=8)
        histories = []
        for task in tasks:
            history_task_id = task.task_id or 0
            sources = repository.list_intent_analysis_sources(history_task_id)
            probes = repository.list_intent_analysis_probes(history_task_id)
            package = repository.build_intent_analysis_package(history_task_id)
            histories.append(
                {
                    "task": task,
                    "sources": sources,
                    "probes": probes,
                    "enabled_probe_count": sum(1 for probe in probes if probe.enabled),
                    "post_count": len(package),
                    "comment_count": sum(len(item.get("comments", [])) for item in package),
                }
            )
        prefill_run_ids: list[str] = []
        prefill_user_intent = ""
        if reuse_task_id is not None:
            reuse_task = repository.get_intent_analysis_task(reuse_task_id)
            if reuse_task is not None and reuse_task.platform == selected:
                prefill_user_intent = reuse_task.user_intent
                prefill_run_ids = [
                    source.run_id
                    for source in repository.list_intent_analysis_sources(reuse_task_id)
                ]
        return {
            "selected_platform": selected,
            "platforms": _collector_platforms(),
            "analysis_runs": runs,
            "intent_tasks": tasks,
            "intent_histories": histories,
            "prefill_run_ids": prefill_run_ids,
            "prefill_user_intent": prefill_user_intent,
        }

    def intent_task_detail_context(repository: FalconRepository, task_id: int):
        task = repository.get_intent_analysis_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Intent analysis task not found")
        sources = repository.list_intent_analysis_sources(task_id)
        probes = repository.list_intent_analysis_probes(task_id)
        matches = repository.list_intent_analysis_matches(task_id)
        matches_by_post: dict[int, list] = {}
        for match in matches:
            matches_by_post.setdefault(match.post_id, []).append(match)
        result_posts = []
        for post in repository.build_intent_analysis_package(task_id):
            post_id = int(post["post_id"])
            post_matches = matches_by_post.get(post_id, [])
            comment_matches = [match for match in post_matches if match.level == "comment"]
            if post_matches:
                result_posts.append(
                    {
                        "post": post,
                        "post_matches": [match for match in post_matches if match.level == "post"],
                        "comment_matches": comment_matches,
                    }
                )
        return {
            "task": task,
            "sources": sources,
            "probes": probes,
            "result_posts": result_posts,
            "package": repository.build_intent_analysis_package(task_id),
        }

    def save_intent_analysis_probes_from_form(repository: FalconRepository, task_id: int, form) -> None:
        def parse_sort_order(value: object, fallback: int) -> int:
            try:
                return int(str(value or "").strip() or fallback)
            except ValueError:
                return fallback

        seen_ids = set()
        delete_ids = {int(str(item)) for item in form.getlist("delete_probe_ids") if str(item).isdigit()}
        for raw_probe_id in form.getlist("probe_ids"):
            probe_id_text = str(raw_probe_id or "").strip()
            if not probe_id_text:
                continue
            probe_id = int(probe_id_text)
            if probe_id in delete_ids:
                repository.delete_intent_analysis_probe(probe_id, task_id=task_id)
                continue
            existing = repository.get_intent_analysis_probe(probe_id)
            if existing is None or existing.task_id != task_id:
                continue
            seen_ids.add(probe_id)
            repository.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    probe_id=probe_id,
                    task_id=task_id,
                    probe_key=str(form.get(f"probe_key_{probe_id}") or f"probe-{probe_id}").strip(),
                    title=str(form.get(f"title_{probe_id}") or "").strip(),
                    description=str(form.get(f"description_{probe_id}") or "").strip(),
                    positive_signals=str(form.get(f"positive_signals_{probe_id}") or "").strip(),
                    negative_signals=str(form.get(f"negative_signals_{probe_id}") or "").strip(),
                    sort_order=parse_sort_order(form.get(f"sort_order_{probe_id}"), existing.sort_order),
                    enabled=form.get(f"enabled_{probe_id}") == "on",
                )
            )
        new_titles = [str(item).strip() for item in form.getlist("new_title") if str(item).strip()]
        for index, title in enumerate(new_titles, start=1):
            sort_order = len(seen_ids) + index
            repository.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key=f"probe-new-{uuid4().hex[:6]}",
                    title=title,
                    description=str(form.get("new_description") or "").strip(),
                    positive_signals=str(form.get("new_positive_signals") or "").strip(),
                    negative_signals=str(form.get("new_negative_signals") or "").strip(),
                    sort_order=sort_order,
                )
            )
        repository.update_intent_analysis_task(task_id, status="probes_ready", failed_reason="")

    def sse_payload(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @app.get("/")
    def dashboard(request: Request):
        repository = repo()
        raw_items = repository.list_raw_items()
        scored_items = repository.list_scored_items(limit=1000)
        high_intent = [item for item in scored_items if int(item["intent_score"]) >= 80]
        pending_tasks = repository.list_outreach_tasks(status="pending", limit=1000)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "active": "dashboard",
                "stats": {
                    "raw_count": len(raw_items),
                    "analyzed_count": len(scored_items),
                    "high_intent_count": len(high_intent),
                    "pending_task_count": len(pending_tasks),
                },
                "last_run": app.state.last_run,
            },
        )

    @app.post("/init-db")
    def init_db():
        repo()
        app.state.last_run = {"message": "数据库已初始化", "report_path": ""}
        return RedirectResponse("/", status_code=303)

    @app.get("/report")
    def report_page(request: Request, path: str = "reports/daily-report.md"):
        report_path = Path(path)
        content = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        return templates.TemplateResponse(
            request,
            "report.html",
            {
                "active": "report",
                "report_path": str(report_path),
                "content": content,
            },
        )

    @app.get("/keywords")
    def keywords_page(request: Request, path: str = "data/collection_keywords.csv"):
        keyword_path = Path(path)
        tasks = load_keyword_tasks(keyword_path) if keyword_path.exists() else []
        return templates.TemplateResponse(
            request,
            "keywords.html",
            {"active": "keywords", "keyword_path": str(keyword_path), "tasks": tasks},
        )

    @app.post("/keywords/default")
    def write_keywords(path: str = Form("data/collection_keywords.csv"), theme: str = Form("内容运营")):
        write_default_keyword_pool(Path(path), theme=theme)
        return RedirectResponse(f"/keywords?path={path}", status_code=303)

    @app.get("/settings/gpt")
    def gpt_settings_page(request: Request, status: str = ""):
        return templates.TemplateResponse(
            request,
            "gpt_settings.html",
            {
                "active": "settings_gpt",
                "gpt_config": load_gpt_config_view(app.state.env_path),
                "settings_notice": _settings_notice(status),
            },
        )

    @app.post("/settings/gpt")
    def save_gpt_settings(
        base_url: str = Form(""),
        api_key: str = Form(""),
    ):
        try:
            save_gpt_config(app.state.env_path, base_url=base_url, api_key=api_key)
        except ValueError as exc:
            return RedirectResponse(
                "/settings/gpt?" + urlencode({"status": f"error:{exc}"}),
                status_code=303,
            )
        return RedirectResponse("/settings/gpt?status=saved", status_code=303)

    @app.get("/collector")
    def collector_page(request: Request):
        repository = repo()
        runs = repository.list_collection_runs(limit=100)
        runs = [refresh_running_run(repository, run) for run in runs]
        dashboard = repository.collector_dashboard()
        posts = repository.list_collected_posts(limit=50)
        queued_runs = [run for run in runs if run.status in {"queued", "running", "manual_action_required"}]
        doctor_report = app.state.doctor_report_builder(app.state.project_root)
        calendar_state = _collector_calendar_state(runs)
        return templates.TemplateResponse(
            request,
            "collector.html",
            {
                "active": "collector",
                "stats": dashboard,
                "platforms": _platform_cards(runs, posts),
                "runs": runs,
                "queued_runs": queued_runs,
                "queue_health": _queue_health(dashboard, queued_runs),
                "calendar_state": calendar_state,
                "environment_ready": doctor_report.required_ok,
                **collector_create_context(repository),
            },
        )

    @app.get("/collector/runs")
    def collector_runs_page(request: Request):
        repository = repo()
        runs = repository.list_collection_runs(limit=100)
        runs = [refresh_running_run(repository, run) for run in runs]
        posts = repository.list_collected_posts(limit=50)
        default_status_filter = request.query_params.get("status", "all")
        if default_status_filter not in {"all", "queued", "manual_action_required", "failed"}:
            default_status_filter = "all"
        try:
            created_count = max(0, int(request.query_params.get("created", "0")))
        except ValueError:
            created_count = 0
        return templates.TemplateResponse(
            request,
            "collector_runs.html",
            {
                "active": "collector_runs",
                "platforms": _platform_cards(runs, posts),
                "runs": runs,
                "queued_count": sum(1 for run in runs if run.status == "queued"),
                "default_status_filter": default_status_filter,
                "created_count": created_count,
                "calendar_state": _collector_calendar_state(runs),
            },
        )

    @app.get("/collector/environment")
    def collector_environment_page(request: Request):
        doctor_report = app.state.doctor_report_builder(app.state.project_root)
        environment_checks = checks_for_web(doctor_report)
        return templates.TemplateResponse(
            request,
            "collector_environment.html",
            {
                "active": "collector_environment",
                "environment_checks": environment_checks,
                "environment_ready": doctor_report.required_ok,
                "environment_summary": _environment_summary(environment_checks),
            },
        )

    @app.get("/collector/accounts")
    def collector_accounts_page(
        request: Request,
        profile_action: str = "",
        profile_platform: str = "",
        profile_name: str = "",
    ):
        repository = repo()
        runs = repository.list_collection_runs(limit=1000)
        profile_entries = list_profile_entries(
            app.state.profile_root,
            runs,
            [item["key"] for item in _collector_platforms()],
            profile_safety_states(repository),
        )
        return templates.TemplateResponse(
            request,
            "collector_accounts.html",
            {
                "active": "collector_accounts",
                "page_view": "collector_accounts",
                "platforms": _collector_platforms(),
                "profile_entries": profile_entries,
                "profile_groups": _profile_groups(profile_entries),
                "profile_summary": _profile_command_summary(profile_entries),
                "profile_notice": _profile_notice(profile_action, profile_platform, profile_name),
                "profile_action": profile_action,
                "profile_platform": profile_platform,
                "profile_name": profile_name,
                "profile_login_supported_platforms": SUPPORTED_PROFILE_LOGIN_PLATFORMS,
            },
        )

    @app.get("/collector/accounts/redesign")
    def collector_accounts_redesign_page(
        request: Request,
        profile_action: str = "",
        profile_platform: str = "",
        profile_name: str = "",
    ):
        query = urlencode(
            {
                key: value
                for key, value in {
                    "profile_action": profile_action,
                    "profile_platform": profile_platform,
                    "profile_name": profile_name,
                }.items()
                if value
            }
        )
        redirect_url = f"/collector/accounts?{query}" if query else "/collector/accounts"
        return RedirectResponse(redirect_url, status_code=303)

    @app.post("/collector/profiles/open-login")
    def open_collector_profile_login(platform: str = Form(...), profile: str = Form(...)):
        clean_platform = platform.strip() or "xiaohongshu"
        clean_profile = profile.strip() or "default"
        allowed_platforms = {item["key"] for item in _collector_platforms()}
        if clean_platform not in allowed_platforms:
            raise HTTPException(status_code=400, detail="Unsupported collector platform")
        try:
            safe_collector_identifier(clean_platform, "platform")
            clean_profile = safe_collector_identifier(clean_profile, "profile")
        except ValueError as exc:
            query = urlencode(
                {
                    "profile_action": "invalid",
                    "profile_platform": clean_platform,
                    "profile_name": clean_profile,
                }
            )
            return RedirectResponse(f"/collector/accounts?{query}", status_code=303)
        if clean_platform not in SUPPORTED_PROFILE_LOGIN_PLATFORMS:
            raise HTTPException(status_code=400, detail="Profile login is not supported for this platform yet")

        profile_path = app.state.profile_root / clean_platform / clean_profile
        try:
            app.state.profile_login_launcher(
                platform=clean_platform,
                profile=clean_profile,
                profile_root=app.state.profile_root,
                profile_path=profile_path,
                project_root=app.state.project_root,
                url=SUPPORTED_PROFILE_LOGIN_PLATFORMS[clean_platform],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not open profile login window: {exc}") from exc
        return RedirectResponse(
            f"/collector/accounts?profile_action=opened&profile_platform={clean_platform}&profile_name={clean_profile}",
            status_code=303,
        )

    @app.post("/collector/profiles/logout")
    def logout_collector_profile(platform: str = Form(...), profile: str = Form(...)):
        clean_platform = platform.strip() or "xiaohongshu"
        clean_profile = profile.strip() or "default"
        allowed_platforms = {item["key"] for item in _collector_platforms()}
        if clean_platform not in allowed_platforms:
            raise HTTPException(status_code=400, detail="Unsupported collector platform")
        try:
            safe_collector_identifier(clean_platform, "platform")
            clean_profile = safe_collector_identifier(clean_profile, "profile")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        repository = repo()
        locked = any(
            run.platform == clean_platform
            and run.profile == clean_profile
            and run.status in {"running", "queued", "manual_action_required"}
            for run in repository.list_collection_runs(limit=1000)
        )
        if locked:
            raise HTTPException(status_code=400, detail="Collector profile has active or queued tasks")

        profile_path = app.state.profile_root / clean_platform / clean_profile
        try:
            clear_profile_directory(
                platform=clean_platform,
                profile=clean_profile,
                profile_root=app.state.profile_root,
                profile_path=profile_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not clear profile directory: {exc}") from exc
        return RedirectResponse(
            f"/collector/accounts?profile_action=logged_out&profile_platform={clean_platform}&profile_name={clean_profile}",
            status_code=303,
        )

    @app.post("/collector/profiles/clear-safety-lock")
    def clear_collector_profile_safety_lock(platform: str = Form(...), profile: str = Form(...)):
        clean_platform = platform.strip() or "xiaohongshu"
        clean_profile = profile.strip() or "default"
        try:
            clean_platform = safe_collector_identifier(clean_platform, "platform")
            clean_profile = safe_collector_identifier(clean_profile, "profile")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        repository = repo()
        collector_service(repository).clear_profile_safety_lock(clean_platform, clean_profile)
        return RedirectResponse(
            f"/collector/accounts?profile_action=safety_cleared&profile_platform={clean_platform}&profile_name={clean_profile}",
            status_code=303,
        )

    @app.get("/collector/create")
    def collector_create_page(request: Request):
        repository = repo()
        return templates.TemplateResponse(
            request,
            "collector_create.html",
            {
                "active": "collector_create",
                "platforms": _collector_platforms(),
                **collector_create_context(repository),
            },
        )

    @app.post("/collector/create")
    def create_collection_run(
        platform: str = Form(...),
        profile: str = Form(...),
        keyword: str = Form(""),
        keywords: str = Form(""),
        max_posts: int = Form(8),
        max_comments_per_post: int = Form(5),
    ):
        clean_platform = platform.strip() or "xiaohongshu"
        allowed_platforms = {item["key"] for item in _collector_platforms()}
        if clean_platform not in allowed_platforms:
            raise HTTPException(status_code=400, detail="Unsupported collector platform")
        try:
            safe_collector_identifier(clean_platform, "platform")
            clean_profile = safe_collector_identifier(profile.strip() or "default", "profile")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        repository = repo()
        if collector_service(repository).is_profile_safety_locked(clean_platform, clean_profile):
            return RedirectResponse(safety_lock_accounts_url(clean_platform, clean_profile), status_code=303)
        keyword_items = _split_keywords(keywords or keyword)
        if not keyword_items:
            raise HTTPException(status_code=400, detail="At least one collector keyword is required")

        created_runs = []
        service = collector_service(repository)
        for item in keyword_items:
            run = CollectionRun(
                run_id=_new_run_id(clean_platform),
                platform=clean_platform,
                keyword=item,
                profile=clean_profile,
                status="queued",
                progress=0,
                current_step="等待浏览器采集调度",
                max_posts=min(30, max(1, max_posts)),
                max_comments_per_post=min(50, max(0, max_comments_per_post)),
            )
            repository.create_collection_run(run)
            service.prepare_run_request(run, headed=True, dry_run=False)
            repository.append_collection_event(
                CollectionEvent(
                    run_id=run.run_id,
                    sequence=1,
                    scope="core",
                    event="request_prepared",
                    message="采集请求已准备，等待启动。",
                )
            )
            created_runs.append(run)
        return RedirectResponse(f"/collector/runs?status=queued&created={len(created_runs)}", status_code=303)

    @app.get("/collector/runs/{run_id}")
    def collector_run_detail(request: Request, run_id: str, run_notice: str = ""):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        run = refresh_running_run(repository, run)
        events = repository.list_collection_events(run_id)
        collected_posts = repository.list_collected_posts(run_id=run_id)
        assets = repository.list_media_assets(run_id)
        evidences = repository.list_evidences(run_id)
        return templates.TemplateResponse(
            request,
            "collector_run.html",
            {
                "active": "collector_run",
                "current_run": run,
                "run": run,
                "events": events,
                "manual_action_reason": latest_manual_action_reason(events),
                "run_notice_title": run_notice_title(run_notice),
                "run_notice": run_notice_message(run_notice, run),
                "run_notice_action_url": safety_lock_accounts_url(run.platform, run.profile)
                if run_notice == "safety_locked"
                else "",
                "posts": posts_with_relevance(collected_posts),
                "relevance_summary": relevance_summary(collected_posts),
                "waterfall_report": waterfall_recovery_report(events),
                "manual_action_context": manual_action_context(repository, run, events, evidences),
                "assets": assets,
                "evidences": evidences,
            },
        )

    @app.post("/collector/runs/{run_id}/relevance/score")
    def score_collection_run_relevance(run_id: str):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        score_collected_posts(repository, run_id=run_id)
        return RedirectResponse(f"/collector/runs/{run_id}", status_code=303)

    @app.post("/collector/runs/{run_id}/start")
    def start_collection_run(run_id: str, background_tasks: BackgroundTasks):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        if run.status == "running":
            return RedirectResponse(f"/collector/runs/{run_id}", status_code=303)
        if not run_can_start(run):
            if run.status == "failed":
                return RedirectResponse(f"/collector/runs/{run_id}?run_notice=start_stale_failed", status_code=303)
            raise HTTPException(status_code=400, detail=f"Collection run cannot start from status: {run.status}")
        if profile_is_busy(repository, run):
            raise HTTPException(status_code=400, detail="Collector profile is already busy")
        if profile_is_safety_locked(repository, run):
            return RedirectResponse(safety_lock_run_url(run), status_code=303)

        collector_service(repository).prepare_run_request(run, headed=True, dry_run=False)
        repository.update_collection_run(
            run_id,
            status="running",
            progress=max(run.progress, 5),
            current_step="采集器启动中",
        )
        append_run_event(
            repository,
            run_id,
            event="run_start_requested",
            message="已请求启动采集器，浏览器即将打开。",
        )
        background_tasks.add_task(app.state.collector_run_launcher, run_id)
        return RedirectResponse(f"/collector/runs/{run_id}", status_code=303)

    @app.post("/collector/queue/start")
    def start_collector_queue(background_tasks: BackgroundTasks):
        repository = repo()
        dispatch_queued_runs(repository, background_tasks=background_tasks)
        return RedirectResponse("/collector/runs", status_code=303)

    @app.post("/collector/runs/{run_id}/open-manual-action")
    def open_collection_run_manual_action(run_id: str):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        if run.status != "manual_action_required":
            raise HTTPException(status_code=400, detail="Collection run does not require manual action")
        if run.platform not in SUPPORTED_PROFILE_LOGIN_PLATFORMS:
            raise HTTPException(status_code=400, detail="Profile login is not supported for this platform yet")
        if latest_manual_action_reason(repository.list_collection_events(run_id)) == "profile_window_busy":
            raise HTTPException(
                status_code=400,
                detail="Please close the existing profile window before resuming collection.",
            )

        profile_path = app.state.profile_root / run.platform / run.profile
        target_url = manual_action_target_url(repository, run)
        try:
            app.state.profile_login_launcher(
                platform=run.platform,
                profile=run.profile,
                profile_root=app.state.profile_root,
                profile_path=profile_path,
                project_root=app.state.project_root,
                url=target_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not open manual action window: {exc}") from exc
        append_run_event(
            repository,
            run_id,
            event="manual_action_window_opened",
            message=f"已打开 {run.platform}/{run.profile} 的人工处理窗口。",
            level="warning",
        )
        return RedirectResponse(f"/collector/runs/{run_id}?manual_action=opened", status_code=303)

    @app.post("/collector/runs/{run_id}/resume")
    def resume_collection_run_after_manual_action(run_id: str, background_tasks: BackgroundTasks):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        if run.status != "manual_action_required":
            raise HTTPException(status_code=400, detail=f"Collection run cannot resume from status: {run.status}")
        if profile_is_busy(repository, run):
            raise HTTPException(status_code=400, detail="Collector profile is already busy")
        if profile_is_safety_locked(repository, run):
            return RedirectResponse(safety_lock_run_url(run), status_code=303)

        collector_service(repository).prepare_run_request(run, headed=True, dry_run=False)
        repository.update_collection_run(
            run_id,
            status="running",
            progress=max(run.progress, 55),
            current_step="人工处理已完成，继续采集器",
        )
        append_run_event(
            repository,
            run_id,
            event="manual_action_resumed",
            message="人工处理已完成，继续使用当前 run 启动采集器。",
        )
        background_tasks.add_task(app.state.collector_run_launcher, run_id)
        return RedirectResponse(f"/collector/runs/{run_id}", status_code=303)

    @app.post("/collector/runs/{run_id}/rerun")
    def rerun_collection_run(run_id: str):
        repository = repo()
        source = repository.get_collection_run(run_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        new_run = CollectionRun(
            run_id=_new_run_id(source.platform),
            platform=source.platform,
            keyword=source.keyword,
            profile=source.profile,
            status="queued",
            progress=0,
            current_step="等待浏览器采集调度",
            max_posts=source.max_posts,
            max_comments_per_post=source.max_comments_per_post,
        )
        repository.create_collection_run(new_run)
        collector_service(repository).prepare_run_request(new_run, headed=True, dry_run=False)
        append_run_event(
            repository,
            new_run.run_id,
            event="request_prepared",
            message=f"从 {source.run_id} 重新创建采集任务，等待启动。",
        )
        append_run_event(
            repository,
            source.run_id,
            event="rerun_created",
            message=f"已创建重跑任务 {new_run.run_id}。",
        )
        return RedirectResponse(f"/collector/runs/{new_run.run_id}", status_code=303)

    @app.post("/collector/runs/{run_id}/mark-failed")
    def mark_collection_run_failed(run_id: str):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        repository.update_collection_run(
            run_id,
            status="failed",
            progress=100,
            current_step="已人工标记失败",
            failed_reason="人工标记为失败",
        )
        append_run_event(
            repository,
            run_id,
            event="run_marked_failed",
            message="已人工标记失败，不占用采集资源。",
            level="warning",
        )
        return RedirectResponse(f"/collector/runs/{run_id}", status_code=303)

    @app.post("/collector/runs/{run_id}/archive")
    def archive_collection_run(
        request: Request,
        background_tasks: BackgroundTasks,
        run_id: str,
        return_to: str = Form(""),
    ):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        released_profile = (run.platform, run.profile) if run.status == "manual_action_required" else None
        repository.update_collection_run(
            run_id,
            status="cancelled",
            current_step="已归档",
        )
        append_run_event(
            repository,
            run_id,
            event="run_archived",
            message="任务已归档，不占用采集资源。",
        )
        if released_profile is not None:
            dispatch_queued_runs(repository, background_tasks=background_tasks, only_profile=released_profile)
        if "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with") == "fetch":
            updated_run = repository.get_collection_run(run_id)
            return JSONResponse(
                {
                    "run_id": run_id,
                    "status": updated_run.status if updated_run else "cancelled",
                    "status_label": collector_status_label("cancelled"),
                }
            )
        if return_to == "/collector":
            return RedirectResponse("/collector", status_code=303)
        return RedirectResponse(f"/collector/runs/{run_id}", status_code=303)

    @app.get("/collector/runs/{run_id}/posts/{post_id}")
    def collector_post_preview(request: Request, run_id: str, post_id: int):
        repository = repo()
        run = repository.get_collection_run(run_id)
        post = repository.get_collected_post(post_id)
        if run is None or post is None or post.run_id != run_id:
            raise HTTPException(status_code=404, detail="Collected post not found")
        assets = [
            asset
            for asset in repository.list_media_assets(run_id)
            if asset.post_id == post.post_id
        ]
        evidences = repository.list_evidences(run_id)
        asset_items = [media_item_from_asset(asset) for asset in assets]
        preview_items = [
            item
            for item in asset_items
            if item["exists"] and item["kind"] in {"image", "video"}
        ]
        preview_items = dedupe_preview_items(preview_items)
        detail_item = detail_screenshot_fallback(evidences, post)
        if detail_item and not detail_media_is_trusted(evidences, post):
            preview_items = []
        if detail_item:
            preview_items = [detail_item, *preview_items]
        return templates.TemplateResponse(
            request,
            "collector_post.html",
            {
                "active": "collector_run",
                "page_view": "collector_post",
                "page_width": "wide",
                "current_run": run,
                "run": run,
                "post": post,
                "comments": repository.list_collected_comments(run_id=run_id, post_id=post.post_id),
                "assets": assets,
                "asset_items": asset_items,
                "preview_items": preview_items,
                "primary_item": preview_items[0] if preview_items else None,
                "relevance": post_relevance_view(post),
            },
        )

    @app.post("/collector/runs/{run_id}/posts/{post_id}/relevance")
    def override_collection_post_relevance(
        run_id: str,
        post_id: int,
        manual_relevance_level: str = Form(...),
        manual_relevance_note: str = Form(""),
    ):
        repository = repo()
        post = repository.get_collected_post(post_id)
        if post is None or post.run_id != run_id:
            raise HTTPException(status_code=404, detail="Collected post not found")
        if manual_relevance_level not in {"excellent", "medium", "poor", ""}:
            raise HTTPException(status_code=400, detail="Invalid relevance level")
        repository.override_collected_post_relevance(post_id, manual_relevance_level, manual_relevance_note)
        return RedirectResponse(f"/collector/runs/{run_id}/posts/{post_id}", status_code=303)

    @app.get("/collector/runs/{run_id}/assets/{asset_id}")
    def collector_asset_file(run_id: str, asset_id: int):
        repository = repo()
        asset = next(
            (item for item in repository.list_media_assets(run_id) if item.asset_id == asset_id),
            None,
        )
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return local_media_response(asset.path)

    @app.get("/collector/runs/{run_id}/evidences/{evidence_id}")
    def collector_evidence_file(run_id: str, evidence_id: int):
        repository = repo()
        evidence = next(
            (item for item in repository.list_evidences(run_id) if item.evidence_id == evidence_id),
            None,
        )
        if evidence is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        return local_media_response(evidence.path)

    @app.get("/analysis")
    def analysis_page(request: Request, platform: str = "xiaohongshu", reuse_task_id: Optional[int] = None):
        repository = repo()
        scored_items = repository.list_scored_items(limit=100)
        keyword_stats = _keyword_stats(scored_items)
        high_intent = [item for item in scored_items if int(item.get("intent_score") or 0) >= 80]
        quality_pool = all_collected_relevance(repository)
        platform_context = analysis_platform_context(repository, platform, reuse_task_id=reuse_task_id)
        return templates.TemplateResponse(
            request,
            "analysis.html",
            {
                "active": "analysis",
                "items": scored_items,
                "keyword_stats": keyword_stats,
                "quality_pool": quality_pool,
                "last_run": app.state.last_run,
                **platform_context,
                "stats": {
                    "scored_count": len(scored_items),
                    "high_intent_count": len(high_intent),
                    "keyword_count": len(keyword_stats),
                    "promotable_count": quality_pool["promotable"],
                },
            },
        )

    @app.post("/analysis/tasks")
    async def create_intent_analysis_task(request: Request):
        form = await request.form()
        platform = str(form.get("platform") or "xiaohongshu").strip()
        allowed = {item["key"] for item in _collector_platforms()}
        if platform not in allowed:
            raise HTTPException(status_code=400, detail="Unsupported analysis platform")
        run_ids = [str(item).strip() for item in form.getlist("run_ids") if str(item).strip()]
        user_intent = str(form.get("user_intent") or "").strip()
        if not user_intent:
            raise HTTPException(status_code=400, detail="Analysis intent is required")
        repository = repo()
        task_id = repository.create_intent_analysis_task(
            IntentAnalysisTask(platform=platform, user_intent=user_intent)
        )
        try:
            repository.add_intent_analysis_sources(task_id, run_ids)
        except ValueError as exc:
            repository.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/analysis/tasks/{task_id}", status_code=303)

    @app.post("/analysis/tasks/{task_id}/delete")
    def delete_intent_analysis_task(task_id: int):
        repository = repo()
        task = repository.get_intent_analysis_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Intent analysis task not found")
        repository.delete_intent_analysis_task(task_id)
        return RedirectResponse(f"/analysis?platform={task.platform}", status_code=303)

    @app.get("/analysis/tasks/{task_id}")
    def intent_analysis_task_page(request: Request, task_id: int):
        repository = repo()
        return templates.TemplateResponse(
            request,
            "analysis_task.html",
            {
                "active": "analysis",
                **intent_task_detail_context(repository, task_id),
            },
        )

    @app.post("/analysis/tasks/{task_id}/probes/generate")
    def generate_intent_analysis_probes(task_id: int):
        repository = repo()
        try:
            intent_analysis_service(repository).generate_probes(task_id)
        except Exception as exc:
            repository.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
        return RedirectResponse(f"/analysis/tasks/{task_id}", status_code=303)

    @app.post("/analysis/tasks/{task_id}/probes/generate/stream")
    def stream_intent_analysis_probes(task_id: int):
        def events():
            repository = repo()
            try:
                task = repository.get_intent_analysis_task(task_id)
                if task is None:
                    yield sse_payload("error", {"message": "Intent analysis task not found"})
                    return
                service = intent_analysis_service(repository)
                yield sse_payload(
                    "status",
                    {
                        "message": "正在准备意向、平台和数据包上下文。",
                        "status": "preparing",
                    },
                )
                for item in service.generate_probes_stream(task_id):
                    event_type = str(item.get("type") or "status")
                    if event_type == "delta":
                        yield sse_payload("delta", {"text": str(item.get("text") or "")})
                    elif event_type == "done":
                        yield sse_payload(
                            "done",
                            {
                                "message": str(item.get("message") or "探针已生成。"),
                                "count": int(item.get("count") or 0),
                                "redirect_url": f"/analysis/tasks/{task_id}",
                            },
                        )
                    else:
                        yield sse_payload(
                            "status",
                            {
                                "message": str(item.get("message") or "正在处理。"),
                                "status": str(item.get("status") or ""),
                            },
                        )
            except Exception as exc:
                repository.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
                yield sse_payload("error", {"message": str(exc)})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/analysis/tasks/{task_id}/probes")
    async def save_intent_analysis_probes(request: Request, task_id: int):
        form = await request.form()
        repository = repo()
        save_intent_analysis_probes_from_form(repository, task_id, form)
        if form.get("next_action") == "execute":
            try:
                intent_analysis_service(repository).execute_task(task_id)
            except Exception as exc:
                repository.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
        return RedirectResponse(f"/analysis/tasks/{task_id}", status_code=303)

    @app.post("/analysis/tasks/{task_id}/execute")
    def execute_intent_analysis_task(task_id: int):
        repository = repo()
        try:
            intent_analysis_service(repository).execute_task(task_id)
        except Exception as exc:
            repository.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
        return RedirectResponse(f"/analysis/tasks/{task_id}", status_code=303)

    @app.get("/analysis/samples")
    def analysis_samples_page(request: Request):
        scored_items = repo().list_scored_items(limit=100)
        keyword_stats = _keyword_stats(scored_items)
        return templates.TemplateResponse(
            request,
            "analysis_samples.html",
            {
                "active": "analysis_samples",
                "items": scored_items,
                "keyword_stats": keyword_stats,
            },
        )

    @app.post("/analysis/promote")
    def promote_collector_samples():
        repository = repo()
        promoted = promote_collected_posts(repository, return_summary=True)
        app.state.last_run = {
            "message": (
                f"已送入分析队列 {promoted.promoted_count} 条采集样本："
                f"优质 {promoted.primary_count} 条，中等 {promoted.reference_count} 条，"
                f"劣质跳过 {promoted.discarded_count} 条，未评分 {promoted.unscored_count} 条。"
            ),
            "report_path": "",
        }
        return RedirectResponse("/analysis", status_code=303)

    @app.get("/execution")
    def execution_page(request: Request):
        tasks = repo().list_outreach_tasks(status="pending", limit=100)
        priority_counts = Counter(task.outreach_priority for task in tasks)
        return templates.TemplateResponse(
            request,
            "execution.html",
            {
                "active": "execution",
                "tasks": tasks,
                "stats": {
                    "pending_count": len(tasks),
                    "high_count": priority_counts.get("high", 0),
                    "medium_count": priority_counts.get("medium", 0),
                },
            },
        )

    @app.get("/review")
    def review_page(request: Request):
        return templates.TemplateResponse(
            request,
            "review.html",
            {"active": "review", "items": repo().list_scored_items(limit=20)},
        )

    @app.post("/review/raw/{raw_id}")
    def review_raw_item(raw_id: int, feedback: str = Form(...), note: str = Form("")):
        repo().add_feedback(feedback, note, raw_item_id=raw_id)
        return RedirectResponse("/review", status_code=303)

    @app.get("/tasks")
    def tasks_page(request: Request):
        return templates.TemplateResponse(
            request,
            "tasks.html",
            {"active": "tasks", "tasks": repo().list_outreach_tasks(status="pending", limit=100)},
        )

    @app.post("/tasks/{task_id}/status")
    def update_task_status(task_id: int, status: str = Form(...)):
        repo().update_task_status(task_id, status)
        return RedirectResponse("/tasks", status_code=303)

    return app


def _new_run_id(platform: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{platform}-{stamp}-{uuid4().hex[:6]}"


def _collector_platforms():
    return [
        {"key": "xiaohongshu", "name": "小红书", "status": "当前开发"},
        {"key": "douyin", "name": "抖音", "status": "待接入"},
        {"key": "weibo", "name": "微博", "status": "待接入"},
        {"key": "xianyu", "name": "闲鱼", "status": "待接入"},
    ]


def _platform_cards(runs, posts):
    run_counts = Counter(run.platform for run in runs)
    running_counts = Counter(run.platform for run in runs if run.status == "running")
    post_counts = Counter(post.platform for post in posts)
    latest = {}
    for run in runs:
        latest.setdefault(run.platform, run)
    cards = []
    for platform in _collector_platforms():
        key = platform["key"]
        cards.append(
            {
                **platform,
                "run_count": run_counts.get(key, 0),
                "running_count": running_counts.get(key, 0),
                "post_count": post_counts.get(key, 0),
                "latest": latest.get(key),
            }
        )
    return cards


def _profile_groups(entries):
    by_platform = {item["key"]: {**item, "entries": []} for item in _collector_platforms()}
    for entry in entries:
        platform = by_platform.get(entry.platform)
        if platform is None:
            continue
        platform["entries"].append(entry)
    return list(by_platform.values())


def _profile_command_summary(entries):
    entry_list = list(entries)
    return {
        "platform_count": len(_collector_platforms()),
        "profile_count": len(entry_list),
        "local_count": sum(1 for entry in entry_list if entry.path_exists),
        "busy_count": sum(1 for entry in entry_list if entry.running_runs),
        "manual_count": sum(1 for entry in entry_list if entry.manual_runs),
    }


def _queue_health(stats, queued_runs):
    manual_count = int(stats.get("waiting_manual_runs") or 0)
    failed_count = int(stats.get("failed_runs") or 0)
    queued_count = sum(1 for run in queued_runs if run.status == "queued")
    return {
        "manual_count": manual_count,
        "failed_count": failed_count,
        "queued_count": queued_count,
        "manual_label": f"{manual_count} 个等待人工" if manual_count else "无人工阻塞",
        "failed_label": f"{failed_count} 个失败 run 可复跑" if failed_count else "无失败 run",
        "queued_label": f"{queued_count} 个等待启动" if queued_count else "队列空闲",
    }


def _collector_calendar_state(runs):
    parsed_dates = [_parse_time(run.created_at) for run in runs]
    parsed_dates = [item.astimezone(SHANGHAI_TZ) for item in parsed_dates if item is not None]
    selected = max(parsed_dates) if parsed_dates else datetime.now(SHANGHAI_TZ)
    selected_day = selected.strftime("%Y-%m-%d")
    return {
        "selected_day": selected_day,
        "month_label": f"{selected.year} 年 {selected.month} 月",
        "days": _calendar_days_for_month(selected),
    }


def _calendar_days_for_month(selected: datetime):
    first = selected.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = first - timedelta(days=first.weekday())
    days = []
    for offset in range(42):
        current = start + timedelta(days=offset)
        days.append(
            {
                "date": current.strftime("%Y-%m-%d"),
                "day": current.day,
                "muted": current.month != selected.month,
            }
        )
    return days


def _split_keywords(value: str) -> list[str]:
    seen = set()
    keywords = []
    for item in re.split(r"[\n,，;；]+", value or ""):
        keyword = item.strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return keywords


def _profile_summary(runs):
    profile_counts = Counter((run.platform, run.profile, run.status) for run in runs)
    return [
        {
            "platform": platform,
            "profile": profile,
            "status": status,
            "count": count,
        }
        for (platform, profile, status), count in profile_counts.most_common()
    ]


def _keyword_stats(scored_items):
    grouped = {}
    for item in scored_items:
        keyword = item.get("keyword") or "未标记"
        stats = grouped.setdefault(keyword, {"keyword": keyword, "count": 0, "high_intent": 0, "total_intent": 0})
        intent_score = int(item.get("intent_score") or 0)
        stats["count"] += 1
        stats["total_intent"] += intent_score
        if intent_score >= 80:
            stats["high_intent"] += 1
    for stats in grouped.values():
        stats["avg_intent"] = round(stats["total_intent"] / stats["count"]) if stats["count"] else 0
    return sorted(grouped.values(), key=lambda value: (-value["high_intent"], -value["avg_intent"], value["keyword"]))


def _environment_summary(checks):
    total = len(checks)
    ok_count = sum(1 for check in checks if check["status"] == "ok")
    required_issues = sum(1 for check in checks if check["required"] and check["status"] != "ok")
    optional_warnings = sum(1 for check in checks if not check["required"] and check["status"] != "ok")
    return {
        "total": total,
        "ok_count": ok_count,
        "required_issues": required_issues,
        "optional_warnings": optional_warnings,
    }


def _profile_notice(action: str, platform: str, profile: str) -> str:
    if action == "invalid":
        return "Profile 名称只能使用英文字母、数字、点、下划线或短横线，并且必须以字母或数字开头。示例：default、creator-1、backup_2。"
    if action == "opened" and platform and profile:
        return f"已打开 {platform}/{profile} 登录窗口。请在弹出的浏览器里完成登录，完成后关闭窗口。"
    if action == "logged_out" and platform and profile:
        return f"已退出 {platform}/{profile}，本机 Profile 目录已清除。需要再次使用时请重新登录。"
    if action == "safety_cleared" and platform and profile:
        return f"已清除 {platform}/{profile} 的账号风控熔断锁。请确认账号状态正常后再低频采集。"
    if action == "safety_locked" and platform and profile:
        return (
            f"账号风控熔断锁正在保护 {platform}/{profile}。"
            "请先确认账号页面没有验证码、登录异常或平台风险提示；确认正常后再点“解除熔断”。"
        )
    return ""


def _settings_notice(status: str) -> dict:
    if not status:
        return {}
    if status == "saved":
        return {"kind": "notice", "message": "GPT-5.5 配置已保存到本地 .env。"}
    if status.startswith("error:"):
        return {"kind": "alert", "message": status.split(":", 1)[1] or "配置保存失败。"}
    return {}
