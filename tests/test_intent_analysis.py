import tempfile
import unittest
from pathlib import Path

from falcon.db import FalconRepository
from falcon.intent_analysis import IntentAnalysisService
from falcon.models import (
    CollectedComment,
    CollectedPost,
    CollectionRun,
    IntentAnalysisMatch,
    IntentAnalysisProbe,
    IntentAnalysisTask,
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


if __name__ == "__main__":
    unittest.main()
