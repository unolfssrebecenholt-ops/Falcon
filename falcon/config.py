import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping, Optional
from urllib.parse import urlparse


DEFAULT_GPT_ENDPOINT = "/v1/chat/completions"
DEFAULT_GPT_MODEL = "gpt-5.5"
DEFAULT_GPT_TIMEOUT = "180"
GPT_ENDPOINT_OPTIONS = {
    "/v1/chat/completions": {
        "label": "Chat Completions",
        "summary": "兼容性更稳，使用流式接收并在后端拼完整 JSON。",
        "mode": "chat",
        "streaming": True,
    },
    "/v1/responses": {
        "label": "Responses API",
        "summary": "支持流式输出；部分中转站的 JSON/stream 通道可能返回 502。",
        "mode": "responses",
        "streaming": True,
    },
}

GPT_ENV_KEYS = {
    "FALCON_GPT_BASE_URL",
    "FALCON_GPT_ENDPOINT",
    "FALCON_GPT_API_KEY",
    "FALCON_GPT_MODEL",
    "FALCON_GPT_TIMEOUT",
}
DEFAULT_RUNTIME_COLLECTOR_MAX_POSTS = 8
DEFAULT_RUNTIME_COLLECTOR_MAX_COMMENTS_PER_POST = 5
DEFAULT_RUNTIME_ANALYSIS_PROBE_COUNT = 8
RUNTIME_SETTINGS_MINIMUMS = {
    "collector_max_posts": 1,
    "collector_max_comments_per_post": 0,
    "analysis_probe_count": 1,
}

RUNTIME_SETTINGS_ENV_KEYS = {
    "FALCON_COLLECTOR_MAX_POSTS",
    "FALCON_COLLECTOR_MAX_COMMENTS_PER_POST",
    "FALCON_ANALYSIS_PROBE_COUNT",
}


@dataclass
class GPTConfigView:
    base_url: str
    endpoint: str
    endpoint_label: str
    endpoint_mode: str
    endpoint_streaming: bool
    endpoint_summary: str
    api_key: str
    model: str
    timeout: str
    masked_api_key: str
    configured: bool
    env_path: Path
    env_exists: bool


@dataclass
class RuntimeSettingsView:
    collector_max_posts: int
    collector_max_comments_per_post: int
    analysis_probe_count: int
    env_path: Path
    env_exists: bool


def load_gpt_config_view(
    env_path: Path,
    environment: Optional[Mapping[str, str]] = None,
) -> GPTConfigView:
    environment = environment if environment is not None else os.environ
    file_values = read_env_values(env_path)

    def value(key: str, default: str = "") -> str:
        return str(environment.get(key) or file_values.get(key) or default)

    api_key = value("FALCON_GPT_API_KEY")
    base_url = value("FALCON_GPT_BASE_URL")
    endpoint = normalize_gpt_endpoint(value("FALCON_GPT_ENDPOINT", DEFAULT_GPT_ENDPOINT))
    endpoint_meta = GPT_ENDPOINT_OPTIONS.get(endpoint, GPT_ENDPOINT_OPTIONS[DEFAULT_GPT_ENDPOINT])
    return GPTConfigView(
        base_url=base_url,
        endpoint=endpoint,
        endpoint_label=endpoint_meta["label"],
        endpoint_mode=endpoint_meta["mode"],
        endpoint_streaming=bool(endpoint_meta["streaming"]),
        endpoint_summary=endpoint_meta["summary"],
        api_key=api_key,
        model=value("FALCON_GPT_MODEL", DEFAULT_GPT_MODEL),
        timeout=value("FALCON_GPT_TIMEOUT", DEFAULT_GPT_TIMEOUT),
        masked_api_key=mask_secret(api_key),
        configured=bool(base_url and api_key),
        env_path=env_path,
        env_exists=env_path.exists(),
    )


def load_runtime_settings_view(
    env_path: Path,
    environment: Optional[Mapping[str, str]] = None,
) -> RuntimeSettingsView:
    environment = environment if environment is not None else os.environ
    file_values = read_env_values(env_path)

    def value(key: str, default: int) -> str:
        return str(environment.get(key) or file_values.get(key) or default)

    return RuntimeSettingsView(
        collector_max_posts=normalize_runtime_setting(
            "collector_max_posts",
            value("FALCON_COLLECTOR_MAX_POSTS", DEFAULT_RUNTIME_COLLECTOR_MAX_POSTS),
        ),
        collector_max_comments_per_post=normalize_runtime_setting(
            "collector_max_comments_per_post",
            value("FALCON_COLLECTOR_MAX_COMMENTS_PER_POST", DEFAULT_RUNTIME_COLLECTOR_MAX_COMMENTS_PER_POST),
        ),
        analysis_probe_count=normalize_runtime_setting(
            "analysis_probe_count",
            value("FALCON_ANALYSIS_PROBE_COUNT", DEFAULT_RUNTIME_ANALYSIS_PROBE_COUNT),
        ),
        env_path=env_path,
        env_exists=env_path.exists(),
    )


