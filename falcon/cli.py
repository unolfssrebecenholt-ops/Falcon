import argparse
from pathlib import Path
from typing import Optional

from .collector import CollectorService
from .db import FalconRepository
from .doctor import build_doctor_report, ensure_project_directories, format_doctor_report, project_root_from_package
from .image2 import FALCON_AGENT_ARCHITECTURE_PROMPT, Image2Client, load_env_file
from .keyword_pool import write_default_keyword_pool
from .workflows import analyze_unanalyzed, write_report


DEFAULT_DB = Path("data/falcon.sqlite3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Falcon Agent local workbench")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize SQLite schema")

    doctor_parser = subparsers.add_parser("doctor", help="Check local Falcon runtime dependencies")
    doctor_parser.add_argument("--project-root", default=str(project_root_from_package()))
    doctor_parser.add_argument("--ensure-dirs", action="store_true", help="Create local data/runtime/profile folders")

    keyword_pool_parser = subparsers.add_parser("write-keyword-pool", help="Write default collection keyword pool CSV")
    keyword_pool_parser.add_argument("output_path")
    keyword_pool_parser.add_argument("--theme", default="内容运营")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze unanalyzed samples and create outreach tasks")
    analyze_parser.add_argument("--limit", type=int, default=100)
    analyze_parser.add_argument("--drafts", choices=["template", "gpt", "off"], default="template")

    report_parser = subparsers.add_parser("report", help="Write daily Markdown report")
    report_parser.add_argument("--output", default="")
    report_parser.add_argument("--summary", choices=["off", "gpt"], default="off")

    image_parser = subparsers.add_parser("generate-architecture-image", help="Generate Falcon Agent architecture image via Image2")
    image_parser.add_argument("--output", default="reports/falcon-agent-architecture.png")
    image_parser.add_argument("--prompt", default="")

    review_parser = subparsers.add_parser("review-task", help="Update outreach task status and optional feedback")
    review_parser.add_argument("task_id", type=int)
    review_parser.add_argument("status", choices=["pending", "copied", "handled", "skipped", "invalid"])
    review_parser.add_argument("--feedback", default="")
    review_parser.add_argument("--note", default="")

    raw_review_parser = subparsers.add_parser("review-raw-item", help="Record human review feedback for a raw sample")
    raw_review_parser.add_argument("raw_id", type=int)
    raw_review_parser.add_argument("feedback", choices=["优秀", "有用", "一般", "无用", "噪音"])
    raw_review_parser.add_argument("--note", default="")

    collector_dry_run_parser = subparsers.add_parser("collector-dry-run", help="Run the Node collector sidecar in dry-run mode")
    collector_dry_run_parser.add_argument("--platform", default="xiaohongshu")
    collector_dry_run_parser.add_argument("--profile", default="default")
    collector_dry_run_parser.add_argument("--keyword", required=True)
    collector_dry_run_parser.add_argument("--run-id", default="")
    collector_dry_run_parser.add_argument("--max-posts", type=int, default=8)
    collector_dry_run_parser.add_argument("--max-comments-per-post", type=int, default=5)
    collector_dry_run_parser.add_argument("--headed", action="store_true")
    collector_dry_run_parser.add_argument("--runtime-root", default=str(Path("runtime") / "collector"))
    collector_dry_run_parser.add_argument("--profile-root", default="browser-profiles")

    collector_run_parser = subparsers.add_parser("collector-run", help="Run the Node collector sidecar in real browser mode")
    collector_run_parser.add_argument("--platform", default="xiaohongshu")
    collector_run_parser.add_argument("--profile", default="default")
    collector_run_parser.add_argument("--keyword", required=True)
    collector_run_parser.add_argument("--run-id", default="")
    collector_run_parser.add_argument("--max-posts", type=int, default=8)
    collector_run_parser.add_argument("--max-comments-per-post", type=int, default=5)
    collector_run_parser.add_argument("--headless", dest="headed", action="store_false")
    collector_run_parser.set_defaults(headed=True)
    collector_run_parser.add_argument("--runtime-root", default=str(Path("runtime") / "collector"))
    collector_run_parser.add_argument("--profile-root", default="browser-profiles")

    collector_ingest_parser = subparsers.add_parser("collector-ingest", help="Ingest collector sidecar JSONL outputs")
    collector_ingest_parser.add_argument("--run-id", required=True)
    collector_ingest_parser.add_argument("--events", required=True)
    collector_ingest_parser.add_argument("--records", required=True)

    web_parser = subparsers.add_parser("web", help="Run local Falcon web console")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)
    web_parser.add_argument("--db", dest="web_db", help="SQLite database path")

    return parser


