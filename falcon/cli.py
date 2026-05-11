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

    report_parser = subparsers.add_parser("report", help="Write daily Markdown report")
    report_parser.add_argument("--output", default="")
    report_parser.add_argument("--summary", choices=["off", "gpt"], default="off")

    review_parser = subparsers.add_parser("review-task", help="Update outreach task status and optional feedback")
    review_parser.add_argument("task_id", type=int)
    review_parser.add_argument("status", choices=["pending", "copied", "handled", "skipped", "invalid"])
    review_parser.add_argument("--feedback", default="")
    review_parser.add_argument("--note", default="")

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
        client = GPT55Client.from_env() if args.drafts == "gpt" else None
        if args.drafts == "gpt" and not client.is_configured():
            raise SystemExit("GPT mode requires FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY")

        analyzer = HeuristicAnalyzer()
        drafting = DraftingService(client=client if args.drafts == "gpt" else None)
        analyzed = 0
        tasks = 0
        for item in repo.list_raw_items(limit=args.limit, unanalyzed_only=True):
            result = analyzer.analyze(item)
            analysis_id = repo.save_analysis(item.raw_id or 0, result)
            analyzed += 1
            if result.outreach_type != "ignore" and args.drafts != "off":
                drafts, risk_note = drafting.generate(item, result)
                if drafts:
                    repo.create_outreach_task(item.raw_id or 0, analysis_id, result, drafts, risk_note)
                    tasks += 1
        print(f"Analyzed {analyzed} items, created {tasks} outreach tasks")
        return 0

    if args.command == "report":
        repo.init_schema()
        summary_client = GPT55Client.from_env() if args.summary == "gpt" else None
        if args.summary == "gpt" and not summary_client.is_configured():
            raise SystemExit("GPT summary requires FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY")
        report = DailyReportBuilder(repo, summary_client=summary_client).build_markdown()
        output = Path(args.output) if args.output else Path("reports") / "daily-report.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(f"Wrote {output}")
        return 0

    if args.command == "review-task":
        repo.init_schema()
        repo.update_task_status(args.task_id, args.status)
        if args.feedback:
            repo.add_feedback(args.feedback, args.note, outreach_task_id=args.task_id)
        print(f"Updated task {args.task_id} -> {args.status}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
