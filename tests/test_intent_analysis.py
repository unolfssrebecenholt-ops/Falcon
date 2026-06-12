import json
import tempfile
import unittest
from pathlib import Path

from falcon.db import FalconRepository
from falcon.intent_analysis import IntentAnalysisService
from falcon.llm import GPTHTTPError, GPTResponseParseError
from falcon.models import (
    CollectedComment,
    CollectedPost,
    CollectionRun,
    IntentAnalysisMatch,
    IntentAnalysisProbe,
    IntentAnalysisTask,
    MediaAsset,
)


class FakeIntentClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if "生成 5 个" in system_prompt:
            return {
                "probes": [
                    {
                        "title": f"探针 {index}",
                        "description": f"识别第 {index} 类需求",
                        "positive_signals": [f"正向 {index}"],
                        "negative_signals": [f"排除 {index}"],
                    }
                    for index in range(1, 6)
                ]
            }
        return {
            "matches": [
                {
                    "probe_key": "probe-1",
                    "post_id": 1,
                    "level": "post",
                    "score": 87,
                    "reason": "正文明确在找生图软件市场机会",
                    "excerpt": "想知道生图软件市场怎么样",
                    "summary": "帖子整体在评估生图软件市场机会",
                },
                {
                    "probe_key": "probe-1",
                    "post_id": 1,
                    "comment_id": 1,
                    "level": "comment",
                    "score": 92,
                    "reason": "评论直接求推荐工具",
                    "excerpt": "跪求好用的生图软件",
                },
            ]
        }

    def is_configured(self):
        return True


class StreamingIntentClient(FakeIntentClient):
    def stream_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        yield {"type": "delta", "text": '{"probes":'}
        yield {
            "type": "done",
            "payload": {
                "probes": [
                    {
                        "title": f"流式探针 {index}",
                        "description": f"识别第 {index} 类流式需求",
                        "positive_signals": [f"流式正向 {index}"],
                        "negative_signals": [f"流式排除 {index}"],
                    }
                    for index in range(1, 6)
                ]
            },
        }


class UnconfiguredIntentClient:
    def is_configured(self):
        return False

    def complete_json(self, system_prompt, user_prompt):
        raise AssertionError("unconfigured client should not be called")


class ModelCaptureClient(FakeIntentClient):
    def __init__(self):
        super().__init__()
        self.model = "not-gpt-5.5"


class DisabledProbeMatchClient(FakeIntentClient):
    def complete_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return {
            "matches": [
                {
                    "probe_key": "probe-disabled",
                    "post_id": 1,
                    "level": "post",
                    "score": 81,
                    "reason": "历史关闭探针仍是当前保留探针",
                    "excerpt": "正在寻找归纳 App",
                    "summary": "帖子表达了归纳 App 需求",
                }
            ]
        }


class MultimodalIntentClient(FakeIntentClient):
    def __init__(self, asset_id: int):
        super().__init__()
        self.asset_id = asset_id
        self.multimodal_calls = []

    def complete_json_multimodal(self, system_prompt, user_prompt, images):
        self.multimodal_calls.append((system_prompt, user_prompt, images))
        return {
            "matches": [
                {
                    "probe_key": "probe-1",
                    "post_id": 1,
                    "asset_id": self.asset_id,
                    "level": "image",
                    "score": 93,
                    "reason": "图片里出现了收纳清单界面。",
                    "excerpt": "图片展示按房间整理物品的清单",
                }
            ]
        }


class BatchCaptureIntentClient(FakeIntentClient):
    def complete_json(self, system_prompt, user_prompt):
        payload = json.loads(user_prompt)
        self.calls.append((system_prompt, user_prompt, payload))
        return {
            "matches": [
                {
                    "probe_key": "probe-1",
                    "post_id": post["post_id"],
                    "level": "post",
                    "score": 81,
                    "reason": "批次内帖子符合需求",
                    "excerpt": post["content"],
                    "summary": "批次内帖子命中",
                }
                for post in payload["posts"]
            ]
        }


