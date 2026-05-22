import base64
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

from falcon.image2 import Image2Client, Image2Provider, load_env_file


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class Image2ClientTest(unittest.TestCase):
    def test_decodes_b64_image_response(self):
        image_bytes = b"fake-png"
        payload = {
            "data": [
                {"b64_json": base64.b64encode(image_bytes).decode("ascii")},
            ]
        }

        def opener(request, timeout):
            self.assertIn("/v1/images/generations", request.full_url)
            self.assertNotIn("secret", request.full_url)
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        client = Image2Client(
            providers=[Image2Provider("primary", "https://example.test", "secret")],
            model="image-model",
            opener=opener,
        )

        result = client.generate("draw Falcon")

        self.assertEqual(result.image_bytes, image_bytes)
        self.assertEqual(result.provider_name, "primary")

    def test_falls_back_when_primary_fails(self):
        calls = []
        image_bytes = b"fallback-image"
        payload = {"data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}]}

        def opener(request, timeout):
            calls.append(request.full_url)
            if "primary.test" in request.full_url:
                raise TimeoutError("primary timeout")
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        client = Image2Client(
            providers=[
                Image2Provider("primary", "https://primary.test", "primary-key"),
                Image2Provider("fallback", "https://fallback.test", "fallback-key"),
            ],
            opener=opener,
        )

        result = client.generate("draw Falcon")

        self.assertEqual(result.image_bytes, image_bytes)
        self.assertEqual(result.provider_name, "fallback")
        self.assertEqual(len(calls), 2)

    def test_follows_308_redirect_for_post(self):
        calls = []
        image_bytes = b"redirected-image"
        payload = {"data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}]}

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                headers = Message()
                headers["Location"] = "https://primary.test/v1/images/generations/"
                raise urllib.error.HTTPError(request.full_url, 308, "Permanent Redirect", headers, None)
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        client = Image2Client(
            providers=[Image2Provider("primary", "https://primary.test", "primary-key")],
            opener=opener,
        )

        result = client.generate("draw Falcon")

        self.assertEqual(result.image_bytes, image_bytes)
        self.assertEqual(result.provider_name, "primary")
        self.assertEqual(calls[-1], "https://primary.test/v1/images/generations/")

    def test_load_env_file_does_not_override_existing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "FALCON_IMAGE2_MODEL=from-file\nFALCON_IMAGE2_TIMEOUT=12\n",
                encoding="utf-8",
            )
            import os

            previous_model = os.environ.get("FALCON_IMAGE2_MODEL")
            previous_timeout = os.environ.get("FALCON_IMAGE2_TIMEOUT")
            os.environ["FALCON_IMAGE2_MODEL"] = "already-set"
            os.environ.pop("FALCON_IMAGE2_TIMEOUT", None)
            try:
                load_env_file(env_path)
                self.assertEqual(os.environ["FALCON_IMAGE2_MODEL"], "already-set")
                self.assertEqual(os.environ["FALCON_IMAGE2_TIMEOUT"], "12")
            finally:
                if previous_model is None:
                    os.environ.pop("FALCON_IMAGE2_MODEL", None)
                else:
                    os.environ["FALCON_IMAGE2_MODEL"] = previous_model
                if previous_timeout is None:
                    os.environ.pop("FALCON_IMAGE2_TIMEOUT", None)
                else:
                    os.environ["FALCON_IMAGE2_TIMEOUT"] = previous_timeout


if __name__ == "__main__":
    unittest.main()
