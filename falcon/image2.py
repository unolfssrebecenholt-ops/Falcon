import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


FALCON_AGENT_ARCHITECTURE_PROMPT = """生成一张清晰的产品架构图，主题为：

“Falcon Agent：GPT-5.5 + Image2 驱动的多平台内容运营 Agent”

画面包含这些层级：
- 采集基座层：小红书、抖音、闲鱼；真实浏览器采集图片、视频、标题、正文、发布时间、点赞、收藏、评论。
- 数据分析层：竞品爆款分析、帖子意向分析、评论意向分析、人工评分反哺。
- 报表工作台：Next.js UI，展示爆款内容、高意向帖子、高意向评论。
- 内容生成层：GPT-5.5 生成评论/发帖文案，Image2 生成发帖配图。
- 推荐执行层：半自动预览，用户可修改或一键发布。
- 飞书通道：验证码、风控暂停、咨询确认、任务通知。
- 安全边界：真实浏览器、复用会话、控制节奏、避免机械批量动作、默认人工确认。

风格：现代 SaaS 架构图，中文标签，深色背景，高级感，清晰模块分区，适合汇报展示。
"""


@dataclass
class Image2Provider:
    name: str
    base_url: str
    api_key: str

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)


@dataclass
class Image2Result:
    image_bytes: bytes
    provider_name: str


def load_env_file(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class Image2Client:
    """OpenAI-compatible image generation client with primary/fallback relays."""

    def __init__(
        self,
        providers: Iterable[Image2Provider] | None = None,
        endpoint: str = "",
        model: str = "",
        timeout: int = 90,
        size: str = "",
        opener: Callable | None = None,
    ):
        self.providers = list(providers) if providers is not None else self._providers_from_env()
        self.endpoint = endpoint or os.getenv("FALCON_IMAGE2_ENDPOINT", "/v1/images/generations")
        self.model = model or os.getenv("FALCON_IMAGE2_MODEL", "gpt-image-2")
        self.timeout = int(os.getenv("FALCON_IMAGE2_TIMEOUT", str(timeout)))
        self.size = size or os.getenv("FALCON_IMAGE2_SIZE", "1536x1024")
        self._opener = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> "Image2Client":
        return cls()

    def is_configured(self) -> bool:
        return any(provider.is_configured() for provider in self.providers)

    def generate(self, prompt: str) -> Image2Result:
        if not self.is_configured():
            raise RuntimeError("FALCON_IMAGE2_* relay configuration is required")

        errors: list[str] = []
        for provider in self.providers:
            if not provider.is_configured():
                continue
            try:
                return Image2Result(
                    image_bytes=self._generate_with_provider(provider, prompt),
                    provider_name=provider.name,
                )
            except Exception as exc:
                errors.append(f"{provider.name}: {type(exc).__name__}: {exc}")
        raise RuntimeError("Image2 generation failed via all configured providers: " + " | ".join(errors))

    def save(self, prompt: str, output_path: Path) -> Image2Result:
        result = self.generate(prompt)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(result.image_bytes)
        return result

    def _generate_with_provider(self, provider: Image2Provider, prompt: str) -> bytes:
        body = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": self.size,
            "response_format": "b64_json",
        }
        url = provider.base_url.rstrip("/") + self.endpoint
        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            response_ctx = self._opener(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in {307, 308}:
                raise
            redirect_url = exc.headers.get("Location")
            if not redirect_url:
                raise
            redirect_request = urllib.request.Request(
                urllib.request.urljoin(url, redirect_url),
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            response_ctx = self._opener(redirect_request, timeout=self.timeout)

        with response_ctx as response:
            payload = json.loads(response.read().decode("utf-8"))
        return self._image_bytes_from_payload(payload)

    def _image_bytes_from_payload(self, payload: dict) -> bytes:
        data = payload.get("data") or []
        if not data:
            raise ValueError("image response did not contain data")

        first = data[0]
        b64_json = first.get("b64_json") if isinstance(first, dict) else None
        if b64_json:
            return base64.b64decode(b64_json)

        image_url = first.get("url") if isinstance(first, dict) else None
        if image_url:
            with self._opener(image_url, timeout=self.timeout) as response:
                return response.read()

        raise ValueError("image response did not contain b64_json or url")

    def _providers_from_env(self) -> list[Image2Provider]:
        return [
            Image2Provider(
                name="primary",
                base_url=os.getenv("FALCON_IMAGE2_PRIMARY_BASE_URL", "").rstrip("/"),
                api_key=os.getenv("FALCON_IMAGE2_PRIMARY_API_KEY", ""),
            ),
            Image2Provider(
                name="fallback",
                base_url=os.getenv("FALCON_IMAGE2_FALLBACK_BASE_URL", "").rstrip("/"),
                api_key=os.getenv("FALCON_IMAGE2_FALLBACK_API_KEY", ""),
            ),
        ]
