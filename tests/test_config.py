import tempfile
import unittest
from pathlib import Path

from falcon.config import (
    load_gpt_config_view,
    load_runtime_settings_view,
    mask_secret,
    save_gpt_config,
    save_runtime_settings,
)


class GPTConfigTest(unittest.TestCase):
    def test_save_gpt_config_preserves_other_env_values_and_updates_runtime_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "FALCON_IMAGE2_MODEL=gpt-image-2\n"
                "FALCON_GPT_ENDPOINT=/v1/chat/completions\n"
                "FALCON_GPT_API_KEY=old-key\n",
                encoding="utf-8",
            )
            runtime_env = {}

            save_gpt_config(
                env_path,
                base_url="https://relay.example.com/",
                api_key="sk-test-secret",
                endpoint="/v1/chat/completions",
                environment=runtime_env,
            )

            content = env_path.read_text(encoding="utf-8")
            self.assertIn("FALCON_IMAGE2_MODEL=gpt-image-2", content)
            self.assertIn("FALCON_GPT_BASE_URL=https://relay.example.com", content)
            self.assertIn("FALCON_GPT_ENDPOINT=/v1/chat/completions", content)
            self.assertIn("FALCON_GPT_API_KEY=sk-test-secret", content)
            self.assertIn("FALCON_GPT_MODEL=gpt-5.5", content)
            self.assertIn("FALCON_GPT_TIMEOUT=180", content)
            self.assertEqual(runtime_env["FALCON_GPT_ENDPOINT"], "/v1/chat/completions")

    def test_load_gpt_config_view_prefers_environment_and_masks_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "FALCON_GPT_BASE_URL=https://file.example.com\n"
                "FALCON_GPT_API_KEY=file-secret-key\n",
                encoding="utf-8",
            )

            view = load_gpt_config_view(
                env_path,
                environment={
                    "FALCON_GPT_BASE_URL": "https://env.example.com",
                    "FALCON_GPT_API_KEY": "env-secret-key",
                },
            )

            self.assertEqual(view.base_url, "https://env.example.com")
            self.assertEqual(view.endpoint, "/v1/chat/completions")
            self.assertEqual(view.endpoint_label, "Chat Completions")
            self.assertTrue(view.endpoint_streaming)
            self.assertEqual(view.model, "gpt-5.5")
            self.assertEqual(view.timeout, "180")
            self.assertEqual(view.masked_api_key, "env-...-key")
            self.assertTrue(view.configured)

    def test_save_gpt_config_rejects_invalid_url_and_line_breaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            with self.assertRaisesRegex(ValueError, "http"):
                save_gpt_config(env_path, base_url="relay.example.com", api_key="secret")
            with self.assertRaisesRegex(ValueError, "line breaks"):
                save_gpt_config(env_path, base_url="https://relay.example.com", api_key="secret\nnext")
            with self.assertRaisesRegex(ValueError, "endpoint"):
                save_gpt_config(
                    env_path,
                    base_url="https://relay.example.com",
                    api_key="secret",
                    endpoint="/v1/unknown",
                )

    def test_mask_secret_handles_short_and_empty_values(self):
        self.assertEqual(mask_secret(""), "未配置")
        self.assertEqual(mask_secret("short"), "*****")
        self.assertEqual(mask_secret("sk-1234567890"), "sk-1...7890")

    def test_runtime_settings_read_defaults_and_save_env_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("FALCON_IMAGE2_MODEL=gpt-image-2\n", encoding="utf-8")
            runtime_env = {}

            defaults = load_runtime_settings_view(env_path, environment=runtime_env)
            saved = save_runtime_settings(
                env_path,
                collector_max_posts=59,
                collector_max_comments_per_post=80,
                analysis_probe_count=16,
                environment=runtime_env,
            )

            self.assertEqual(defaults.collector_max_posts, 8)
            self.assertEqual(defaults.collector_max_comments_per_post, 5)
            self.assertEqual(defaults.analysis_probe_count, 8)
            self.assertEqual(saved.collector_max_posts, 59)
            self.assertEqual(saved.collector_max_comments_per_post, 80)
            self.assertEqual(saved.analysis_probe_count, 16)
            content = env_path.read_text(encoding="utf-8")
            self.assertIn("FALCON_IMAGE2_MODEL=gpt-image-2", content)
            self.assertIn("FALCON_COLLECTOR_MAX_POSTS=59", content)
            self.assertIn("FALCON_COLLECTOR_MAX_COMMENTS_PER_POST=80", content)
            self.assertIn("FALCON_ANALYSIS_PROBE_COUNT=16", content)
            self.assertEqual(runtime_env["FALCON_ANALYSIS_PROBE_COUNT"], "16")

    def test_runtime_settings_reject_invalid_values_without_writing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("FALCON_IMAGE2_MODEL=gpt-image-2\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "greater than or equal to 1"):
                save_runtime_settings(
                    env_path,
                    collector_max_posts=0,
                    collector_max_comments_per_post=5,
                    analysis_probe_count=8,
                    environment={},
                )
            with self.assertRaisesRegex(ValueError, "greater than or equal to 0"):
                save_runtime_settings(
                    env_path,
                    collector_max_posts=8,
                    collector_max_comments_per_post=-1,
                    analysis_probe_count=8,
                    environment={},
                )
            with self.assertRaisesRegex(ValueError, "greater than or equal to 1"):
                save_runtime_settings(
                    env_path,
                    collector_max_posts=8,
                    collector_max_comments_per_post=5,
                    analysis_probe_count=0,
                    environment={},
                )

            content = env_path.read_text(encoding="utf-8")
            self.assertIn("FALCON_IMAGE2_MODEL=gpt-image-2", content)
            self.assertNotIn("FALCON_COLLECTOR_MAX_POSTS", content)


if __name__ == "__main__":
    unittest.main()
