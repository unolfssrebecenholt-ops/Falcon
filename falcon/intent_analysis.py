import json
from typing import Dict, Iterable, List, Optional

from .db import FalconRepository
from .llm import GPT55Client
from .models import IntentAnalysisMatch, IntentAnalysisProbe, utc_now_iso


class IntentAnalysisService:
    """GPT-5.5 powered semantic probe analysis over collected posts."""

    MAX_POSTS = 40
    MAX_COMMENTS_PER_POST = 20
    MAX_TEXT_CHARS = 900

    def __init__(self, repo: FalconRepository, client: Optional[GPT55Client] = None):
        self.repo = repo
        self.client = client or GPT55Client.from_env()
        if hasattr(self.client, "model"):
            self.client.model = "gpt-5.5"

    def generate_probes(self, task_id: int) -> List[IntentAnalysisProbe]:
        task = self.repo.get_intent_analysis_task(task_id)
        if task is None:
            raise ValueError("Intent analysis task not found")
        try:
            self._require_configured()
            payload = self.client.complete_json(
                system_prompt=(
                    "你是 Falcon 的意向探针规划器。只返回 JSON。"
                    "根据用户输入生成 5 个语义探针，用于判断采集帖子和评论是否符合分析意图。"
                    "必须生成 5 个探针，不要 markdown。"
                ),
                user_prompt=json.dumps(
                    {
                        "platform": task.platform,
                        "user_intent": task.user_intent,
                        "required_schema": {
                            "probes": [
                                {
                                    "title": "string",
                                    "description": "string",
                                    "positive_signals": ["string"],
                                    "negative_signals": ["string"],
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
            )
            specs = self._validate_probe_payload(payload)
            probes: List[IntentAnalysisProbe] = []
            for index, spec in enumerate(specs, start=1):
                probe = IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key=f"probe-{index}",
                    title=spec["title"],
                    description=spec["description"],
                    positive_signals="\n".join(spec["positive_signals"]),
                    negative_signals="\n".join(spec["negative_signals"]),
                    sort_order=index,
                    enabled=True,
                    model_name="gpt-5.5",
                )
                probe_id = self.repo.save_intent_analysis_probe(probe)
                saved = self.repo.get_intent_analysis_probe(probe_id)
                if saved is not None:
                    probes.append(saved)
            self.repo.update_intent_analysis_task(task_id, status="probes_ready", failed_reason="")
            return probes
        except Exception as exc:
            self.repo.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
            raise

    def execute_task(self, task_id: int) -> List[IntentAnalysisMatch]:
        task = self.repo.get_intent_analysis_task(task_id)
        if task is None:
            raise ValueError("Intent analysis task not found")
        try:
            probes = self.repo.list_intent_analysis_probes(task_id, enabled_only=True)
            if not 1 <= len(probes) <= 12:
                raise ValueError("Intent analysis requires 1 to 12 enabled probes")
            package = self.repo.build_intent_analysis_package(task_id)
            if not package:
                raise ValueError("Intent analysis data package has no collected posts")
            self._require_configured()
            payload = self.client.complete_json(
                system_prompt=(
                    "你是 Falcon 的 GPT-5.5 意向语义分析器。只返回 JSON。"
                    "请根据探针对帖子标题、正文和评论做语义匹配，返回帖子级和评论级证据。"
                    "帖子级命中必须给出 summary，不要生成执行动作，不要创建回复或私信。"
                ),
                user_prompt=json.dumps(
                    {
                        "platform": task.platform,
                        "user_intent": task.user_intent,
                        "probes": [self._probe_payload(probe) for probe in probes],
                        "posts": self._trimmed_package(package),
                        "required_schema": {
                            "matches": [
                                {
                                    "probe_key": "probe-1",
                                    "post_id": 1,
                                    "comment_id": None,
                                    "level": "post",
                                    "score": 0,
                                    "reason": "string",
                                    "excerpt": "string",
                                    "summary": "string",
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
            )
            matches = self._validate_match_payload(task_id, payload, probes, package)
            self.repo.clear_intent_analysis_matches(task_id)
            saved_matches: List[IntentAnalysisMatch] = []
            for match in matches:
                match_id = self.repo.save_intent_analysis_match(match)
                saved = next(
                    (item for item in self.repo.list_intent_analysis_matches(task_id) if item.match_id == match_id),
                    None,
                )
                if saved is not None:
                    saved_matches.append(saved)
            self.repo.update_intent_analysis_task(task_id, status="completed", failed_reason="", completed_at=utc_now_iso())
            return saved_matches
        except Exception as exc:
            self.repo.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
            raise

    def _require_configured(self) -> None:
        if not self.client or not self.client.is_configured():
            raise RuntimeError("GPT intent probe analysis requires FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY")

    def _validate_probe_payload(self, payload: Dict[str, object]) -> List[Dict[str, object]]:
        probes = payload.get("probes")
        if not isinstance(probes, list) or len(probes) != 5:
            raise ValueError("GPT probe generation must return exactly 5 probes")
        normalized = []
        for item in probes:
            if not isinstance(item, dict):
                raise ValueError("Each probe must be a JSON object")
            title = str(item.get("title") or "").strip()
            description = str(item.get("description") or "").strip()
            positive = self._signal_list(item.get("positive_signals"), "positive_signals")
            negative = self._signal_list(item.get("negative_signals"), "negative_signals")
            if not title or not description:
                raise ValueError("Probe title and description are required")
            normalized.append(
                {
                    "title": title,
                    "description": description,
                    "positive_signals": positive,
                    "negative_signals": negative,
                }
            )
        return normalized

    def _signal_list(self, value: object, field_name: str) -> List[str]:
        if not isinstance(value, list):
            raise ValueError(f"Probe {field_name} must be a list")
        signals = [str(item).strip() for item in value if str(item).strip()]
        if not signals:
            raise ValueError(f"Probe {field_name} must not be empty")
        return signals

    def _probe_payload(self, probe: IntentAnalysisProbe) -> Dict[str, object]:
        return {
            "probe_key": probe.probe_key,
            "title": probe.title,
            "description": probe.description,
            "positive_signals": [line.strip() for line in probe.positive_signals.splitlines() if line.strip()],
            "negative_signals": [line.strip() for line in probe.negative_signals.splitlines() if line.strip()],
        }

    def _trimmed_package(self, package: List[Dict[str, object]]) -> List[Dict[str, object]]:
        trimmed = []
        for post in package[: self.MAX_POSTS]:
            comments = post.get("comments") if isinstance(post.get("comments"), list) else []
            trimmed.append(
                {
                    "post_id": post.get("post_id"),
                    "run_id": post.get("run_id"),
                    "keyword": post.get("keyword"),
                    "title": self._truncate(post.get("title")),
                    "content": self._truncate(post.get("content")),
                    "comments": [
                        {
                            "comment_id": comment.get("comment_id"),
                            "commenter": comment.get("commenter"),
                            "content": self._truncate(comment.get("content")),
                        }
                        for comment in comments[: self.MAX_COMMENTS_PER_POST]
                        if isinstance(comment, dict)
                    ],
                }
            )
        return trimmed

    def _validate_match_payload(
        self,
        task_id: int,
        payload: Dict[str, object],
        probes: List[IntentAnalysisProbe],
        package: List[Dict[str, object]],
    ) -> List[IntentAnalysisMatch]:
        raw_matches = payload.get("matches")
        if not isinstance(raw_matches, list):
            raise ValueError("GPT analysis must return a matches list")
        probes_by_key = {probe.probe_key: probe for probe in probes}
        probes_by_title = {probe.title: probe for probe in probes}
        post_ids = {int(post["post_id"]) for post in package if post.get("post_id") is not None}
        comment_post_ids = {}
        for post in package:
            if post.get("post_id") is None:
                continue
            package_post_id = int(post["post_id"])
            for comment in post.get("comments") or []:
                if isinstance(comment, dict) and comment.get("comment_id") is not None:
                    comment_post_ids[int(comment["comment_id"])] = package_post_id
        matches: List[IntentAnalysisMatch] = []
        for item in raw_matches:
            if not isinstance(item, dict):
                raise ValueError("Each match must be a JSON object")
            probe = self._match_probe(item, probes_by_key, probes_by_title)
            level = str(item.get("level") or item.get("source_type") or "").strip()
            if level not in {"post", "comment"}:
                raise ValueError("Match level must be post or comment")
            post_id = int(item.get("post_id") or 0)
            if post_id not in post_ids:
                raise ValueError(f"Match post_id is not in the supplied package: {post_id}")
            raw_comment_id = item.get("comment_id")
            comment_id = int(raw_comment_id) if raw_comment_id not in (None, "") else None
            if level == "post" and comment_id is not None:
                raise ValueError("Post-level matches must not include comment_id")
            if level == "comment" and comment_post_ids.get(comment_id) != post_id:
                raise ValueError(f"Match comment_id is not in the supplied package: {comment_id}")
            score = int(item.get("score") if item.get("score") is not None else item.get("confidence", 0))
            if score < 0 or score > 100:
                raise ValueError("Match score must be between 0 and 100")
            reason = str(item.get("reason") or "").strip()
            excerpt = str(item.get("excerpt") or item.get("evidence") or "").strip()
            summary = str(item.get("summary") or item.get("post_summary") or "").strip()
            if level == "post" and not summary:
                summary = reason
            if not reason or not excerpt:
                raise ValueError("Match reason and excerpt are required")
            matches.append(
                IntentAnalysisMatch(
                    task_id=task_id,
                    probe_id=probe.probe_id or 0,
                    probe_key=probe.probe_key,
                    probe_title=probe.title,
                    post_id=post_id,
                    comment_id=comment_id,
                    level=level,
                    score=score,
                    reason=reason,
                    excerpt=excerpt,
                    summary=summary,
                )
            )
        return matches

    def _match_probe(
        self,
        item: Dict[str, object],
        probes_by_key: Dict[str, IntentAnalysisProbe],
        probes_by_title: Dict[str, IntentAnalysisProbe],
    ) -> IntentAnalysisProbe:
        key = str(item.get("probe_key") or "").strip()
        title = str(item.get("probe_title") or "").strip()
        probe = probes_by_key.get(key) or probes_by_title.get(title)
        if probe is None:
            raise ValueError("Match probe does not reference an enabled probe")
        return probe

    def _truncate(self, value: object) -> str:
        text = str(value or "").strip()
        if len(text) <= self.MAX_TEXT_CHARS:
            return text
        return text[: self.MAX_TEXT_CHARS] + "..."
