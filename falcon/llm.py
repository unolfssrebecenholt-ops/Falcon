import json
import os
import urllib.request
from typing import Dict


class GPT55Client:
    """OpenAI-compatible chat client for the user's GPT-5.5 relay."""

    def __init__(
        self,
        base_url: str = "",
        endpoint: str = "",
        api_key: str = "",
        model: str = "",
        timeout: int = 60,
    ):
        self.base_url = (base_url or os.getenv("FALCON_GPT_BASE_URL", "")).rstrip("/")
        self.endpoint = endpoint or os.getenv("FALCON_GPT_ENDPOINT", "/v1/chat/completions")
        self.api_key = api_key or os.getenv("FALCON_GPT_API_KEY", "")
        self.model = model or os.getenv("FALCON_GPT_MODEL", "gpt-5.5")
        self.timeout = int(os.getenv("FALCON_GPT_TIMEOUT", str(timeout)))

    @classmethod
    def from_env(cls) -> "GPT55Client":
        return cls()

    def is_configured(self) -> bool:
        return bool(self.base_url and self.endpoint and self.api_key)

    def complete_json(self, system_prompt: str, user_prompt: str) -> Dict[str, object]:
        if not self.is_configured():
            raise RuntimeError("FALCON_GPT_BASE_URL, FALCON_GPT_ENDPOINT, and FALCON_GPT_API_KEY are required")

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.base_url + self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        content = payload["choices"][0]["message"]["content"]
        return self._parse_json_object(content)

    def _parse_json_object(self, content: str) -> Dict[str, object]:
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content.replace("json\n", "", 1).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("GPT response did not contain a JSON object")
        return json.loads(content[start : end + 1])
