# Codex Local Notes

- Keep normal Codex chat, code editing, and completions on the provider configured in `~/.codex/config.toml`.
- When the user asks to use image2 for image generation or editing, read `~/.codex/image2.toml` and call `base_url` + `endpoint` with OpenAI-style Bearer auth.
- Do not route normal Codex requests through image2, and do not print the full image2 API key.
- Always use the GPT-5.5 model for this project in every scenario, including subagents, subprocesses, simple tasks, and any delegated or background work. Do not downgrade or switch to smaller/faster models unless the user explicitly overrides this rule.
