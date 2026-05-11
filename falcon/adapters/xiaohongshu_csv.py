import csv
from pathlib import Path
from typing import Dict, Iterable, List

from ..models import RawItem


HEADER_ALIASES = {
    "platform": ["platform", "平台"],
    "keyword": ["keyword", "关键词", "搜索词"],
    "source_type": ["source_type", "类型", "来源类型"],
    "title": ["title", "标题", "帖子标题"],
    "content": ["content", "正文", "内容", "评论", "评论内容"],
    "url": ["url", "链接", "来源链接"],
    "published_at": ["published_at", "发布时间", "时间"],
}


class XiaohongshuCsvAdapter:
    def load(self, path: Path) -> List[RawItem]:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return [self._row_to_item(row) for row in reader if self._has_content(row)]

    def _row_to_item(self, row: Dict[str, str]) -> RawItem:
        return RawItem(
            platform=self._value(row, "platform") or "xiaohongshu",
            keyword=self._value(row, "keyword") or "小红书封面",
            source_type=self._value(row, "source_type") or "comment",
            title=self._value(row, "title"),
            content=self._value(row, "content"),
            url=self._value(row, "url"),
            published_at=self._value(row, "published_at"),
        )

    def _value(self, row: Dict[str, str], field: str) -> str:
        for key in HEADER_ALIASES[field]:
            if key in row and row[key]:
                return row[key].strip()
        return ""

    def _has_content(self, row: Dict[str, str]) -> bool:
        return bool(self._value(row, "title") or self._value(row, "content"))
