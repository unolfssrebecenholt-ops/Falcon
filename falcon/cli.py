import argparse
from pathlib import Path
from typing import Optional

from .adapters.xiaohongshu_csv import XiaohongshuCsvAdapter
from .adapters.yingdao_xlsx import YingdaoXlsxAdapter
from .analysis import HeuristicAnalyzer
from .db import FalconRepository
from .drafting import DraftingService
from .keyword_pool import write_default_keyword_pool
from .llm import GPT55Client
from .reports import DailyReportBuilder


DEFAULT_DB = Path("data/falcon.sqlite3")


def main(argv: Optional[list] = None) -> int:
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
        analyzed, tasks = _analyze(repo, limit=args.limit, drafts_mode=args.drafts)
        print(f"Analyzed {analyzed} items, created {tasks} outreach tasks")
        return 0

    if args.command == "run-yingdao-daily":
        repo.init_schema()
        items = YingdaoXlsxAdapter().load(
            Path(args.xlsx_path),
            keyword=args.keyword,
            platform=args.platform,
            source_type=args.source_type,
        )
        ids = repo.upsert_raw_items(items)
        print(f"Imported {len(set(ids))} unique items from {args.xlsx_path}")
        analyzed, tasks = _analyze(repo, limit=args.limit, drafts_mode=args.drafts)
        print(f"Analyzed {analyzed} items, created {tasks} outreach tasks")
        output = Path(args.report_output) if args.report_output else Path("reports") / "daily-report.md"
        _write_report(repo, output=output, summary_mode=args.summary)
        print(f"Wrote {output}")
        return 0

    if args.command == "report":
        repo.init_schema()
        output = Path(args.output) if args.output else Path("reports") / "daily-report.md"
        _write_report(repo, output=output, summary_mode=args.summary)
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

    parser.print_help()
    return 1


def _analyze(repo: FalconRepository, limit: int, drafts_mode: str) -> tuple:
    client = GPT55Client.from_env() if drafts_mode == "gpt" else None
    if drafts_mode == "gpt" and not client.is_configured():
        raise SystemExit("GPT mode requires FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY")

    analyzer = HeuristicAnalyzer()
    drafting = DraftingService(client=client if drafts_mode == "gpt" else None)
    analyzed = 0
    tasks = 0
    for item in repo.list_raw_items(limit=limit, unanalyzed_only=True):
        result = analyzer.analyze(item)
        analysis_id = repo.save_analysis(item.raw_id or 0, result)
        analyzed += 1
        if result.outreach_type != "ignore" and drafts_mode != "off":
            drafts, risk_note = drafting.generate(item, result)
            if drafts:
                repo.create_outreach_task(item.raw_id or 0, analysis_id, result, drafts, risk_note)
                tasks += 1
    return analyzed, tasks


def _write_report(repo: FalconRepository, output: Path, summary_mode: str) -> None:
    summary_client = GPT55Client.from_env() if summary_mode == "gpt" else None
    if summary_mode == "gpt" and not summary_client.is_configured():
        raise SystemExit("GPT summary requires FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY")
    report = DailyReportBuilder(repo, summary_client=summary_client).build_markdown()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
