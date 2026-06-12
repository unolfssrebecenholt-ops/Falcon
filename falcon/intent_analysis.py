import base64
import json
import mimetypes
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

from .db import FalconRepository
from .llm import GPT55Client, GPTHTTPError, GPTResponseParseError
from .models import IntentAnalysisMatch, IntentAnalysisProbe, utc_now_iso


class IntentAnalysisService:
    """GPT-5.5 powered semantic probe analysis over collected posts."""

    POSTS_PER_BATCH = 2
    MAX_COMMENTS_PER_POST = 12
    MAX_TEXT_CHARS = 700
    MAX_IMAGES_PER_POST = 4

    def __init__(self, repo: FalconRepository, client: Optional[GPT55Client] = None):
        self.repo = repo
        self.client = client or GPT55Client.from_env()
        if hasattr(self.client, "model"):
            self.client.model = "gpt-5.5"
        self.log_root = Path.cwd() / "runtime" / "analysis"

    def generate_probes(self, task_id: int) -> List[IntentAnalysisProbe]:
        probes: List[IntentAnalysisProbe] = []
        for event in self.generate_probes_stream(task_id):
            if event.get("type") == "done":
                event_probes = event.get("probes")
                if isinstance(event_probes, list):
                    probes = event_probes
        return probes

    def generate_probes_stream(self, task_id: int) -> Iterator[Dict[str, object]]:
        task = self.repo.get_intent_analysis_task(task_id)
        if task is None:
            raise ValueError("Intent analysis task not found")
        try:
            self._require_configured()
            self.repo.update_intent_analysis_task(task_id, status="generating_probes", failed_reason="")
            system_prompt, user_prompt = self._probe_generation_prompts(task)
            yield {
                "type": "status",
                "message": "已连接 GPT-5.5，正在生成语义探针。",
                "status": "generating_probes",
                "progress": 48,
            }
            payload: Optional[Dict[str, object]] = None
            if hasattr(self.client, "stream_json"):
                for event in self.client.stream_json(system_prompt, user_prompt):
                    if event.get("type") == "delta":
                        yield {"type": "delta", "text": str(event.get("text") or "")}
                    elif event.get("type") == "done":
                        event_payload = event.get("payload")
                        if not isinstance(event_payload, dict):
                            raise ValueError("GPT probe generation did not return a JSON object")
                        payload = event_payload
            else:
                payload = self.client.complete_json(system_prompt, user_prompt)

            if payload is None:
                raise ValueError("GPT probe generation did not return a JSON object")
            yield {"type": "status", "message": "正在校验 5 个探针并写入本地数据库。", "progress": 92}
            probes = self._save_probe_payload(task_id, payload)
            self.repo.update_intent_analysis_task(task_id, status="probes_ready", failed_reason="")
            yield {
                "type": "done",
                "message": "5 个探针已生成，可以继续编辑或执行分析。",
                "probes": probes,
                "count": len(probes),
            }
        except Exception as exc:
            self.repo.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
            raise

    def _probe_generation_prompts(self, task: object) -> tuple[str, str]:
        return (
            (
                "你是 Falcon 的意向探针规划器。只返回 JSON。"
                "根据用户输入生成 5 个语义探针，用于判断采集帖子和评论是否符合分析意图。"
                "必须生成 5 个探针，不要 markdown。"
            ),
            json.dumps(
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

    def _save_probe_payload(self, task_id: int, payload: Dict[str, object]) -> List[IntentAnalysisProbe]:
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
        return probes

    def execute_task(self, task_id: int) -> List[IntentAnalysisMatch]:
        task = self.repo.get_intent_analysis_task(task_id)
        if task is None:
            raise ValueError("Intent analysis task not found")
        try:
            probes = self.repo.list_intent_analysis_probes(task_id)
            if not 1 <= len(probes) <= 12:
                raise ValueError("Intent analysis requires 1 to 12 probes")
            package = self.repo.build_intent_analysis_package(task_id)
            if not package:
                raise ValueError("Intent analysis data package has no collected posts")
            self._require_configured()
            batches = list(self._post_batches(package))
            matches: List[IntentAnalysisMatch] = []
            for batch_index, batch in enumerate(batches, start=1):
                supplied_package: List[Dict[str, object]] = []
                image_inputs: List[Dict[str, str]] = []
                try:
                    image_inputs = self._image_inputs(batch)
                    supplied_package = self._trimmed_package(
                        batch,
                        image_asset_ids={int(image["asset_id"]) for image in image_inputs if image.get("asset_id")},
                    )
                    self._write_execution_log(
                        task_id=task_id,
                        batch_index=batch_index,
                        batch_count=len(batches),
                        event="request",
                        payload={
                            "task": {
                                "task_id": task_id,
                                "platform": task.platform,
                                "user_intent": task.user_intent,
                                "model_name": getattr(self.client, "model", "gpt-5.5"),
                            },
                            "batch": self._batch_log_summary(supplied_package, image_inputs),
                            "probes": [self._probe_payload(probe) for probe in probes],
                            "posts": supplied_package,
                        },
                    )
                    payload = self._execute_analysis_request(task, probes, supplied_package, image_inputs)
                    batch_matches = self._validate_match_payload(task_id, payload, probes, supplied_package)
                    self._write_execution_log(
                        task_id=task_id,
                        batch_index=batch_index,
                        batch_count=len(batches),
                        event="response",
                        payload={
                            "batch": self._batch_log_summary(supplied_package, image_inputs),
                            "match_count": len(batch_matches),
                            "response": payload,
                        },
                    )
                    matches.extend(batch_matches)
                except Exception as exc:
                    failure_payload = {
                        "batch": self._batch_log_summary(supplied_package, image_inputs),
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                    parse_error = self._parse_error_from_exception(exc)
                    if isinstance(parse_error, GPTResponseParseError):
                        failure_payload["raw_response"] = parse_error.content
                    http_error = self._http_error_from_exception(exc)
                    if isinstance(http_error, GPTHTTPError):
                        failure_payload["http_status"] = http_error.status
                        failure_payload["http_reason"] = http_error.reason
                        if http_error.content:
                            failure_payload["raw_response"] = http_error.content[:4000]
                    self._write_execution_log(
                        task_id=task_id,
                        batch_index=batch_index,
                        batch_count=len(batches),
                        event="error",
                        payload=failure_payload,
                    )
                    message = f"第 {batch_index}/{len(batches)} 批分析失败：{self._relay_error_hint(exc)}"
                    if isinstance(exc, ValueError):
                        raise ValueError(message) from exc
                    raise RuntimeError(message) from exc
            self.repo.clear_intent_analysis_matches(task_id)
            for match in matches:
                self.repo.save_intent_analysis_match(match)
            saved_matches = self.repo.list_intent_analysis_matches(task_id)
            self.repo.update_intent_analysis_task(task_id, status="completed", failed_reason="", completed_at=utc_now_iso())
            return saved_matches
        except Exception as exc:
            self.repo.update_intent_analysis_task(task_id, status="failed", failed_reason=str(exc))
            raise

    def _post_batches(self, package: List[Dict[str, object]]) -> Iterator[List[Dict[str, object]]]:
        size = max(1, int(self.POSTS_PER_BATCH))
        for start in range(0, len(package), size):
            yield package[start : start + size]

    def _execute_analysis_request(
        self,
        task: object,
        probes: List[IntentAnalysisProbe],
        supplied_package: List[Dict[str, object]],
        images: List[Dict[str, str]],
    ) -> Dict[str, object]:
        system_prompt = (
            "你是 Falcon 的 GPT-5.5 意向语义分析器。只返回 JSON。"
            "请根据探针对帖子标题、正文、图片和评论做语义匹配，返回帖子内容、帖子图片和帖子评论证据。"
            "level 只能是 post、image、comment。"
            "帖子内容命中必须给出 summary，图片命中必须引用输入里存在的 asset_id。"
            "score 必须是 0 到 100 的整数。"
            "只输出一个合法 JSON object，根字段只能包含 matches；不要 markdown、注释、尾随逗号或 JSON 之外的文字。"
            "不要生成执行动作，不要创建回复或私信。"
        )
        user_prompt = json.dumps(
            {
                "platform": task.platform,
                "user_intent": task.user_intent,
                "probes": [self._probe_payload(probe) for probe in probes],
                "posts": supplied_package,
                "required_schema": {
                    "matches": [
                        {
                            "probe_key": "probe-1",
                            "post_id": 1,
                            "comment_id": None,
                            "asset_id": None,
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
        )
        if images:
            if not hasattr(self.client, "complete_json_multimodal"):
                raise RuntimeError("GPT relay does not support multimodal image input")
            return self.client.complete_json_multimodal(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                images=images,
            )
        return self.client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)

    def _require_configured(self) -> None:
        if not self.client or not self.client.is_configured():
            raise RuntimeError("GPT intent probe analysis requires FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY")

    def _relay_error_hint(self, exc: Exception) -> str:
        http_error = self._http_error_from_exception(exc)
        endpoint = str(getattr(self.client, "endpoint", "") or "")
        if (
            isinstance(http_error, GPTHTTPError)
            and http_error.status == 502
            and endpoint.rstrip("/").endswith("/responses")
        ):
            return f"{exc}；当前 relay 的 Responses JSON/stream 通道异常，可在模型配置切换到 Chat Completions 后重试。"
        return str(exc)

    def _write_execution_log(
        self,
        task_id: int,
        batch_index: int,
        batch_count: int,
        event: str,
        payload: Dict[str, object],
    ) -> None:
        log_dir = self.log_root / f"task-{task_id}"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_payload = {
            "event": event,
            "task_id": task_id,
            "batch_index": batch_index,
            "batch_count": batch_count,
            "created_at": utc_now_iso(),
            **payload,
        }
        log_path = log_dir / f"batch-{batch_index:02d}-{event}.json"
        try:
            log_path.write_text(json.dumps(log_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _parse_error_from_exception(self, exc: BaseException) -> Optional[GPTResponseParseError]:
        visited = set()
        current: Optional[BaseException] = exc
        while current is not None and id(current) not in visited:
            if isinstance(current, GPTResponseParseError):
                return current
            visited.add(id(current))
            current = current.__cause__ or current.__context__
        return None

    def _http_error_from_exception(self, exc: BaseException) -> Optional[GPTHTTPError]:
        visited = set()
        current: Optional[BaseException] = exc
        while current is not None and id(current) not in visited:
            if isinstance(current, GPTHTTPError):
                return current
            visited.add(id(current))
            current = current.__cause__ or current.__context__
        return None

    def _batch_log_summary(
        self,
        supplied_package: List[Dict[str, object]],
        image_inputs: List[Dict[str, str]],
    ) -> Dict[str, object]:
        return {
            "post_count": len(supplied_package),
            "comment_count": sum(len(post.get("comments") or []) for post in supplied_package),
            "image_count": len(image_inputs),
            "post_ids": [post.get("post_id") for post in supplied_package],
            "titles": [
                {
                    "post_id": post.get("post_id"),
                    "title": str(post.get("title") or "")[:120],
                }
                for post in supplied_package
            ],
        }

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

    def _trimmed_package(
        self,
        package: List[Dict[str, object]],
        image_asset_ids: Optional[set[int]] = None,
    ) -> List[Dict[str, object]]:
        trimmed = []
        for post in package:
            comments = post.get("comments") if isinstance(post.get("comments"), list) else []
            images = post.get("images") if isinstance(post.get("images"), list) else []
            if image_asset_ids is not None:
                images = [
                    image
                    for image in images
                    if isinstance(image, dict)
                    and image.get("asset_id") is not None
                    and int(image["asset_id"]) in image_asset_ids
                ]
            trimmed.append(
                {
                    "post_id": post.get("post_id"),
                    "run_id": post.get("run_id"),
                    "keyword": post.get("keyword"),
                    "title": self._truncate(post.get("title")),
                    "content": self._truncate(post.get("content")),
                    "images": [
                        {
                            "asset_id": image.get("asset_id"),
                            "asset_type": image.get("asset_type"),
                            "url": image.get("url"),
                            "sha256": image.get("sha256"),
                        }
                        for image in images[: self.MAX_IMAGES_PER_POST]
                        if isinstance(image, dict)
                    ],
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

    def _image_inputs(self, package: List[Dict[str, object]]) -> List[Dict[str, str]]:
        images: List[Dict[str, str]] = []
        for post in package:
            post_images = post.get("images") if isinstance(post.get("images"), list) else []
            for image in post_images[: self.MAX_IMAGES_PER_POST]:
                if not isinstance(image, dict) or image.get("asset_id") is None:
                    continue
                path = self._existing_image_path(image.get("path"))
                if path is None:
                    continue
                mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
                if not mime_type.startswith("image/"):
                    continue
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                images.append(
                    {
                        "asset_id": str(image.get("asset_id")),
                        "post_id": str(post.get("post_id") or ""),
                        "mime_type": mime_type,
                        "data_url": f"data:{mime_type};base64,{encoded}",
                    }
                )
        return images

    def _existing_image_path(self, value: object) -> Optional[Path]:
        path_text = str(value or "").strip()
        if not path_text:
            return None
        path = Path(path_text)
        if not path.is_absolute():
            candidates = [
                Path.cwd() / path,
                self.repo.db_path.parent / path,
                Path(__file__).resolve().parents[1] / path,
            ]
        else:
            candidates = [path]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

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
        asset_post_ids = {}
        for post in package:
            if post.get("post_id") is None:
                continue
            package_post_id = int(post["post_id"])
            for comment in post.get("comments") or []:
                if isinstance(comment, dict) and comment.get("comment_id") is not None:
                    comment_post_ids[int(comment["comment_id"])] = package_post_id
            for image in (post.get("images") or [])[: self.MAX_IMAGES_PER_POST]:
                if isinstance(image, dict) and image.get("asset_id") is not None:
                    asset_post_ids[int(image["asset_id"])] = package_post_id
        matches: List[IntentAnalysisMatch] = []
        for item in raw_matches:
            if not isinstance(item, dict):
                raise ValueError("Each match must be a JSON object")
            probe = self._match_probe(item, probes_by_key, probes_by_title)
            level = str(item.get("level") or item.get("source_type") or "").strip()
            if level not in {"post", "comment", "image"}:
                raise ValueError("Match level must be post, image, or comment")
            post_id = int(item.get("post_id") or 0)
            if post_id not in post_ids:
                raise ValueError(f"Match post_id is not in the supplied package: {post_id}")
            raw_comment_id = item.get("comment_id")
            comment_id = int(raw_comment_id) if raw_comment_id not in (None, "") else None
            raw_asset_id = item.get("asset_id")
            asset_id = int(raw_asset_id) if raw_asset_id not in (None, "") else None
            if level == "post" and (comment_id is not None or asset_id is not None):
                raise ValueError("Post-level matches must not include comment_id or asset_id")
            if level == "comment" and asset_id is not None:
                raise ValueError("Comment-level matches must not include asset_id")
            if level == "comment" and comment_post_ids.get(comment_id) != post_id:
                raise ValueError(f"Match comment_id is not in the supplied package: {comment_id}")
            if level == "image" and comment_id is not None:
                raise ValueError("Image-level matches must not include comment_id")
            if level == "image" and asset_post_ids.get(asset_id) != post_id:
                raise ValueError(f"Match asset_id is not in the supplied package: {asset_id}")
            score = self._normalize_score(item.get("score") if item.get("score") is not None else item.get("confidence", 0))
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
                    asset_id=asset_id,
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
            raise ValueError("Match probe does not reference a task probe")
        return probe

    def _truncate(self, value: object) -> str:
        text = str(value or "").strip()
        if len(text) <= self.MAX_TEXT_CHARS:
            return text
        return text[: self.MAX_TEXT_CHARS] + "..."

    def _normalize_score(self, value: object) -> int:
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0
        if 0 < score <= 1:
            score *= 100
        return round(score)
