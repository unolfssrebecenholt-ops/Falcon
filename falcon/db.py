import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .analysis import AnalysisResult
from .models import Draft, OutreachTask, RawItem, utc_now_iso


class FalconRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def init_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_hash TEXT NOT NULL UNIQUE,
                    platform TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT NOT NULL DEFAULT '',
                    collected_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ai_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_item_id INTEGER NOT NULL,
                    scene_tag TEXT NOT NULL,
                    intent_score INTEGER NOT NULL,
                    content_value_score INTEGER NOT NULL,
                    pain_point TEXT NOT NULL,
                    suggested_topic TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    outreach_type TEXT NOT NULL,
                    outreach_priority TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(raw_item_id) REFERENCES raw_items(id)
                );

                CREATE TABLE IF NOT EXISTS outreach_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_item_id INTEGER NOT NULL,
                    analysis_id INTEGER NOT NULL,
                    outreach_type TEXT NOT NULL,
                    outreach_priority TEXT NOT NULL,
                    drafts_json TEXT NOT NULL,
                    risk_note TEXT NOT NULL,
                    task_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    handled_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(raw_item_id) REFERENCES raw_items(id),
                    FOREIGN KEY(analysis_id) REFERENCES ai_scores(id)
                );

                CREATE TABLE IF NOT EXISTS review_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_item_id INTEGER,
                    outreach_task_id INTEGER,
                    human_feedback TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert_raw_item(self, item: RawItem) -> int:
        source_hash = self._source_hash(item)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO raw_items (
                    source_hash, platform, keyword, source_type, title, content, url, published_at, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_hash,
                    item.platform,
                    item.keyword,
                    item.source_type,
                    item.title,
                    item.content,
                    item.url,
                    item.published_at,
                    item.collected_at,
                ),
            )
            row = conn.execute("SELECT id FROM raw_items WHERE source_hash = ?", (source_hash,)).fetchone()
            return int(row["id"])

    def upsert_raw_items(self, items: List[RawItem]) -> List[int]:
        return [self.upsert_raw_item(item) for item in items]

    def list_raw_items(self, limit: Optional[int] = None, unanalyzed_only: bool = False) -> List[RawItem]:
        sql = "SELECT raw_items.* FROM raw_items"
        params: List[object] = []
        if unanalyzed_only:
            sql += " LEFT JOIN ai_scores ON ai_scores.raw_item_id = raw_items.id WHERE ai_scores.id IS NULL"
        sql += " ORDER BY raw_items.id ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_raw_item(row) for row in rows]

    def save_analysis(self, raw_item_id: int, result: AnalysisResult) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ai_scores (
                    raw_item_id, scene_tag, intent_score, content_value_score, pain_point,
                    suggested_topic, recommended_action, outreach_type, outreach_priority, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw_item_id,
                    result.scene_tag,
                    result.intent_score,
                    result.content_value_score,
                    result.pain_point,
                    result.suggested_topic,
                    result.recommended_action,
                    result.outreach_type,
                    result.outreach_priority,
                    result.reason,
                    utc_now_iso(),
                ),
            )
            return int(cursor.lastrowid)

    def create_outreach_task(
        self,
        raw_item_id: int,
        analysis_id: int,
        result: AnalysisResult,
        drafts: List[Draft],
        risk_note: str,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO outreach_tasks (
                    raw_item_id, analysis_id, outreach_type, outreach_priority,
                    drafts_json, risk_note, task_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    raw_item_id,
                    analysis_id,
                    result.outreach_type,
                    result.outreach_priority,
                    json.dumps([draft.__dict__ for draft in drafts], ensure_ascii=False),
                    risk_note,
                    utc_now_iso(),
                ),
            )
            return int(cursor.lastrowid)

    def list_outreach_tasks(self, status: Optional[str] = None, limit: Optional[int] = None) -> List[OutreachTask]:
        sql = """
            SELECT
                outreach_tasks.*,
                raw_items.title,
                raw_items.content,
                raw_items.url
            FROM outreach_tasks
            JOIN raw_items ON raw_items.id = outreach_tasks.raw_item_id
        """
        params: List[object] = []
        if status:
            sql += " WHERE outreach_tasks.task_status = ?"
            params.append(status)
        sql += """
            ORDER BY
                CASE outreach_tasks.outreach_priority
                    WHEN 'high' THEN 0
                    WHEN 'medium' THEN 1
                    ELSE 2
                END,
                outreach_tasks.id DESC
        """
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_task(row) for row in rows]

    def list_scored_items(self, limit: int = 20) -> List[Dict[str, object]]:
        sql = """
            SELECT
                raw_items.id AS raw_id,
                raw_items.platform,
                raw_items.keyword,
                raw_items.source_type,
                raw_items.title,
                raw_items.content,
                raw_items.url,
                ai_scores.*
            FROM ai_scores
            JOIN raw_items ON raw_items.id = ai_scores.raw_item_id
            ORDER BY ai_scores.intent_score DESC, ai_scores.content_value_score DESC, ai_scores.id DESC
            LIMIT ?
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, (limit,)).fetchall()]

    def keyword_stats(self) -> List[Dict[str, object]]:
        sql = """
            SELECT
                raw_items.keyword,
                COUNT(*) AS total,
                ROUND(AVG(ai_scores.intent_score), 1) AS avg_intent,
                SUM(CASE WHEN ai_scores.intent_score >= 80 THEN 1 ELSE 0 END) AS high_intent
            FROM raw_items
            LEFT JOIN ai_scores ON ai_scores.raw_item_id = raw_items.id
            GROUP BY raw_items.keyword
            ORDER BY high_intent DESC, avg_intent DESC, total DESC
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql).fetchall()]

    def add_feedback(
        self,
        human_feedback: str,
        note: str = "",
        raw_item_id: Optional[int] = None,
        outreach_task_id: Optional[int] = None,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO review_feedback (
                    raw_item_id, outreach_task_id, human_feedback, note, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (raw_item_id, outreach_task_id, human_feedback, note, utc_now_iso()),
            )
            return int(cursor.lastrowid)

    def update_task_status(self, task_id: int, status: str) -> None:
        handled_at = utc_now_iso() if status in {"copied", "handled", "skipped", "invalid"} else ""
        with self._connect() as conn:
            conn.execute(
                "UPDATE outreach_tasks SET task_status = ?, handled_at = ? WHERE id = ?",
                (status, handled_at, task_id),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _source_hash(self, item: RawItem) -> str:
        payload = "\n".join([item.platform, item.url, item.title, item.content])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _row_to_raw_item(self, row: sqlite3.Row) -> RawItem:
        return RawItem(
            raw_id=int(row["id"]),
            platform=row["platform"],
            keyword=row["keyword"],
            source_type=row["source_type"],
            title=row["title"],
            content=row["content"],
            url=row["url"],
            published_at=row["published_at"],
            collected_at=row["collected_at"],
        )

    def _row_to_task(self, row: sqlite3.Row) -> OutreachTask:
        drafts_payload = json.loads(row["drafts_json"])
        drafts = [Draft(kind=item["kind"], text=item["text"]) for item in drafts_payload]
        return OutreachTask(
            task_id=int(row["id"]),
            raw_id=int(row["raw_item_id"]),
            analysis_id=int(row["analysis_id"]),
            outreach_type=row["outreach_type"],
            outreach_priority=row["outreach_priority"],
            task_status=row["task_status"],
            risk_note=row["risk_note"],
            drafts=drafts,
            url=row["url"],
            title=row["title"],
            content=row["content"],
            handled_at=row["handled_at"],
        )