def main(argv: Optional[list] = None) -> int:
    load_env_file()
    parser = build_parser()
    args = parser.parse_args(argv)
    repo = FalconRepository(Path(args.db))

    if args.command == "init-db":
        repo.init_schema()
        print(f"Initialized {args.db}")
        return 0

    if args.command == "doctor":
        project_root = Path(args.project_root)
        if args.ensure_dirs:
            ensure_project_directories(project_root)
        report = build_doctor_report(project_root)
        print(format_doctor_report(report))
        return 0 if report.required_ok else 1

    if args.command == "write-keyword-pool":
        tasks = write_default_keyword_pool(Path(args.output_path), theme=args.theme)
        print(f"Wrote {len(tasks)} keyword tasks to {args.output_path}")
        return 0

    if args.command == "analyze":
        repo.init_schema()
        result = analyze_unanalyzed(repo, limit=args.limit, drafts_mode=args.drafts)
        print(f"Analyzed {result.analyzed_count} items, created {result.task_count} outreach tasks")
        return 0

    if args.command == "report":
        repo.init_schema()
        output = Path(args.output) if args.output else Path("reports") / "daily-report.md"
        write_report(repo, output=output, summary_mode=args.summary)
        print(f"Wrote {output}")
        return 0

    if args.command == "generate-architecture-image":
        output = Path(args.output)
        prompt = args.prompt or FALCON_AGENT_ARCHITECTURE_PROMPT
        client = Image2Client.from_env()
        result = client.save(prompt, output)
        print(f"Wrote {output} via Image2 {result.provider_name}")
        return 0

    if args.command == "review-task":
        repo.init_schema()
        repo.update_task_status(args.task_id, args.status)
        if args.feedback:
            repo.add_feedback(args.feedback, args.note, outreach_task_id=args.task_id)
        print(f"Updated task {args.task_id} -> {args.status}")
        return 0

    if args.command == "review-raw-item":
        repo.init_schema()
        feedback_id = repo.add_feedback(args.feedback, args.note, raw_item_id=args.raw_id)
        print(f"Recorded raw item feedback {feedback_id} for raw_id {args.raw_id}")
        return 0

    if args.command == "collector-dry-run":
        repo.init_schema()
        service = CollectorService(
            repo,
            runtime_root=Path(args.runtime_root),
            profile_root=Path(args.profile_root),
        )
        run = service.run_dry_run(
            platform=args.platform,
            profile=args.profile,
            keyword=args.keyword,
            max_posts=args.max_posts,
            max_comments_per_post=args.max_comments_per_post,
            headed=args.headed,
            run_id=args.run_id,
        )
        print(f"Collector dry-run {run.run_id} -> {run.status}")
        return 0 if run.status == "completed" else 1

    if args.command == "collector-run":
        repo.init_schema()
        service = CollectorService(
            repo,
            runtime_root=Path(args.runtime_root),
            profile_root=Path(args.profile_root),
        )
        run = service.run_sidecar(
            platform=args.platform,
            profile=args.profile,
            keyword=args.keyword,
            max_posts=args.max_posts,
            max_comments_per_post=args.max_comments_per_post,
            headed=args.headed,
            dry_run=False,
            run_id=args.run_id,
        )
        print(f"Collector run {run.run_id} -> {run.status}")
        return 0 if run.status == "completed" else 1

    if args.command == "collector-ingest":
        repo.init_schema()
        service = CollectorService(repo)
        service.ingest_outputs(args.run_id, Path(args.events), Path(args.records))
        print(f"Ingested collector outputs for {args.run_id}")
        return 0

    if args.command == "web":
        import uvicorn

        from .web.app import create_app

        db_path = Path(args.web_db or args.db)
        uvicorn.run(create_app(db_path), host=args.host, port=args.port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
