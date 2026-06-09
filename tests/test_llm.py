import json
import unittest

from falcon.llm import GPT55Client, GPTResponseParseError


class FakeResponse:
    def __init__(self, lines=None, body=None):
        self.lines = lines or []
        self.body = body or b""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def __iter__(self):
        return iter(self.lines)

    def read(self):
        return self.body


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return self.response


def sse_event(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


class GPT55ClientTest(unittest.TestCase):
    def test_complete_json_uses_responses_stream_by_default(self):
        response = FakeResponse(
            lines=[
                sse_event({"type": "response.output_text.delta", "delta": '{"summary":"'}),
                sse_event({"type": "response.output_text.delta", "delta": "可以执行"}),
                sse_event({"type": "response.output_text.delta", "delta": '"}'}),
                b"data: [DONE]\n\n",
            ]
        )
        opener = FakeOpener(response)
        client = GPT55Client(base_url="https://relay.test", api_key="secret", opener=opener)

        result = client.complete_json("system", "user")

        self.assertEqual(result, {"summary": "可以执行"})
        request, timeout = opener.requests[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://relay.test/v1/responses")
        self.assertEqual(timeout, 60)
        self.assertTrue(body["stream"])
        self.assertEqual(body["model"], "gpt-5.5")
        self.assertEqual(body["instructions"], "system")
        self.assertEqual(body["input"], "user")
        self.assertNotIn("text", body)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.get_header("Accept"), "text/event-stream")
        self.assertEqual(request.get_header("User-agent"), "Falcon/0.1 OpenAI-Compatible-Client")

    def test_complete_json_accepts_responses_done_text(self):
        response = FakeResponse(
            lines=[
                sse_event({"type": "response.output_text.delta", "delta": '{"ignored":true}'}),
                sse_event({"type": "response.output_text.done", "text": '{"done":true}'}),
            ]
        )
        client = GPT55Client(base_url="https://relay.test", api_key="secret", opener=FakeOpener(response))

        self.assertEqual(client.complete_json("system", "user"), {"done": True})

    def test_stream_json_yields_delta_then_done_payload(self):
        response = FakeResponse(
            lines=[
                sse_event({"type": "response.output_text.delta", "delta": '{"summary":"'}),
                sse_event({"type": "response.output_text.delta", "delta": "流式"}),
                sse_event({"type": "response.output_text.delta", "delta": '"}'}),
                b"data: [DONE]\n\n",
            ]
        )
        client = GPT55Client(base_url="https://relay.test", api_key="secret", opener=FakeOpener(response))

        events = list(client.stream_json("system", "user"))

        self.assertEqual(
            events,
            [
                {"type": "delta", "text": '{"summary":"'},
                {"type": "delta", "text": "流式"},
                {"type": "delta", "text": '"}'},
                {"type": "done", "payload": {"summary": "流式"}},
            ],
        )

    def test_complete_json_raises_for_responses_stream_error(self):
        response = FakeResponse(
            lines=[
                sse_event(
                    {
                        "type": "error",
                        "error": {"message": "relay stream failed"},
                    }
                )
            ]
        )
        client = GPT55Client(base_url="https://relay.test", api_key="secret", opener=FakeOpener(response))

        with self.assertRaisesRegex(RuntimeError, "relay stream failed"):
            client.complete_json("system", "user")

    def test_parse_error_keeps_raw_json_candidate(self):
        response = FakeResponse(
            lines=[
                sse_event({"type": "response.output_text.done", "text": '{"matches":[{"reason":"ok" "excerpt":"bad"}]}'}),
                b"data: [DONE]\n\n",
            ]
        )
        client = GPT55Client(base_url="https://relay.test", api_key="secret", opener=FakeOpener(response))

        with self.assertRaises(GPTResponseParseError) as caught:
            client.complete_json("system", "user")

        self.assertIn('"matches"', caught.exception.content)
        self.assertIn('"excerpt"', caught.exception.content)

    def test_chat_completions_endpoint_remains_supported(self):
        response = FakeResponse(
            body=json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "```json\n{\"legacy\": true}\n```",
                            }
                        }
                    ]
                }
            ).encode("utf-8")
        )
        opener = FakeOpener(response)
        client = GPT55Client(
            base_url="https://relay.test",
            endpoint="/v1/chat/completions",
            api_key="secret",
            opener=opener,
        )

        result = client.complete_json("system", "user")

        self.assertEqual(result, {"legacy": True})
        request, _timeout = opener.requests[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://relay.test/v1/chat/completions")
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["response_format"]["type"], "json_object")
        self.assertEqual(request.get_header("Accept"), "application/json")

    def test_complete_json_multimodal_uses_responses_image_parts(self):
        response = FakeResponse(
            lines=[
                sse_event({"type": "response.output_text.done", "text": '{"ok":true}'}),
                b"data: [DONE]\n\n",
            ]
        )
        opener = FakeOpener(response)
        client = GPT55Client(base_url="https://relay.test", api_key="secret", opener=opener)

        result = client.complete_json_multimodal(
            "system",
            "user",
            [
                {
                    "post_id": "12",
                    "asset_id": "34",
                    "mime_type": "image/jpeg",
                    "data_url": "data:image/jpeg;base64,abc",
                }
            ],
        )

        self.assertEqual(result, {"ok": True})
        request, _timeout = opener.requests[0]
        body = json.loads(request.data.decode("utf-8"))
        content = body["input"][0]["content"]
        self.assertEqual(body["instructions"], "system")
        self.assertEqual(content[0], {"type": "input_text", "text": "user"})
        self.assertEqual(content[1]["type"], "input_text")
        self.assertIn("asset_id=34", content[1]["text"])
        self.assertEqual(content[2], {"type": "input_image", "image_url": "data:image/jpeg;base64,abc"})

    def test_complete_json_multimodal_uses_chat_image_parts(self):
        response = FakeResponse(
            body=json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"ok": true}',
                            }
                        }
                    ]
                }
            ).encode("utf-8")
        )
        opener = FakeOpener(response)
        client = GPT55Client(
            base_url="https://relay.test",
            endpoint="/v1/chat/completions",
            api_key="secret",
            opener=opener,
        )

        result = client.complete_json_multimodal(
            "system",
            "user",
            [
                {
                    "post_id": "12",
                    "asset_id": "34",
                    "mime_type": "image/png",
                    "data_url": "data:image/png;base64,abc",
                }
            ],
        )

        self.assertEqual(result, {"ok": True})
        request, _timeout = opener.requests[0]
        body = json.loads(request.data.decode("utf-8"))
        content = body["messages"][1]["content"]
        self.assertEqual(body["messages"][0], {"role": "system", "content": "system"})
        self.assertEqual(content[0], {"type": "text", "text": "user"})
        self.assertEqual(content[1]["type"], "text")
        self.assertIn("asset_id=34", content[1]["text"])
        self.assertEqual(content[2], {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}})


if __name__ == "__main__":
    unittest.main()