class EmptyMultimodalBatchClient(FakeIntentClient):
    def __init__(self):
        super().__init__()
        self.multimodal_calls = []

    def complete_json_multimodal(self, system_prompt, user_prompt, images):
        payload = json.loads(user_prompt)
        self.multimodal_calls.append((system_prompt, user_prompt, images, payload))
        return {"matches": []}


class WrappedParseErrorClient(FakeIntentClient):
    def complete_json(self, system_prompt, user_prompt):
        raise RuntimeError("relay returned invalid JSON") from GPTResponseParseError(
            "Expecting ',' delimiter",
            '{"matches":[{"reason":"ok" "excerpt":"bad"}]}',
        )


class FractionalScoreIntentClient(FakeIntentClient):
    def complete_json(self, system_prompt, user_prompt):
        return {
            "matches": [
                {
                    "probe_key": "probe-1",
                    "post_id": 1,
                    "level": "post",
                    "score": 0.95,
                    "reason": "小数置信度应该按百分制保存",
                    "excerpt": "正在寻找收纳工具",
                    "summary": "帖子表达了收纳工具需求",
                }
            ]
        }


class WrappedHTTPErrorClient(FakeIntentClient):
    endpoint = "/v1/responses"

    def complete_json(self, system_prompt, user_prompt):
        raise RuntimeError("relay gateway failed") from GPTHTTPError(502, "Bad Gateway", '{"error":"upstream"}')


class IntentAnalysisRepositoryTest(unittest.TestCase):
    def test_saves_task_sources_probes_matches_and_builds_post_comment_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-market-1",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    profile="default",
                    status="completed",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-market-1",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    title="生图软件市场观察",
                    content="想知道哪些人需要生图软件，以及付费意愿。",
                    url="local://xhs-market-1/post-1",
                    detail_fingerprint="market-1",
                )
            )
            comment_id = repo.save_collected_comment(
                CollectedComment(
                    post_id=post_id,
                    run_id="xhs-market-1",
                    commenter="reader",
                    content="跪求好用的 image2 生图软件推荐。",
                    like_count="12",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析生图软件的市场")
            )
            source_ids = repo.add_intent_analysis_sources(task_id, ["xhs-market-1"])
            probe_id = repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="求推荐生图工具",
                    description="识别正在寻找或比较生图工具的人",
                    positive_signals="求推荐\n有没有",
                    negative_signals="纯展示作品",
                    sort_order=1,
                )
            )
            match_id = repo.save_intent_analysis_match(
                IntentAnalysisMatch(
                    task_id=task_id,
                    probe_id=probe_id,
                    probe_key="probe-1",
                    post_id=post_id,
                    comment_id=comment_id,
                    level="comment",
                    score=92,
                    reason="评论直接求推荐",
                    excerpt="跪求好用的 image2 生图软件推荐。",
                )
            )

            package = repo.build_intent_analysis_package(task_id)
            task = repo.get_intent_analysis_task(task_id)
            sources = repo.list_intent_analysis_sources(task_id)
            probes = repo.list_intent_analysis_probes(task_id)
            matches = repo.list_intent_analysis_matches(task_id)

            self.assertEqual(task.user_intent, "我想分析生图软件的市场")
            self.assertEqual(source_ids, [sources[0].source_id])
            self.assertEqual(sources[0].run_id, "xhs-market-1")
            self.assertEqual(probes[0].title, "求推荐生图工具")
            self.assertEqual(matches[0].match_id, match_id)
            self.assertEqual(package[0]["title"], "生图软件市场观察")
            self.assertEqual(package[0]["comments"][0]["content"], "跪求好用的 image2 生图软件推荐。")

    def test_saves_image_level_matches_with_asset_id_and_dedupes_by_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="market")
            )
            probe_id = repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="Image evidence",
                    description="Find image demand",
                    positive_signals="image",
                    negative_signals="none",
                    sort_order=1,
                )
            )
            first = IntentAnalysisMatch(
                task_id=task_id,
                probe_id=probe_id,
                probe_key="probe-1",
                probe_title="Image evidence",
                post_id=1,
                asset_id=10,
                level="image",
                score=91,
                reason="same image",
                excerpt="same excerpt",
            )
            second = IntentAnalysisMatch(
                task_id=task_id,
                probe_id=probe_id,
                probe_key="probe-1",
                probe_title="Image evidence",
                post_id=1,
                asset_id=11,
                level="image",
                score=88,
                reason="other image",
                excerpt="same excerpt",
            )

            first_id = repo.save_intent_analysis_match(first)
            duplicate_id = repo.save_intent_analysis_match(first)
            second_id = repo.save_intent_analysis_match(second)
            matches = repo.list_intent_analysis_matches(task_id)

            self.assertEqual(first_id, duplicate_id)
            self.assertNotEqual(first_id, second_id)
            self.assertEqual([match.asset_id for match in matches], [10, 11])

    def test_rejects_mixed_platform_sources_for_one_intent_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(CollectionRun("xhs-run", "xiaohongshu", "生图软件", "default"))
            repo.create_collection_run(CollectionRun("douyin-run", "douyin", "生图软件", "default"))
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想知道哪些人需要生图软件")
            )

            with self.assertRaises(ValueError):
                repo.add_intent_analysis_sources(task_id, ["xhs-run", "douyin-run"])

    def test_rejects_non_completed_runs_for_intent_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(CollectionRun("xhs-queued", "xiaohongshu", "生图软件", "default", status="queued"))
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析生图软件的市场")
            )

            with self.assertRaises(ValueError):
                repo.add_intent_analysis_sources(task_id, ["xhs-queued"])

    def test_dedupes_duplicate_post_level_matches_with_null_comment_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="market")
            )
            probe_id = repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="Market need",
                    description="Find market demand",
                    positive_signals="need",
                    negative_signals="none",
                    sort_order=1,
                )
            )
            match = IntentAnalysisMatch(
                task_id=task_id,
                probe_id=probe_id,
                probe_key="probe-1",
                probe_title="Market need",
                post_id=1,
                level="post",
                score=88,
                reason="same reason",
                excerpt="same excerpt",
                summary="same summary",
            )

            first_id = repo.save_intent_analysis_match(match)
            second_id = repo.save_intent_analysis_match(match)

            self.assertEqual(first_id, second_id)
            self.assertEqual(len(repo.list_intent_analysis_matches(task_id)), 1)


