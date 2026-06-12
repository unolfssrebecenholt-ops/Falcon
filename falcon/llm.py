import json
import os
from typing import BinaryIO, Callable, Dict, Iterator, List, Optional
import urllib.error
import urllib.request

from .config import DEFAULT_GPT_ENDPOINT, DEFAULT_GPT_MODEL, DEFAULT_GPT_TIMEOUT


class GPTResponseParseError(ValueError):
    def __init__(self, message: str, content: str):
        super().__init__(message)
        self.content = content


class GPTHTTPError(RuntimeError):
    def __init__(self, status: int, reason: str, content: str = ""):
        message = f"GPT relay 返回 HTTP {status}: {reason or 'request failed'}"
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.content = content


class GPT55Client:
    """OpenAI-compatible client for the user's GPT-5.5 relay."""

    def __init__(
        self,
        base_url: str = "",
        endpoint: str = "",
        api_key: str = "",
        model: str = "",
        timeout: int = int(DEFAULT_GPT_TIMEOUT),
        opener: Optional[Callable[..., BinaryIO]] = None,
    ):
        self.base_url = (base_url or os.getenv("FALCON_GPT_BASE_URL", "")).rstrip("/")
        self.endpoint = endpoint or os.getenv("FALCON_GPT_ENDPOINT", DEFAULT_GPT_ENDPOINT)
        self.api_key = api_key or os.getenv("FALCON_GPT_API_KEY", "")
        self.model = model or os.getenv("FALCON_GPT_MODEL", DEFAULT_GPT_MODEL)
        self.timeout = int(os.getenv("FALCON_GPT_TIMEOUT", str(timeout)))
        self.opener = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> "GPT55Client":
        return cls()

    def is_configured(self) -> bool:
        return bool(self.base_url and self.endpoint and self.api_key)

    def complete_json(self, system_prompt: str, user_prompt: str) -> Dict[str, object]:
        if not self.is_configured():
            raise RuntimeError("FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY are required")

        if self.endpoint.rstrip("/").endswith("/chat/completions"):
            return self._complete_json_chat_completions(system_prompt, user_prompt)
        payload = None
        for event in self.stream_json(system_prompt, user_prompt):
            if event.get("type") == "done":
                payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("GPT responses stream did not return a JSON object")
        return payload

    def complete_json_multimodal(
        self,
        system_prompt: str,
        user_prompt: str,
        images: List[Dict[str, str]],
    ) -> Dict[str, object]:
        if not self.is_configured():
            raise RuntimeError("FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY are required")

        if self.endpoint.rstrip("/").endswith("/chat/completions"):
            return self._complete_json_chat_completions_multimodal(system_prompt, user_prompt, images)
        body = {
            "model": self.model,
            "instructions": system_prompt,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        *self._responses_image_parts(images),
                    ],
                }
            ],
            "stream": True,
            "text": self._responses_json_text_format(),
        }
        request = self._request(body)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                content = self._read_responses_stream(response)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        return self._parse_json_object(content)

    def stream_json(self, system_prompt: str, user_prompt: str) -> Iterator[Dict[str, object]]:
        if not self.is_configured():
            raise RuntimeError("FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY are required")

        if self.endpoint.rstrip("/").endswith("/chat/completions"):
            body = self._chat_completions_body(system_prompt, user_prompt, stream=True)
            yield from self._stream_json_chat_completions(body)
            return

        body = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "stream": True,
            "text": self._responses_json_text_format(),
        }
        request = self._request(body)
        chunks = []
        done_text = ""
        try:
            with self.opener(request, timeout=self.timeout) as response:
                for text_event in self._iter_responses_text(response):
                    if text_event["type"] == "delta":
                        text = str(text_event.get("text") or "")
                        chunks.append(text)
                        yield {"type": "delta", "text": text}
                    elif text_event["type"] == "done_text":
                        done_text = str(text_event.get("text") or "")
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        content = done_text or "".join(chunks)
        if not content:
            raise ValueError("GPT responses stream did not contain output text")
        yield {"type": "done", "payload": self._parse_json_object(content)}

    def _complete_json_chat_completions(self, system_prompt: str, user_prompt: str) -> Dict[str, object]:
        body = self._chat_completions_body(system_prompt, user_prompt, stream=True)
        content = self._read_chat_completions_stream(body)
        return self._parse_json_object(content)

    def _complete_json_chat_completions_multimodal(
        self,
        system_prompt: str,
        user_prompt: str,
        images: List[Dict[str, str]],
    ) -> Dict[str, object]:
        body = self._chat_completions_body(
            system_prompt,
            [
                {"type": "text", "text": user_prompt},
                *self._chat_image_parts(images),
            ],
            stream=True,
        )
        content = self._read_chat_completions_stream(body)
        return self._parse_json_object(content)

    def _chat_completions_body(
        self,
        system_prompt: str,
        user_content: object,
        *,
        stream: bool,
    ) -> Dict[str, object]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "stream": stream,
        }
        return body

    def _read_chat_completions_stream(self, body: Dict[str, object]) -> str:
        chunks = []
        try:
            with self.opener(self._request(body), timeout=self.timeout) as response:
                for text_event in self._iter_chat_completions_text(response):
                    if text_event["type"] == "delta":
                        chunks.append(str(text_event.get("text") or ""))
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        content = "".join(chunks)
        if not content:
            raise ValueError("GPT chat completions stream did not contain output text")
        return content

    def _stream_json_chat_completions(self, body: Dict[str, object]) -> Iterator[Dict[str, object]]:
        chunks = []
        request = self._request(body)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                for text_event in self._iter_chat_completions_text(response):
                    if text_event["type"] == "delta":
                        text = str(text_event.get("text") or "")
                        chunks.append(text)
                        yield {"type": "delta", "text": text}
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        content = "".join(chunks)
        if not content:
            raise ValueError("GPT chat completions stream did not contain output text")
        yield {"type": "done", "payload": self._parse_json_object(content)}

    def _responses_image_parts(self, images: List[Dict[str, str]]) -> List[Dict[str, object]]:
        parts: List[Dict[str, object]] = []
        for index, image in enumerate(images, start=1):
            parts.append(
                {
                    "type": "input_text",
                    "text": (
                        f"Image input {index}: post_id={image.get('post_id', '')}, "
                        f"asset_id={image.get('asset_id', '')}."
                    ),
                }
            )
            parts.append(
                {
                    "type": "input_image",
                    "image_url": image["data_url"],
                }
            )
        return parts

    def _chat_image_parts(self, images: List[Dict[str, str]]) -> List[Dict[str, object]]:
        parts: List[Dict[str, object]] = []
        for index, image in enumerate(images, start=1):
            parts.append(
                {
                    "type": "text",
                    "text": (
                        f"Image input {index}: post_id={image.get('post_id', '')}, "
                        f"asset_id={image.get('asset_id', '')}."
                    ),
                }
            )
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image["data_url"]},
                }
            )
        return parts

    def _request(self, body: Dict[str, object]) -> urllib.request.Request:
        wants_stream = bool(body.get("stream"))
        return urllib.request.Request(
            self.base_url + self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if wants_stream else "application/json",
                "User-Agent": "Falcon/0.1 OpenAI-Compatible-Client",
            },
            method="POST",
        )

    def _responses_json_text_format(self) -> Dict[str, object]:
        return {"format": {"type": "json_object"}}

    def _http_error(self, exc: urllib.error.HTTPError) -> GPTHTTPError:
        try:
            content = exc.read().decode("utf-8", errors="replace")
        except Exception:
            content = ""
        return GPTHTTPError(exc.code, exc.reason, content)

    def _read_responses_stream(self, response: BinaryIO) -> str:
        chunks = []
        done_text = ""
        for text_event in self._iter_responses_text(response):
            if text_event["type"] == "delta":
                chunks.append(str(text_event.get("text") or ""))
            elif text_event["type"] == "done_text":
                done_text = str(text_event.get("text") or "")
        content = done_text or "".join(chunks)
        if not content:
            raise ValueError("GPT responses stream did not contain output text")
        return content

    def _iter_responses_text(self, response: BinaryIO) -> Iterator[Dict[str, str]]:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            event_type = str(event.get("type") or "")
            if event_type == "response.output_text.delta":
                yield {"type": "delta", "text": str(event.get("delta") or "")}
            elif event_type == "response.output_text.done":
                text = str(event.get("text") or "")
                if text:
                    yield {"type": "done_text", "text": text}
            elif event_type == "error":
                error = event.get("error") if isinstance(event.get("error"), dict) else {}
                message = error.get("message") if isinstance(error, dict) else ""
                raise RuntimeError(str(message or "GPT responses stream failed"))

    def _iter_chat_completions_text(self, response: BinaryIO) -> Iterator[Dict[str, str]]:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            if isinstance(event.get("error"), dict):
                message = str(event["error"].get("message") or "GPT chat completions stream failed")
                raise RuntimeError(message)
            choices = event.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            choice = choices[0] if isinstance(choices[0], dict) else {}
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            text = delta.get("content")
            if text:
                yield {"type": "delta", "text": str(text)}

    def _parse_json_object(self, content: str) -> Dict[str, object]:
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content.replace("json\n", "", 1).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("GPT response did not contain a JSON object")
        candidate = content[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise GPTResponseParseError(str(exc), candidate) from exc
