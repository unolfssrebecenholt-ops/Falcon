from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
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
            current_step="queued for browser collector",
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
                message="Sidecar request prepared; waiting for manual start.",
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
        {"key": "xiaohongshu", "name": "小红书", "status": "第一阶段"},
        {"key": "douyin", "name": "抖音", "status": "入口占位"},
        {"key": "weibo", "name": "微博", "status": "入口占位"},
        {"key": "xianyu", "name": "闲鱼", "status": "入口占位"},
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