def save_runtime_settings(
    env_path: Path,
    *,
    collector_max_posts: object,
    collector_max_comments_per_post: object,
    analysis_probe_count: object,
    environment: Optional[MutableMapping[str, str]] = None,
) -> RuntimeSettingsView:
    values = {
        "FALCON_COLLECTOR_MAX_POSTS": str(
            normalize_runtime_setting("collector_max_posts", collector_max_posts)
        ),
        "FALCON_COLLECTOR_MAX_COMMENTS_PER_POST": str(
            normalize_runtime_setting(
                "collector_max_comments_per_post",
                collector_max_comments_per_post,
            )
        ),
        "FALCON_ANALYSIS_PROBE_COUNT": str(
            normalize_runtime_setting("analysis_probe_count", analysis_probe_count)
        ),
    }
    write_env_values(env_path, values)
    target_env = environment if environment is not None else os.environ
    for key, value in values.items():
        target_env[key] = value
    return load_runtime_settings_view(env_path, environment=target_env)


def save_gpt_config(
    env_path: Path,
    *,
    base_url: str,
    api_key: str,
    endpoint: str = DEFAULT_GPT_ENDPOINT,
    environment: Optional[MutableMapping[str, str]] = None,
) -> None:
    base_url = normalize_base_url(base_url)
    api_key = _clean_env_value(api_key, "FALCON_GPT_API_KEY")
    endpoint = normalize_gpt_endpoint(endpoint)
    if not base_url:
        raise ValueError("GPT base URL is required")
    if not api_key:
        raise ValueError("GPT API key is required")

    values = {
        "FALCON_GPT_BASE_URL": base_url,
        "FALCON_GPT_ENDPOINT": endpoint,
        "FALCON_GPT_API_KEY": api_key,
        "FALCON_GPT_MODEL": DEFAULT_GPT_MODEL,
        "FALCON_GPT_TIMEOUT": DEFAULT_GPT_TIMEOUT,
    }
    write_env_values(env_path, values)
    target_env = environment if environment is not None else os.environ
    for key, value in values.items():
        target_env[key] = value


def normalize_runtime_setting(field_name: str, value: object) -> int:
    if field_name not in RUNTIME_SETTINGS_MINIMUMS:
        raise ValueError(f"Unknown runtime setting: {field_name}")
    cleaned = _clean_env_value(str(value), field_name)
    try:
        number = int(cleaned)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    minimum = RUNTIME_SETTINGS_MINIMUMS[field_name]
    if number < minimum:
        raise ValueError(f"{field_name} must be greater than or equal to {minimum}")
    return number


def normalize_base_url(value: str) -> str:
    cleaned = _clean_env_value(value, "FALCON_GPT_BASE_URL").rstrip("/")
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("GPT base URL must start with http:// or https://")
    return cleaned


def normalize_gpt_endpoint(value: str) -> str:
    endpoint = _clean_env_value(value, "FALCON_GPT_ENDPOINT") or DEFAULT_GPT_ENDPOINT
    if endpoint not in GPT_ENDPOINT_OPTIONS:
        allowed = "、".join(GPT_ENDPOINT_OPTIONS)
        raise ValueError(f"GPT endpoint must be one of: {allowed}")
    return endpoint


def read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        values[key] = value
    return values


def write_env_values(path: Path, values: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
    output = []
    written: set[str] = set()
    for line in lines:
        parsed = _parse_env_line(line.rstrip("\n\r"))
        if parsed is None or parsed[0] not in values:
            output.append(line)
            continue
        key = parsed[0]
        if key in written:
            continue
        output.append(_format_env_line(key, values[key]))
        written.add(key)
    missing = [key for key in values if key not in written]
    if missing and output and not output[-1].endswith("\n"):
        output[-1] = output[-1] + "\n"
    if missing and output and output[-1].strip():
        output.append("\n")
    for key in missing:
        output.append(_format_env_line(key, values[key]))
    path.write_text("".join(output), encoding="utf-8")


def mask_secret(value: str) -> str:
    if not value:
        return "未配置"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _clean_env_value(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if "\n" in text or "\r" in text:
        raise ValueError(f"{field_name} cannot contain line breaks")
    return text


def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None
    return key, value.strip().strip('"').strip("'")


def _format_env_line(key: str, value: str) -> str:
    return f"{key}={value}\n"
