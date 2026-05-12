from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..db import FalconRepository
from ..keyword_pool import load_keyword_tasks, write_default_keyword_pool
from ..workflows import run_yingdao_daily


WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="Falcon 控制台")
    app.state.db_path = Path(db_path)
    app.state.last_run = None
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def repo() -> FalconRepository:
        repository = FalconRepository(app.state.db_path)
        repository.init_schema()
        return repository

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

    @app.get("/run")
    def run_page(request: Request):
        return templates.TemplateResponse(
            request,
            "run.html",
            {
                "active": "run",
                "default_xlsx_path": "data/xhs_raw_export.xlsx",
                "default_keyword": "生图小程序",
                "default_report_output": "reports/daily-report.md",
                "last_run": app.state.last_run,
            },
        )

    @app.post("/run")
    def run_daily(
        xlsx_path: str = Form(...),
        keyword: str = Form(...),
        drafts: str = Form("template"),
        report_output: str = Form("reports/daily-report.md"),
    ):
        repository = repo()
        try:
            result = run_yingdao_daily(
                repository,
                xlsx_path=Path(xlsx_path),
                keyword=keyword,
                report_output=Path(report_output),
                drafts_mode=drafts,
            )
        except Exception as exc:
            app.state.last_run = {
                "error": f"{type(exc).__name__}: {exc}",
                "report_path": report_output,
            }
            return RedirectResponse("/run", status_code=303)

        app.state.last_run = {
            "imported_count": result.imported_count,
            "analyzed_count": result.analyzed_count,
            "task_count": result.task_count,
            "report_path": str(result.report_path),
        }
        return RedirectResponse("/run", status_code=303)

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
    def keywords_page(request: Request, path: str = "data/rpa_keywords.csv"):
        keyword_path = Path(path)
        tasks = load_keyword_tasks(keyword_path) if keyword_path.exists() else []
        return templates.TemplateResponse(
            request,
            "keywords.html",
            {"active": "keywords", "keyword_path": str(keyword_path), "tasks": tasks},
        )

    @app.post("/keywords/default")
    def write_keywords(path: str = Form("data/rpa_keywords.csv"), theme: str = Form("生图小程序")):
        write_default_keyword_pool(Path(path), theme=theme)
        return RedirectResponse(f"/keywords?path={path}", status_code=303)

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