class IntentAnalysisServiceTest(unittest.TestCase):
    def test_generates_five_gpt55_probes_for_user_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想知道哪些人需要生图软件")
            )

            fake_client = FakeIntentClient()
            probes = IntentAnalysisService(repo, client=fake_client).generate_probes(task_id)

            self.assertEqual(len(probes), 5)
            self.assertEqual([probe.sort_order for probe in probes], [1, 2, 3, 4, 5])
            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "probes_ready")
            self.assertIn("哪些人需要生图软件", fake_client.calls[0][1])

    def test_streams_probe_generation_events_and_saves_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想知道谁需要封面设计")
            )

            fake_client = StreamingIntentClient()
            events = list(IntentAnalysisService(repo, client=fake_client).generate_probes_stream(task_id))

            self.assertEqual(events[0]["type"], "status")
            self.assertEqual(events[1], {"type": "delta", "text": '{"probes":'})
            self.assertEqual(events[-1]["type"], "done")
            self.assertEqual(events[-1]["count"], 5)
            self.assertEqual(len(repo.list_intent_analysis_probes(task_id)), 5)
            self.assertEqual(repo.list_intent_analysis_probes(task_id)[0].title, "流式探针 1")
            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "probes_ready")

    def test_unconfigured_gpt_marks_task_failed_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析生图软件的市场")
            )

            with self.assertRaises(RuntimeError):
                IntentAnalysisService(repo, client=UnconfiguredIntentClient()).generate_probes(task_id)

            task = repo.get_intent_analysis_task(task_id)
            self.assertEqual(task.status, "failed")
            self.assertIn("FALCON_GPT_BASE_URL", task.failed_reason)

    def test_intent_service_pins_gpt55_model_even_when_client_has_other_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            fake_client = ModelCaptureClient()

            IntentAnalysisService(repo, client=fake_client)

            self.assertEqual(fake_client.model, "gpt-5.5")

    def test_executes_task_probes_with_title_content_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-market-1", "xiaohongshu", "生图软件", "default", status="completed")
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-market-1",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    title="生图软件市场观察",
                    content="想知道生图软件市场怎么样。",
                    url="local://xhs-market-1/post-1",
                    detail_fingerprint="market-1",
                )
            )
            repo.save_collected_comment(
                CollectedComment(
                    post_id=post_id,
                    run_id="xhs-market-1",
                    commenter="reader",
                    content="跪求好用的生图软件。",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析生图软件的市场")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-market-1"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="求推荐",
                    description="识别求推荐生图软件的人",
                    positive_signals="跪求\n推荐",
                    negative_signals="无需求展示",
                    sort_order=1,
                )
            )
            fake_client = FakeIntentClient()

            matches = IntentAnalysisService(repo, client=fake_client).execute_task(task_id)

            self.assertEqual(len(matches), 2)
            self.assertEqual({match.level for match in matches}, {"post", "comment"})
            self.assertEqual(
                [match.summary for match in matches if match.level == "post"],
                ["帖子整体在评估生图软件市场机会"],
            )
            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "completed")
            self.assertIn("生图软件市场观察", fake_client.calls[-1][1])
            self.assertIn("跪求好用的生图软件", fake_client.calls[-1][1])

    def test_executes_large_package_in_post_batches_without_global_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-batched-posts", "xiaohongshu", "收纳工具", "default", status="completed")
            )
            post_ids = []
            for index in range(1, 42):
                post_ids.append(
                    repo.save_collected_post(
                        CollectedPost(
                            run_id="xhs-batched-posts",
                            platform="xiaohongshu",
                            keyword="收纳工具",
                            title=f"第 {index} 个帖子",
                            content=f"第 {index} 个帖子正文，正在寻找收纳工具。",
                            url=f"local://xhs-batched-posts/post-{index}",
                            detail_fingerprint=f"batched-post-{index}",
                        )
                    )
                )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析收纳工具需求")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-batched-posts"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="收纳需求",
                    description="识别收纳工具需求",
                    positive_signals="收纳\n工具",
                    negative_signals="广告",
                    sort_order=1,
                )
            )
            fake_client = BatchCaptureIntentClient()

            matches = IntentAnalysisService(repo, client=fake_client).execute_task(task_id)

            batch_sizes = [len(call[2]["posts"]) for call in fake_client.calls]
            self.assertEqual(batch_sizes, [2] * 20 + [1])
            self.assertEqual(len(matches), 41)
            self.assertIn(post_ids[-1], {match.post_id for match in matches})
            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "completed")

    def test_executes_task_with_multimodal_images_and_saves_image_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            asset_root = tmp_path / "runtime" / "collector" / "xhs-images" / "assets"
            asset_root.mkdir(parents=True)
            for index in range(1, 8):
                (asset_root / f"cover-{index}.jpg").write_bytes(f"fake image {index}".encode("utf-8"))
            repo = FalconRepository(tmp_path / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-images", "xiaohongshu", "收纳工具", "default", status="completed")
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-images",
                    platform="xiaohongshu",
                    keyword="收纳工具",
                    title="收纳清单截图",
                    content="想找一个能记录家里物品的小程序。",
                    url="local://xhs-images/post-1",
                    detail_fingerprint="xhs-images-1",
                )
            )
            asset_ids = []
            for index in range(1, 8):
                asset_ids.append(
                    repo.save_media_asset(
                        MediaAsset(
                            run_id="xhs-images",
                            post_id=post_id,
                            path=f"runtime/collector/xhs-images/assets/cover-{index}.jpg",
                            asset_type="image",
                        )
                    )
                )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析收纳工具需求")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-images"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="图片中的收纳需求",
                    description="识别图片里出现的收纳工具场景",
                    positive_signals="收纳\n清单",
                    negative_signals="广告",
                    sort_order=1,
                )
            )
            fake_client = MultimodalIntentClient(asset_ids[0])

            matches = IntentAnalysisService(repo, client=fake_client).execute_task(task_id)

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].level, "image")
            self.assertEqual(matches[0].asset_id, asset_ids[0])
            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "completed")
            self.assertEqual(len(fake_client.multimodal_calls[0][2]), 4)
            self.assertIn('"asset_id": %d' % asset_ids[0], fake_client.multimodal_calls[0][1])

    def test_execute_normalizes_fractional_scores_to_percentage(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-fractional-score", "xiaohongshu", "收纳工具", "default", status="completed")
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-fractional-score",
                    platform="xiaohongshu",
                    keyword="收纳工具",
                    title="收纳工具求推荐",
                    content="正在寻找收纳工具。",
                    url="local://xhs-fractional-score/post-1",
                    detail_fingerprint="fractional-score-post-1",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析收纳工具需求")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-fractional-score"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="收纳需求",
                    description="识别收纳工具需求",
                    positive_signals="收纳",
                    negative_signals="广告",
                    sort_order=1,
                )
            )

            matches = IntentAnalysisService(repo, client=FractionalScoreIntentClient()).execute_task(task_id)

            self.assertEqual(matches[0].score, 95)

    def test_multimodal_images_are_limited_inside_each_post_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            asset_root = tmp_path / "runtime" / "collector" / "xhs-image-batches" / "assets"
            asset_root.mkdir(parents=True)
            repo = FalconRepository(tmp_path / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-image-batches", "xiaohongshu", "收纳工具", "default", status="completed")
            )
            for post_index in range(1, 10):
                post_id = repo.save_collected_post(
                    CollectedPost(
                        run_id="xhs-image-batches",
                        platform="xiaohongshu",
                        keyword="收纳工具",
                        title=f"图片帖子 {post_index}",
                        content=f"第 {post_index} 个图片帖子正文。",
                        url=f"local://xhs-image-batches/post-{post_index}",
                        detail_fingerprint=f"image-batch-post-{post_index}",
                    )
                )
                for image_index in range(1, 8):
                    filename = f"post-{post_index}-cover-{image_index}.jpg"
                    (asset_root / filename).write_bytes(f"fake image {post_index}-{image_index}".encode("utf-8"))
                    repo.save_media_asset(
                        MediaAsset(
                            run_id="xhs-image-batches",
                            post_id=post_id,
                            path=f"runtime/collector/xhs-image-batches/assets/{filename}",
                            asset_type="image",
                        )
                    )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析图片里的收纳需求")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-image-batches"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="图片收纳需求",
                    description="识别图片中的收纳工具场景",
                    positive_signals="收纳",
                    negative_signals="广告",
                    sort_order=1,
                )
            )
            fake_client = EmptyMultimodalBatchClient()

            matches = IntentAnalysisService(repo, client=fake_client).execute_task(task_id)

            self.assertEqual(matches, [])
            self.assertEqual([len(call[2]) for call in fake_client.multimodal_calls], [8, 8, 8, 8, 4])
            self.assertEqual([len(call[3]["posts"]) for call in fake_client.multimodal_calls], [2, 2, 2, 2, 1])
            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "completed")

    def test_execute_marks_task_failed_when_images_exist_but_client_lacks_multimodal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            asset_root = tmp_path / "runtime" / "collector" / "xhs-no-mm" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "cover.jpg").write_bytes(b"fake image")
            repo = FalconRepository(tmp_path / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-no-mm", "xiaohongshu", "收纳工具", "default", status="completed")
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-no-mm",
                    platform="xiaohongshu",
                    keyword="收纳工具",
                    title="图片任务",
                    content="正文",
                    url="local://xhs-no-mm/post",
                    detail_fingerprint="xhs-no-mm-post",
                )
            )
            repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-no-mm",
                    post_id=post_id,
                    path="runtime/collector/xhs-no-mm/assets/cover.jpg",
                    asset_type="image",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="market")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-no-mm"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="Market need",
                    description="Find market demand",
                    positive_signals="need",
                    negative_signals="none",
                    sort_order=1,
                )
            )

            with self.assertRaisesRegex(RuntimeError, "multimodal"):
                IntentAnalysisService(repo, client=FakeIntentClient()).execute_task(task_id)

            task = repo.get_intent_analysis_task(task_id)
            self.assertEqual(task.status, "failed")
            self.assertIn("multimodal", task.failed_reason)

    def test_execute_failed_batch_marks_task_failed_with_batch_position(self):
        class FailingSecondBatchClient(FakeIntentClient):
            def complete_json(self, system_prompt, user_prompt):
                self.calls.append((system_prompt, user_prompt))
                if len(self.calls) == 2:
                    raise RuntimeError("relay overload")
                return {"matches": []}

        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-batch-failure", "xiaohongshu", "收纳工具", "default", status="completed")
            )
            for index in range(1, 18):
                repo.save_collected_post(
                    CollectedPost(
                        run_id="xhs-batch-failure",
                        platform="xiaohongshu",
                        keyword="收纳工具",
                        title=f"第 {index} 个帖子",
                        content=f"第 {index} 个帖子正文。",
                        url=f"local://xhs-batch-failure/post-{index}",
                        detail_fingerprint=f"batch-failure-post-{index}",
                    )
                )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析收纳工具需求")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-batch-failure"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="收纳需求",
                    description="识别收纳工具需求",
                    positive_signals="收纳",
                    negative_signals="广告",
                    sort_order=1,
                )
            )
            fake_client = FailingSecondBatchClient()

            with self.assertRaisesRegex(RuntimeError, "第 2/9 批分析失败"):
                service = IntentAnalysisService(repo, client=fake_client)
                service.log_root = Path(tmp) / "runtime" / "analysis"
                service.execute_task(task_id)

            task = repo.get_intent_analysis_task(task_id)
            self.assertEqual(task.status, "failed")
            self.assertIn("第 2/9 批分析失败", task.failed_reason)
            self.assertIn("relay overload", task.failed_reason)
            self.assertEqual(repo.list_intent_analysis_matches(task_id), [])
            error_log = Path(tmp) / "runtime" / "analysis" / f"task-{task_id}" / "batch-02-error.json"
            request_log = Path(tmp) / "runtime" / "analysis" / f"task-{task_id}" / "batch-02-request.json"
            self.assertTrue(request_log.exists())
            self.assertTrue(error_log.exists())
            error_payload = json.loads(error_log.read_text(encoding="utf-8"))
            self.assertEqual(error_payload["event"], "error")
            self.assertEqual(error_payload["batch_index"], 2)
            self.assertEqual(error_payload["batch_count"], 9)
            self.assertIn("relay overload", error_payload["error"])

    def test_execute_error_log_keeps_raw_response_from_wrapped_parse_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-bad-json", "xiaohongshu", "收纳工具", "default", status="completed")
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-bad-json",
                    platform="xiaohongshu",
                    keyword="收纳工具",
                    title="收纳工具求推荐",
                    content="正在寻找收纳工具。",
                    url="local://xhs-bad-json/post-1",
                    detail_fingerprint="bad-json-post-1",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析收纳工具需求")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-bad-json"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="收纳需求",
                    description="识别收纳工具需求",
                    positive_signals="收纳",
                    negative_signals="广告",
                    sort_order=1,
                )
            )
            service = IntentAnalysisService(repo, client=WrappedParseErrorClient())
            service.log_root = Path(tmp) / "runtime" / "analysis"

            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                service.execute_task(task_id)

            error_log = Path(tmp) / "runtime" / "analysis" / f"task-{task_id}" / "batch-01-error.json"
            error_payload = json.loads(error_log.read_text(encoding="utf-8"))
            self.assertIn('"matches"', error_payload["raw_response"])
            self.assertIn('"excerpt"', error_payload["raw_response"])

    def test_execute_error_log_keeps_http_status_and_body_from_wrapped_http_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-http-error", "xiaohongshu", "收纳工具", "default", status="completed")
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-http-error",
                    platform="xiaohongshu",
                    keyword="收纳工具",
                    title="收纳工具求推荐",
                    content="正在寻找收纳工具。",
                    url="local://xhs-http-error/post-1",
                    detail_fingerprint="http-error-post-1",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析收纳工具需求")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-http-error"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="收纳需求",
                    description="识别收纳工具需求",
                    positive_signals="收纳",
                    negative_signals="广告",
                    sort_order=1,
                )
            )
            service = IntentAnalysisService(repo, client=WrappedHTTPErrorClient())
            service.log_root = Path(tmp) / "runtime" / "analysis"

            with self.assertRaisesRegex(RuntimeError, "relay gateway failed"):
                service.execute_task(task_id)

            task = repo.get_intent_analysis_task(task_id)
            self.assertIn("Chat Completions", task.failed_reason)
            self.assertIn("Responses JSON/stream 通道异常", task.failed_reason)
            error_log = Path(tmp) / "runtime" / "analysis" / f"task-{task_id}" / "batch-01-error.json"
            error_payload = json.loads(error_log.read_text(encoding="utf-8"))
            self.assertEqual(error_payload["http_status"], 502)
            self.assertEqual(error_payload["http_reason"], "Bad Gateway")
            self.assertIn("upstream", error_payload["raw_response"])

    def test_execute_rejects_zero_probes_before_gpt_config_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="market")
            )

            with self.assertRaisesRegex(ValueError, "1 to 12"):
                IntentAnalysisService(repo, client=UnconfiguredIntentClient()).execute_task(task_id)

            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "failed")

    def test_executes_all_remaining_probes_even_if_legacy_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-disabled-probe", "xiaohongshu", "归纳 App", "default", status="completed")
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-disabled-probe",
                    platform="xiaohongshu",
                    keyword="归纳 App",
                    title="正在寻找归纳 App",
                    content="希望有工具能整理讨论。",
                    url="local://disabled-probe/post-1",
                    detail_fingerprint="disabled-probe-1",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想知道有没有归纳 App 需求")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-disabled-probe"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-disabled",
                    title="归纳需求",
                    description="识别归纳整理需求",
                    positive_signals="归纳\n整理",
                    negative_signals="广告",
                    sort_order=1,
                    enabled=False,
                )
            )
            fake_client = DisabledProbeMatchClient()

            matches = IntentAnalysisService(repo, client=fake_client).execute_task(task_id)

            self.assertEqual(len(matches), 1)
            self.assertIn('"probe_key": "probe-disabled"', fake_client.calls[-1][1])
            self.assertEqual(matches[0].probe_key, "probe-disabled")

    def test_execute_rejects_empty_data_package_without_calling_gpt(self):
        class NoCallClient(FakeIntentClient):
            def complete_json(self, system_prompt, user_prompt):
                raise AssertionError("empty package should block before GPT call")

        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-empty", "xiaohongshu", "生图软件", "default", status="completed")
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="market")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-empty"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="Market need",
                    description="Find market demand",
                    positive_signals="need",
                    negative_signals="none",
                    sort_order=1,
                )
            )

            with self.assertRaisesRegex(ValueError, "no collected posts"):
                IntentAnalysisService(repo, client=NoCallClient()).execute_task(task_id)

            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "failed")

    def test_rejects_comment_match_when_comment_belongs_to_another_post(self):
        class CrossPostCommentClient(FakeIntentClient):
            def complete_json(self, system_prompt, user_prompt):
                return {
                    "matches": [
                        {
                            "probe_key": "probe-1",
                            "post_id": 1,
                            "comment_id": 2,
                            "level": "comment",
                            "score": 90,
                            "reason": "wrong post comment",
                            "excerpt": "跨帖评论",
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-cross-comment", "xiaohongshu", "生图软件", "default", status="completed")
            )
            first_post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-cross-comment",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    title="第一帖",
                    content="第一帖正文",
                    url="local://cross/1",
                    detail_fingerprint="cross-1",
                )
            )
            second_post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-cross-comment",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    title="第二帖",
                    content="第二帖正文",
                    url="local://cross/2",
                    detail_fingerprint="cross-2",
                )
            )
            repo.save_collected_comment(
                CollectedComment(first_post_id, "xhs-cross-comment", "a", "第一帖评论")
            )
            repo.save_collected_comment(
                CollectedComment(second_post_id, "xhs-cross-comment", "b", "第二帖评论")
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="我想分析生图软件的市场")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-cross-comment"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="求推荐",
                    description="识别求推荐",
                    positive_signals="求推荐",
                    negative_signals="无",
                    sort_order=1,
                )
            )

            with self.assertRaises(ValueError):
                IntentAnalysisService(repo, client=CrossPostCommentClient()).execute_task(task_id)

            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "failed")

    def test_rejects_post_level_match_with_comment_id(self):
        class PostMatchWithCommentClient(FakeIntentClient):
            def complete_json(self, system_prompt, user_prompt):
                return {
                    "matches": [
                        {
                            "probe_key": "probe-1",
                            "post_id": 1,
                            "comment_id": 1,
                            "level": "post",
                            "score": 90,
                            "reason": "post match should not point to a comment",
                            "excerpt": "post excerpt",
                            "summary": "post summary",
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-post-comment", "xiaohongshu", "生图软件", "default", status="completed")
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-post-comment",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    title="帖子",
                    content="正文",
                    url="local://post-comment/1",
                    detail_fingerprint="post-comment-1",
                )
            )
            repo.save_collected_comment(
                CollectedComment(post_id, "xhs-post-comment", "a", "评论")
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="market")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-post-comment"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="Market need",
                    description="Find market demand",
                    positive_signals="need",
                    negative_signals="none",
                    sort_order=1,
                )
            )

            with self.assertRaisesRegex(ValueError, "Post-level"):
                IntentAnalysisService(repo, client=PostMatchWithCommentClient()).execute_task(task_id)

            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "failed")

    def test_rejects_image_match_when_asset_belongs_to_another_post(self):
        class CrossPostImageClient(FakeIntentClient):
            def __init__(self, asset_id: int):
                super().__init__()
                self.asset_id = asset_id

            def complete_json_multimodal(self, system_prompt, user_prompt, images):
                return {
                    "matches": [
                        {
                            "probe_key": "probe-1",
                            "post_id": 1,
                            "asset_id": self.asset_id,
                            "level": "image",
                            "score": 90,
                            "reason": "wrong post image",
                            "excerpt": "跨帖图片",
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            asset_root = tmp_path / "runtime" / "collector" / "xhs-cross-image" / "assets"
            asset_root.mkdir(parents=True)
            (asset_root / "first.jpg").write_bytes(b"first")
            (asset_root / "second.jpg").write_bytes(b"second")
            repo = FalconRepository(tmp_path / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun("xhs-cross-image", "xiaohongshu", "生图软件", "default", status="completed")
            )
            first_post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-cross-image",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    title="第一帖",
                    content="第一帖正文",
                    url="local://cross-image/1",
                    detail_fingerprint="cross-image-1",
                )
            )
            second_post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-cross-image",
                    platform="xiaohongshu",
                    keyword="生图软件",
                    title="第二帖",
                    content="第二帖正文",
                    url="local://cross-image/2",
                    detail_fingerprint="cross-image-2",
                )
            )
            repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-cross-image",
                    post_id=first_post_id,
                    path="runtime/collector/xhs-cross-image/assets/first.jpg",
                    asset_type="image",
                )
            )
            second_asset_id = repo.save_media_asset(
                MediaAsset(
                    run_id="xhs-cross-image",
                    post_id=second_post_id,
                    path="runtime/collector/xhs-cross-image/assets/second.jpg",
                    asset_type="image",
                )
            )
            task_id = repo.create_intent_analysis_task(
                IntentAnalysisTask(platform="xiaohongshu", user_intent="market")
            )
            repo.add_intent_analysis_sources(task_id, ["xhs-cross-image"])
            repo.save_intent_analysis_probe(
                IntentAnalysisProbe(
                    task_id=task_id,
                    probe_key="probe-1",
                    title="Market need",
                    description="Find market demand",
                    positive_signals="need",
                    negative_signals="none",
                    sort_order=1,
                )
            )

            with self.assertRaisesRegex(ValueError, f"{second_asset_id}"):
                IntentAnalysisService(repo, client=CrossPostImageClient(second_asset_id)).execute_task(task_id)

            self.assertEqual(repo.get_intent_analysis_task(task_id).status, "failed")


if __name__ == "__main__":
    unittest.main()
