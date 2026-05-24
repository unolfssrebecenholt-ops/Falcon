from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class RawItem:
    platform: str
    keyword: str
    source_type: str
    title: str
    content: str
    url: str
    parent_url: str = ""
    author: str = ""
    commenter: str = ""
    like_count: str = ""
    comment_rank: str = ""
    published_at: str = ""
    relevance_score: int = -1
    relevance_level: str = "unscored"
    relevance_role: str = "pending"
    relevance_reason: str = ""
    collected_at: str = field(default_factory=utc_now_iso)
    raw_id: Optional[int] = None


@dataclass
class CollectionRun:
    run_id: str
    platform: str
    keyword: str
    profile: str
    status: str = "queued"
    progress: int = 0
    current_step: str = ""
    max_posts: int = 20
    max_comments_per_post: int = 10
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    completed_at: str = ""
    failed_reason: str = ""


@dataclass
class CollectionEvent:
    run_id: str
    sequence: int
    scope: str
    event: str
    message: str
    level: str = "info"
    payload_json: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    event_id: Optional[int] = None


@dataclass
class CollectedPost:
    run_id: str
    platform: str
    keyword: str
    title: str
    content: str
    url: str
    author: str = ""
    published_at: str = ""
    like_count: str = ""
    collect_count: str = ""
    comment_count: str = ""
    detail_fingerprint: str = ""
    relevance_score: int = -1
    relevance_level: str = "unscored"
    relevance_role: str = "pending"
    relevance_reason: str = ""
    relevance_breakdown_json: str = "{}"
    relevance_updated_at: str = ""
    manual_relevance_level: str = ""
    manual_relevance_note: str = ""
    collected_at: str = field(default_factory=utc_now_iso)
    post_id: Optional[int] = None


@dataclass
class CollectedComment:
    post_id: int
    run_id: str
    commenter: str
    content: str
    like_count: str = ""
    comment_rank: str = ""
    comment_type: str = "comment"
    reply_to: str = ""
    collected_at: str = field(default_factory=utc_now_iso)
    comment_id: Optional[int] = None


@dataclass
class MediaAsset:
    run_id: str
    path: str
    asset_type: str
    post_id: Optional[int] = None
    url: str = ""
    sha256: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    asset_id: Optional[int] = None


@dataclass
class Evidence:
    run_id: str
    evidence_type: str
    path: str
    scope: str = ""
    payload_json: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    evidence_id: Optional[int] = None


@dataclass
class Draft:
    kind: str
    text: str


@dataclass
class OutreachTask:
    task_id: int
    raw_id: int
    analysis_id: int
    outreach_type: str
    outreach_priority: str
    task_status: str
    risk_note: str
    drafts: List[Draft]
    url: str
    title: str
    content: str
    handled_at: str = ""
