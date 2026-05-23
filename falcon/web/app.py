from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..collector import CollectorService, safe_collector_identifier
from ..db import FalconRepository
from ..doctor import build_doctor_report, checks_for_web
from ..keyword_pool import load_keyword_tasks, write_default_keyword_pool
from ..models import CollectionEvent, CollectionRun
from ..profiles import SUPPORTED_PROFILE_LOGIN_PLATFORMS, launch_profile_login, list_profile_entries
from ..workflows import promote_collected_posts


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
    "manual_action_required": "人工处理",
}
COLLECTOR_EVENT_LABELS = {
    "request_prepared": "请求已准备",
    "run_started": "任务启动",
    "profile_loaded": "账号环境已加载",
    "browser_launching": "浏览器启动",
    "detail_opening": "打开详情",
    "record_collected": "记录生成",
    "records_collected": "记录生成",
    "media_download_failed": "图片下载失败",
    "manual_action_required": "等待人工处理",
    "run_completed": "任务完成",
    "run_failed": "任务失败",
    "rerun_created": "已创建重跑",
    "run_marked_failed": "人工标记失败",
    "run_archived": "任务归档",
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
    "screenshot": "截图",
    "asset": "素材",
}
EVIDENCE_SCOPE_LABELS = {
    "dry_run_fixture": "测试合同",
    "search_results_screenshot": "搜索页截图",
    "field_snapshot": "字段快照",
    "detail_screenshot": "详情页截图",
    "screenshot": "截图",
    "manual_action_required": "人工处理",
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
        return "已生成测试合同记录"
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


templates.env.filters["collector_status"] = collector_status_label
templates.env.filters["collector_level"] = collector_level_label
templates.env.filters["collector_scope"] = collector_scope_label
templates.env.filters["collector_event"] = collector_event_label
templates.env.filters["collector_message"] = collector_message_label
templates.env.filters["collector_step"] = collector_step_label
templates.env.filters["platform_label"] = platform_label
templates.env.filters["asset_type"] = asset_type_label
templates.env.filters["evidence_scope"] = evidence_scope_label
SHANGHAI_TZ = timezone(timedelta(hours=8))


def readable_time(value: str) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "-"
    return parsed.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


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
        return "采集中"
    return "无占用"


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
templates.env.filters["run_duration"] = run_duration_label
templates.env.filters["run_progress_stage"] = run_progress_stage
templates.env.filters["run_resource"] = run_resource_label


def create_app(db_path: Path, doctor_report_builder=None, profile_root=None, profile_login_launcher=None) -> FastAPI:
    app = FastAPI(title="Falcon 控制台")
    app.state.db_path = Path(db_path)
    app.state.last_run = None
    app.state.runtime_root = Path(db_path).parent / "runtime" / "collector"
    app.state.profile_root = Path(profile_root) if profile_root is not None else Path("browser-profiles")
    app.state.project_root = Path(__file__).resolve().parents[2]
    app.state.doctor_report_builder = doctor_report_builder or build_doctor_report
    app.state.profile_login_launcher = profile_login_launcher or launch_profile_login
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
                "active": "dashboard",
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
    def write_keywords(path: str = Form("data/collection_keywords.csv"), theme: str = Form("生图小程序")):
        write_default_keyword_pool(Path(path), theme=theme)
        return RedirectResponse(f"/keywords?path={path}", status_code=303)

    @app.get("/collector")
    def collector_page(
        request: Request,
        profile_action: str = "",
        profile_platform: str = "",
        profile_name: str = "",
    ):
        repository = repo()
        runs = repository.list_collection_runs(limit=20)
        dashboard = repository.collector_dashboard()
        posts = repository.list_collected_posts(limit=50)
        queued_runs = [run for run in runs if run.status in {"queued", "running", "manual_action_required"}]
        doctor_report = app.state.doctor_report_builder(app.state.project_root)
        environment_checks = checks_for_web(doctor_report)
        return templates.TemplateResponse(
            request,
            "collector.html",
            {
                "active": "collector",
                "stats": dashboard,
                "platforms": _platform_cards(runs, posts),
                "runs": runs,
                "queued_runs": queued_runs,
                "profile_summary": _profile_summary(runs),
                "profile_entries": list_profile_entries(
                    app.state.profile_root,
                    runs,
                    [item["key"] for item in _collector_platforms()],
                ),
                "profile_notice": _profile_notice(profile_action, profile_platform, profile_name),
                "profile_login_supported_platforms": SUPPORTED_PROFILE_LOGIN_PLATFORMS,
                "environment_checks": environment_checks,
                "environment_ready": doctor_report.required_ok,
                "environment_summary": _environment_summary(environment_checks),
            },
        )

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
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not open profile login window: {exc}") from exc
        return RedirectResponse(
            f"/collector?profile_action=opened&profile_platform={clean_platform}&profile_name={clean_profile}",
            status_code=303,
        )

    @app.get("/collector/create")
    def collector_create_page(request: Request):
        return templates.TemplateResponse(
            request,
            "collector_create.html",
            {
                "active": "collector_create",
                "platforms": _collector_platforms(),
                "defaults": {
                    "platform": "xiaohongshu",
                    "profile": "default",
                    "max_posts": 20,
                    "max_comments_per_post": 10,
                },
            },
        )

    @app.post("/collector/create")
    def create_collection_run(
        platform: str = Form(...),
        profile: str = Form(...),
        keyword: str = Form(...),
        max_posts: int = Form(20),
        max_comments_per_post: int = Form(10),
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
        run = CollectionRun(
            run_id=_new_run_id(clean_platform),
            platform=clean_platform,
            keyword=keyword.strip(),
            profile=clean_profile,
            status="queued",
            progress=0,
            current_step="等待浏览器采集调度",
            max_posts=max(1, max_posts),
            max_comments_per_post=max(0, max_comments_per_post),
        )
        repository.create_collection_run(run)
        collector_service(repository).prepare_run_request(run, headed=True, dry_run=False)
        repository.append_collection_event(
            CollectionEvent(
                run_id=run.run_id,
                sequence=1,
                scope="core",
                event="request_prepared",
                message="采集请求已准备，等待启动。",
            )
        )
        return RedirectResponse(f"/collector/runs/{run.run_id}", status_code=303)

    @app.get("/collector/runs/{run_id}")
    def collector_run_detail(request: Request, run_id: str):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
        return templates.TemplateResponse(
            request,
            "collector_run.html",
            {
                "active": "collector_run",
                "current_run": run,
                "run": run,
                "events": repository.list_collection_events(run_id),
                "posts": repository.list_collected_posts(run_id=run_id),
                "assets": repository.list_media_assets(run_id),
                "evidences": repository.list_evidences(run_id),
            },
        )

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
    def archive_collection_run(run_id: str):
        repository = repo()
        run = repository.get_collection_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Collection run not found")
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
        return templates.TemplateResponse(
            request,
            "collector_post.html",
            {
                "active": "collector_run",
                "current_run": run,
                "run": run,
                "post": post,
                "comments": repository.list_collected_comments(run_id=run_id, post_id=post.post_id),
                "assets": assets,
            },
        )

    @app.get("/analysis")
    def analysis_page(request: Request):
        scored_items = repo().list_scored_items(limit=100)
        keyword_stats = _keyword_stats(scored_items)
        high_intent = [item for item in scored_items if int(item.get("intent_score") or 0) >= 80]
        return templates.TemplateResponse(
            request,
            "analysis.html",
            {
                "active": "analysis",
                "items": scored_items,
                "keyword_stats": keyword_stats,
                "stats": {
                    "scored_count": len(scored_items),
                    "high_intent_count": len(high_intent),
                    "keyword_count": len(keyword_stats),
                },
            },
        )

    @app.post("/analysis/promote")
    def promote_collector_samples():
        repository = repo()
        promoted = promote_collected_posts(repository)
        app.state.last_run = {"message": f"已送入分析队列 {promoted} 条采集样本", "report_path": ""}
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
                "post_count": post_counts.get(key, 0),
                "latest": latest.get(key),
            }
        )
    return cards


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
    if action == "opened" and platform and profile:
        return f"已打开 {platform}/{profile} 登录窗口。请在弹出的浏览器里完成登录，完成后关闭窗口。"
    return ""
