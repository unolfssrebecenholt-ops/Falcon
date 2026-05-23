import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .analysis import AnalysisResult
from .models import (
    CollectedComment,
    CollectedPost,
    CollectionEvent,
    CollectionRun,
    Draft,
    Evidence,
    MediaAsset,
    OutreachTask,
    RawItem,
    utc_now_iso,
)


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
                    parent_url TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    commenter TEXT NOT NULL DEFAULT '',
                    like_count TEXT NOT NULL DEFAULT '',
                    comment_rank TEXT NOT NULL DEFAULT '',
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

                CREATE TABLE IF NOT EXISTS collection_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    platform TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT NOT NULL DEFAULT '',
                    max_posts INTEGER NOT NULL DEFAULT 20,
                    max_comments_per_post INTEGER NOT NULL DEFAULT 10,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    failed_reason TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS collection_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    scope TEXT NOT NULL,
                    event TEXT NOT NULL,
                    message TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'info',
                    payload_json TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_events_run_exact
                    ON collection_events(run_id, sequence, event, message);

                CREATE TABLE IF NOT EXISTS collected_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    url TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT '',
                    published_at TEXT NOT NULL DEFAULT '',
                    like_count TEXT NOT NULL DEFAULT '',
                    comment_count TEXT NOT NULL DEFAULT '',
                    detail_fingerprint TEXT NOT NULL DEFAULT '',
                    collected_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_collected_posts_run_fingerprint
                    ON collected_posts(run_id, detail_fingerprint)
                    WHERE detail_fingerprint <> '';
                CREATE UNIQUE INDEX IF NOT EXISTS idx_collected_posts_run_url_title
                    ON collected_posts(run_id, url, title)
                    WHERE detail_fingerprint = '';

                CREATE TABLE IF NOT EXISTS collected_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    run_id TEXT NOT NULL,
                    commenter TEXT NOT NULL,
                    content TEXT NOT NULL,
                    like_count TEXT NOT NULL DEFAULT '',
                    comment_rank TEXT NOT NULL DEFAULT '',
                    collected_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_collected_comments_run_post_content
                    ON collected_comments(run_id, post_id, commenter, content);

                CREATE TABLE IF NOT EXISTS media_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    post_id INTEGER,
                    path TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    sha256 TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_media_assets_run_post_path
                    ON media_assets(run_id, post_id, path, asset_type);

                CREATE TABLE IF NOT EXISTS evidences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_evidences_run_path_scope
                    ON evidences(run_id, evidence_type, path, scope);
                """
            )
            self._ensure_column(conn, "raw_items", "parent_url", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "raw_items", "author", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "raw_items", "commenter", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "raw_items", "like_count", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "raw_items", "comment_rank", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "collection_runs", "completed_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "collection_runs", "failed_reason", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "collected_posts", "comment_count", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "collected_posts", "detail_fingerprint", "TEXT NOT NULL DEFAULT ''")

    def create_collection_run(self, run: CollectionRun) -> str:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO collection_runs (
                    run_id, platform, keyword, profile, status, progress, current_step,
                    max_posts, max_comments_per_post, created_at, updated_at, completed_at, failed_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.platform,
                    run.keyword,
                    run.profile,
                    run.status,
                    run.progress,
                    run.current_step,
                    run.max_posts,
                    run.max_comments_per_post,
                    run.created_at,
                    run.updated_at,
                    run.completed_at,
                    run.failed_reason,
                ),
            )
        return run.run_id

    def update_collection_run(
        self,
        run_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        current_step: Optional[str] = None,
        failed_reason: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        updates: List[str] = ["updated_at = ?"]
        params: List[object] = [utc_now_iso()]
        fields = {
            "status": status,
            "progress": progress,
            "current_step": current_step,
            "failed_reason": failed_reason,
            "completed_at": completed_at,
        }
        for column, value in fields.items():
            if value is not None:
                updates.append(f"{column} = ?")
                params.append(value)
        params.append(run_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE collection_runs SET {', '.join(updates)} WHERE run_id = ?",
                params,
            )

    def append_collection_event(self, event: CollectionEvent) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO collection_events (
                    run_id, sequence, scope, event, message, level, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.run_id,
                    event.sequence,
                    event.scope,
                    event.event,
                    event.message,
                    event.level,
                    event.payload_json,
                    event.created_at,
                ),
            )
            if cursor.rowcount:
                return int(cursor.lastrowid)
            row = conn.execute(
                """
                SELECT id FROM collection_events
                WHERE run_id = ? AND sequence = ? AND event = ? AND message = ?
                """,
                (event.run_id, event.sequence, event.event, event.message),
            ).fetchone()
            return int(row["id"])

    def save_collected_post(self, post: CollectedPost) -> int:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO collected_posts (
                    run_id, platform, keyword, title, content, url, author, published_at,
                    like_count, comment_count, detail_fingerprint, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    post.run_id,
                    post.platform,
                    post.keyword,
                    post.title,
                    post.content,
                    post.url,
                    post.author,
                    post.published_at,
                    post.like_count,
                    post.comment_count,
                    post.detail_fingerprint,
                    post.collected_at,
                ),
            )
            if post.detail_fingerprint:
                row = conn.execute(
                    """
                    SELECT id FROM collected_posts
                    WHERE run_id = ? AND detail_fingerprint = ?
                    """,
                    (post.run_id, post.detail_fingerprint),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id FROM collected_posts
                    WHERE run_id = ? AND url = ? AND title = ? AND detail_fingerprint = ''
                    """,
                    (post.run_id, post.url, post.title),
                ).fetchone()
            return int(row["id"])

    def save_collected_comment(self, comment: CollectedComment) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO collected_comments (
                    post_id, run_id, commenter, content, like_count, comment_rank, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comment.post_id,
                    comment.run_id,
                    comment.commenter,
                    comment.content,
                    comment.like_count,
                    comment.comment_rank,
                    comment.collected_at,
                ),
            )
            if cursor.rowcount:
                return int(cursor.lastrowid)
            row = conn.execute(
                """
                SELECT id FROM collected_comments
                WHERE post_id = ? AND run_id = ? AND commenter = ? AND content = ?
                """,
                (comment.post_id, comment.run_id, comment.commenter, comment.content),
            ).fetchone()
            return int(row["id"])

    def save_media_asset(self, asset: MediaAsset) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO media_assets (
                    run_id, post_id, path, asset_type, url, sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.run_id,
                    asset.post_id,
                    asset.path,
                    asset.asset_type,
                    asset.url,
                    asset.sha256,
                    asset.created_at,
                ),
            )
            if cursor.rowcount:
                return int(cursor.lastrowid)
            if asset.post_id is None:
                row = conn.execute(
                    """
                    SELECT id FROM media_assets
                    WHERE run_id = ? AND post_id IS NULL AND path = ? AND asset_type = ?
                    """,
                    (asset.run_id, asset.path, asset.asset_type),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id FROM media_assets
                    WHERE run_id = ? AND post_id = ? AND path = ? AND asset_type = ?
                    """,
                    (asset.run_id, asset.post_id, asset.path, asset.asset_type),
                ).fetchone()
            return int(row["id"])

    def save_evidence(self, evidence: Evidence) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO evidences (
                    run_id, evidence_type, path, scope, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.run_id,
                    evidence.evidence_type,
                    evidence.path,
                    evidence.scope,
                    evidence.payload_json,
                    evidence.created_at,
                ),
            )
            if cursor.rowcount:
                return int(cursor.lastrowid)
            row = conn.execute(
                """
                SELECT id FROM evidences
                WHERE run_id = ? AND evidence_type = ? AND path = ? AND scope = ?
                """,
                (evidence.run_id, evidence.evidence_type, evidence.path, evidence.scope),
            ).fetchone()
            return int(row["id"])

    def list_collection_runs(self, limit: Optional[int] = None) -> List[CollectionRun]:
        sql = "SELECT * FROM collection_runs ORDER BY id DESC"
        params: List[object] = []
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_collection_run(row) for row in rows]

    def get_collection_run(self, run_id: str) -> Optional[CollectionRun]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM collection_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_collection_run(row)

    def list_collection_events(self, run_id: str) -> List[CollectionEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM collection_events
                WHERE run_id = ?
                ORDER BY sequence ASC, id ASC
                """,
                (run_id,),
            ).fetchall()
        return [self._row_to_collection_event(row) for row in rows]

    def list_collected_posts(
        self,
        run_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[CollectedPost]:
        sql = "SELECT * FROM collected_posts"
        params: List[object] = []
        if run_id:
            sql += " WHERE run_id = ?"
            params.append(run_id)
        sql += " ORDER BY id ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_collected_post(row) for row in rows]

    def get_collected_post(self, post_id: int) -> Optional[CollectedPost]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM collected_posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_collected_post(row)

    def list_collected_comments(
        self,
        run_id: Optional[str] = None,
        post_id: Optional[int] = None,
    ) -> List[CollectedComment]:
        sql = "SELECT * FROM collected_comments"
        params: List[object] = []
        clauses: List[str] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if post_id is not None:
            clauses.append("post_id = ?")
            params.append(post_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id ASC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_collected_comment(row) for row in rows]

    def list_media_assets(self, run_id: str) -> List[MediaAsset]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM media_assets WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return [self._row_to_media_asset(row) for row in rows]

    def list_evidences(self, run_id: str) -> List[Evidence]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evidences WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def collector_dashboard(self) -> Dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_runs,
                    SUM(CASE WHEN status = 'manual_action_required' THEN 1 ELSE 0 END) AS waiting_manual_runs,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_runs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_runs
                FROM collection_runs
                """
            ).fetchone()
            posts_row = conn.execute("SELECT COUNT(*) AS total_posts FROM collected_posts").fetchone()
        return {
            "total_runs": int(row["total_runs"] or 0),
            "running_runs": int(row["running_runs"] or 0),
            "waiting_manual_runs": int(row["waiting_manual_runs"] or 0),
            "failed_runs": int(row["failed_runs"] or 0),
            "completed_runs": int(row["completed_runs"] or 0),
            "total_posts": int(posts_row["total_posts"] or 0),
        }

    def upsert_raw_item(self, item: RawItem) -> int:
        source_hash = self._source_hash(item)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO raw_items (
                    source_hash, platform, keyword, source_type, title, content, url,
                    parent_url, author, commenter, like_count, comment_rank,
                    published_at, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_hash,
                    item.platform,
                    item.keyword,
                    item.source_type,
                    item.title,
                    item.content,
                    item.url,
                    item.parent_url,
                    item.author,
                    item.commenter,
                    item.like_count,
                    item.comment_rank,
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
                raw_items.parent_url,
                raw_items.author,
                raw_items.commenter,
                raw_items.like_count,
                raw_items.comment_rank,
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
            parent_url=row["parent_url"],
            author=row["author"],
            commenter=row["commenter"],
            like_count=row["like_count"],
            comment_rank=row["comment_rank"],
            published_at=row["published_at"],
            collected_at=row["collected_at"],
        )

    def _row_to_collection_run(self, row: sqlite3.Row) -> CollectionRun:
        return CollectionRun(
            run_id=row["run_id"],
            platform=row["platform"],
            keyword=row["keyword"],
            profile=row["profile"],
            status=row["status"],
            progress=int(row["progress"]),
            current_step=row["current_step"],
            max_posts=int(row["max_posts"]),
            max_comments_per_post=int(row["max_comments_per_post"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            failed_reason=row["failed_reason"],
        )

    def _row_to_collection_event(self, row: sqlite3.Row) -> CollectionEvent:
        return CollectionEvent(
            event_id=int(row["id"]),
            run_id=row["run_id"],
            sequence=int(row["sequence"]),
            scope=row["scope"],
            event=row["event"],
            message=row["message"],
            level=row["level"],
            payload_json=row["payload_json"],
            created_at=row["created_at"],
        )

    def _row_to_collected_post(self, row: sqlite3.Row) -> CollectedPost:
        return CollectedPost(
            post_id=int(row["id"]),
            run_id=row["run_id"],
            platform=row["platform"],
            keyword=row["keyword"],
            title=row["title"],
            content=row["content"],
            url=row["url"],
            author=row["author"],
            published_at=row["published_at"],
            like_count=row["like_count"],
            comment_count=row["comment_count"],
            detail_fingerprint=row["detail_fingerprint"],
            collected_at=row["collected_at"],
        )

    def _row_to_collected_comment(self, row: sqlite3.Row) -> CollectedComment:
        return CollectedComment(
            comment_id=int(row["id"]),
            post_id=int(row["post_id"]),
            run_id=row["run_id"],
            commenter=row["commenter"],
            content=row["content"],
            like_count=row["like_count"],
            comment_rank=row["comment_rank"],
            collected_at=row["collected_at"],
        )

    def _row_to_media_asset(self, row: sqlite3.Row) -> MediaAsset:
        return MediaAsset(
            asset_id=int(row["id"]),
            run_id=row["run_id"],
            post_id=row["post_id"],
            path=row["path"],
            asset_type=row["asset_type"],
            url=row["url"],
            sha256=row["sha256"],
            created_at=row["created_at"],
        )

    def _row_to_evidence(self, row: sqlite3.Row) -> Evidence:
        return Evidence(
            evidence_id=int(row["id"]),
            run_id=row["run_id"],
            evidence_type=row["evidence_type"],
            path=row["path"],
            scope=row["scope"],
            payload_json=row["payload_json"],
            created_at=row["created_at"],
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

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
