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
    collected_at: str = field(default_factory=utc_now_iso)
    raw_id: Optional[int] = None


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
