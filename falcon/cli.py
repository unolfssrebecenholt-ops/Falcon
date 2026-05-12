import argparse
from pathlib import Path
from typing import Optional

from .adapters.xiaohongshu_csv import XiaohongshuCsvAdapter
from .adapters.yingdao_xlsx import YingdaoXlsxAdapter
from .db import FalconRepository
from .keyword_pool import write_default_keyword_pool
from .workflows import analyze_unanalyzed, run_yingdao_daily, write_report


DEFAULT_DB = Path("data/falcon.sqlite3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Falcon demand radar MVP")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize SQLite schema")

    import_parser = subparsers.add_parser("import-csv", help="Import Xiaohongshu RPA CSV")
    import_parser.add_argument("csv_path")

    yingdao_parser = subparsers.add_parser("import-yingdao-xlsx", help="Import Yingdao/Xiaohongshu xlsx export")
    yingdao_parser.add_argument("xlsx_path")
    yingdao_parser.add_argument("--keyword", required=True, help="Keyword or theme used for this Yingdao sampling run")
    yingdao_parser.add_argument("--platform", default="xiaohongshu")
    yingdao_parser.add_argument("--source-type", default="post", choices=["post", "comment"])

    keyword_pool_parser = subparsers.add_parser("write-keyword-pool", help="Write default RPA keyword pool CSV")
    keyword_pool_parser.add_argument("output_path")
    keyword_pool_parser.add_argument("--theme", default="生图小程序")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze unanalyzed samples and create outreach tasks")
    analyze_parser.add_argument("--limit", type=int, default=100)
    analyze_parser.add_argument("--drafts", choices=["template", "gpt", "off"], default="template")

    daily_parser = subparsers.add_parser("run-yingdao-daily", help="Import Yingdao xlsx, analyze, and write report")
    daily_parser.add_argument("xlsx_path")
    daily_parser.add_argument("--keyword", required=True)
    daily_parser.add_argument("--platform", default="xiaohongshu")
    daily_parser.add_argument("--source-type", default="post", choices=["post", "comment"])
    daily_parser.add_argument("--limit", type=int, default=100)
    daily_parser.add_argument("--drafts", choices=["template", "gpt", "off"], default="template")
    daily_parser.add_argument("--report-output", default="")
    daily_parser.add_argument("--summary", choices=["off", "gpt"], default="off")

    report_parser = subparsers.add_parser("report", help="Write daily Markdown report")
    report_parser.add_argument("--output", default="")
    report_parser.add_argument("--summary", choices=["off", "gpt"], default="off")

    review_parser = subparsers.add_parser("review-task", help="Update outreach task status and optional feedback")
    review_parser.add_argument("task_id", type=int)
    review_parser.add_argument("status", choices=["pending", "copied", "handled", "skipped", "invalid"])
    review_parser.add_argument("--feedback", default="")
    review_parser.add_argument("--note", default="")

    raw_review_parser = subparsers.add_parser("review-raw-item", help="Record human review feedback for a raw sample")
    raw_review_parser.add_argument("raw_id", type=int)
    raw_review_parser.add_argument("feedback", choices=["优秀", "有用", "一般", "无用", "噪音"])
    raw_review_parser.add_argument("--note", default="")

    web_parser = subparsers.add_parser("web", help="Run local Falcon web console")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)
    web_parser.add_argument("--db", dest="web_db", help="SQLite database path")

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo = FalconRepository(Path(args.db))

    if args.command == "init-db":
        repo.init_schema()
        print(f"Initialized {args.db}")
        return 0

    if args.command == "import-csv":
        repo.init_schema()
        items = XiaohongshuCsvAdapter().load(Path(args.csv_path))
        ids = repo.upsert_raw_items(items)
        print(f"Imported {len(set(ids))} unique items from {args.csv_path}")
        return 0

    if args.command == "import-yingdao-xlsx":
        repo.init_schema()
        items = YingdaoXlsxAdapter().load(
            Path(args.xlsx_path),
            keyword=args.keyword,
            platform=args.platform,
            source_type=args.source_type,
        )
        ids = repo.upsert_raw_items(items)
        print(f"Imported {len(set(ids))} unique items from {args.xlsx_path}")
        return 0

    if args.command == "write-keyword-pool":
        tasks = write_default_keyword_pool(Path(args.output_path), theme=args.theme)
        print(f"Wrote {len(tasks)} keyword tasks to {args.output_path}")
        return 0

    if args.command == "analyze":
        repo.init_schema()
        result = analyze_unanalyzed(repo, limit=args.limit, drafts_mode=args.drafts)
        print(f"Analyzed {result.analyzed_count} items, created {result.task_count} outreach tasks")
        return 0

    if args.command == "run-yingdao-daily":
        repo.init_schema()
        result = run_yingdao_daily(
            repo,
            xlsx_path=Path(args.xlsx_path),
            keyword=args.keyword,
            platform=args.platform,
            source_type=args.source_type,
            limit=args.limit,
            drafts_mode=args.drafts,
            report_output=Path(args.report_output) if args.report_output else Path("reports") / "daily-report.md",
            summary_mode=args.summary,
        )
        print(f"Imported {result.imported_count} unique items from {args.xlsx_path}")
        print(f"Analyzed {result.analyzed_count} items, created {result.task_count} outreach tasks")
        print(f"Wrote {result.report_path}")
        return 0

    if args.command == "report":
        repo.init_schema()
        output = Path(args.output) if args.output else Path("reports") / "daily-report.md"
        write_report(repo, output=output, summary_mode=args.summary)
        print(f"Wrote {output}")
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
