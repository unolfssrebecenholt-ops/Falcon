from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .analysis import HeuristicAnalyzer
from .db import FalconRepository
from .drafting import DraftingService
from .llm import GPT55Client
from .models import RawItem
from .reports import DailyReportBuilder


@dataclass
class AnalyzeResult:
    analyzed_count: int
    task_count: int


def promote_collected_posts(repo: FalconRepository, run_id: Optional[str] = None, limit: Optional[int] = None) -> int:
    promoted = 0
    for post in repo.list_collected_posts(run_id=run_id, limit=limit):
        repo.upsert_raw_item(
            RawItem(
                platform=post.platform,
                keyword=post.keyword,
                source_type="post",
                title=post.title,
                content=post.content,
                url=post.url,
                author=post.author,
                like_count=post.like_count,
                published_at=post.published_at,
            )
        )
        promoted += 1
    return promoted


def analyze_unanalyzed(
    repo: FalconRepository,
    limit: int = 100,
    drafts_mode: str = "template",
    client: Optional[GPT55Client] = None,
) -> AnalyzeResult:
    if drafts_mode == "gpt":
        client = client or GPT55Client.from_env()
        if not client.is_configured():
            raise SystemExit("GPT mode requires FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY")
    else:
        client = None

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
    return AnalyzeResult(analyzed_count=analyzed, task_count=tasks)


def write_report(repo: FalconRepository, output: Path, summary_mode: str = "off") -> Path:
    summary_client = GPT55Client.from_env() if summary_mode == "gpt" else None
    if summary_mode == "gpt" and not summary_client.is_configured():
        raise SystemExit("GPT summary requires FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY")
    report = DailyReportBuilder(repo, summary_client=summary_client).build_markdown()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    return output
