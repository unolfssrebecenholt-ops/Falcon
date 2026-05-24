import json
from dataclasses import dataclass, field
from typing import Dict, Sequence

from .models import CollectedComment, CollectedPost


LEVEL_LABELS = {
    "excellent": "优质",
    "medium": "中等",
    "poor": "劣质",
    "unscored": "未评分",
}
ROLE_LABELS = {
    "primary": "主分析",
    "reference": "参考",
    "discard": "跳过",
    "pending": "待评分",
}

DEFAULT_RELEVANCE_SCORE = 100
DEFAULT_RELEVANCE_LEVEL = "excellent"
DEFAULT_RELEVANCE_ROLE = "primary"
DEFAULT_RELEVANCE_REASON = "默认优质：采集样本默认进入主分析；如需降级或剔除，请人工校准。"


@dataclass
class RelevanceResult:
    score: int
    level: str
    analysis_role: str
    reason: str
    breakdown: Dict[str, int] = field(default_factory=dict)

    def breakdown_json(self) -> str:
        return json.dumps(self.breakdown, ensure_ascii=False)


def default_relevance_result(
    post: CollectedPost,
    comments: Sequence[CollectedComment] = (),
    asset_count: int = 0,
) -> RelevanceResult:
    return RelevanceResult(
        score=DEFAULT_RELEVANCE_SCORE,
        level=DEFAULT_RELEVANCE_LEVEL,
        analysis_role=DEFAULT_RELEVANCE_ROLE,
        reason=DEFAULT_RELEVANCE_REASON,
        breakdown={
            "default_quality": DEFAULT_RELEVANCE_SCORE,
            "manual_override": 0,
        },
    )


def relevance_role_for_level(level: str) -> str:
    if level == "excellent":
        return "primary"
    if level == "medium":
        return "reference"
    if level == "poor":
        return "discard"
    return "pending"


def effective_relevance_level(post: CollectedPost) -> str:
    return post.manual_relevance_level or post.relevance_level or "unscored"


def effective_relevance_role(post: CollectedPost) -> str:
    return relevance_role_for_level(effective_relevance_level(post))


def relevance_label(level: str) -> str:
    return LEVEL_LABELS.get(level or "unscored", level or "-")


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role or "pending", role or "-")
