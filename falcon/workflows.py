from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .analysis import HeuristicAnalyzer
from .db import FalconRepository
from .drafting import DraftingService
from .llm import GPT55Client
from .models import RawItem
from .relevance import default_relevance_result, effective_relevance_level, effective_relevance_role
from .reports import DailyReportBuilder


@dataclass
class AnalyzeResult:
    analyzed_count: int
    task_count: int


@dataclass
class RelevanceScoreResult:
    scored_count: int


@dataclass
class PromoteCollectedResult:
    promoted_count: int = 0
    primary_count: int = 0
    reference_count: int = 0
    discarded_count: int = 0
    unscored_count: int = 0


def score_collected_posts(repo: FalconRepository, run_id: Optional[str] = None, limit: Optional[int] = None) -> RelevanceScoreResult:
    scored = 0
    for post in repo.list_collected_posts(run_id=run_id, limit=limit):
        if post.post_id is None:
            continue
        result = default_relevance_result(post)
        repo.update_collected_post_relevance(
            post.post_id,
            score=result.score,
            level=result.level,
            role=result.analysis_role,
            reason=result.reason,
            breakdown_json=result.breakdown_json(),
        )
        scored += 1
    return RelevanceScoreResult(scored_count=scored)


def promote_collected_posts(
    repo: FalconRepository,
    run_id: Optional[str] = None,
    limit: Optional[int] = None,
    return_summary: bool = False,
) -> Union[int, PromoteCollectedResult]:
    result = PromoteCollectedResult()
    for post in repo.list_collected_posts(run_id=run_id, limit=limit):
        level = effective_relevance_level(post)
        role = effective_relevance_role(post)
        if level == "unscored":
            result.unscored_count += 1
            continue
        if role == "discard":
            result.discarded_count += 1
            continue
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
                relevance_score=post.relevance_score,
                relevance_level=level,
                relevance_role=role,
                relevance_reason=post.relevance_reason,
            )
        )
        result.promoted_count += 1
        if role == "primary":
            result.primary_count += 1
        elif role == "reference":
            result.reference_count += 1
    return result if return_summary else result.promoted_count


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
        if item.relevance_role == "reference":
            continue
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
