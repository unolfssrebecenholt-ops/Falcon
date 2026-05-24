import tempfile
import unittest
from pathlib import Path

from falcon.db import FalconRepository
from falcon.models import (
    CollectedComment,
    CollectedPost,
    CollectionEvent,
    CollectionRun,
    Evidence,
    MediaAsset,
)


class CollectorRepositoryTest(unittest.TestCase):
    def make_repo(self, tmp: str) -> FalconRepository:
        repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
        repo.init_schema()
        return repo

    def test_collection_run_lifecycle_and_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)

            repo.create_collection_run(
                CollectionRun(
                    run_id="run-1",
                    platform="xiaohongshu",
                    keyword="cover design",
                    profile="default",
                )
            )
            repo.create_collection_run(
                CollectionRun(
                    run_id="run-2",
                    platform="xiaohongshu",
                    keyword="image app",
                    profile="creator",
                    status="manual_action_required",
                )
            )
            repo.update_collection_run(
                "run-1",
                status="completed",
                progress=100,
                current_step="saved posts",
                completed_at="2026-05-23T10:00:00+00:00",
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="run-1",
                    platform="xiaohongshu",
                    keyword="cover design",
                    title="Useful cover",
                    content="A useful post",
                    url="https://example.test/post/1",
                    detail_fingerprint="fp-1",
                )
            )

            run = repo.get_collection_run("run-1")
            runs = repo.list_collection_runs()
            dashboard = repo.collector_dashboard()

            self.assertIsNotNone(run)
            self.assertEqual(run.status, "completed")
            self.assertEqual(run.progress, 100)
            self.assertEqual(run.current_step, "saved posts")
            self.assertEqual(run.completed_at, "2026-05-23T10:00:00+00:00")
            self.assertEqual([item.run_id for item in runs], ["run-2", "run-1"])
            self.assertEqual(
                dashboard,
                {
                    "total_runs": 2,
                    "running_runs": 0,
                    "waiting_manual_runs": 1,
                    "failed_runs": 0,
                    "completed_runs": 1,
                    "total_posts": 1,
                },
            )

    def test_collection_events_preserve_sequence_then_insert_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            repo.create_collection_run(
                CollectionRun(
                    run_id="run-events",
                    platform="xiaohongshu",
                    keyword="cover design",
                    profile="default",
                )
            )

            second_id = repo.append_collection_event(
                CollectionEvent(
                    run_id="run-events",
                    sequence=2,
                    scope="search",
                    event="scroll",
                    message="Scrolled results",
                )
            )
            first_id = repo.append_collection_event(
                CollectionEvent(
                    run_id="run-events",
                    sequence=1,
                    scope="search",
                    event="open",
                    message="Opened search",
                    level="debug",
                    payload_json='{"query":"cover design"}',
                )
            )
            tie_id = repo.append_collection_event(
                CollectionEvent(
                    run_id="run-events",
                    sequence=2,
                    scope="detail",
                    event="click",
                    message="Opened detail",
                )
            )

            events = repo.list_collection_events("run-events")

            self.assertEqual([event.event_id for event in events], [first_id, second_id, tie_id])
            self.assertEqual([event.sequence for event in events], [1, 2, 2])
            self.assertEqual(events[0].payload_json, '{"query":"cover design"}')
            self.assertEqual(events[0].level, "debug")

    def test_collected_posts_dedupe_by_fingerprint_then_fallback_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            repo.create_collection_run(
                CollectionRun(
                    run_id="run-posts",
                    platform="xiaohongshu",
                    keyword="cover design",
                    profile="default",
                )
            )

            fingerprint_id = repo.save_collected_post(
                CollectedPost(
                    run_id="run-posts",
                    platform="xiaohongshu",
                    keyword="cover design",
                    title="Original title",
                    content="Original content",
                    url="https://example.test/post/a",
                    detail_fingerprint="same-fingerprint",
                )
            )
            duplicate_fingerprint_id = repo.save_collected_post(
                CollectedPost(
                    run_id="run-posts",
                    platform="xiaohongshu",
                    keyword="cover design",
                    title="Changed title",
                    content="Changed content",
                    url="https://example.test/post/b",
                    detail_fingerprint="same-fingerprint",
                )
            )
            fallback_id = repo.save_collected_post(
                CollectedPost(
                    run_id="run-posts",
                    platform="xiaohongshu",
                    keyword="cover design",
                    title="Fallback title",
                    content="Fallback content",
                    url="https://example.test/post/fallback",
                )
            )
            duplicate_fallback_id = repo.save_collected_post(
                CollectedPost(
                    run_id="run-posts",
                    platform="xiaohongshu",
                    keyword="cover design",
                    title="Fallback title",
                    content="Different content",
                    url="https://example.test/post/fallback",
                )
            )

            posts = repo.list_collected_posts("run-posts")

            self.assertEqual(fingerprint_id, duplicate_fingerprint_id)
            self.assertEqual(fallback_id, duplicate_fallback_id)
            self.assertEqual([post.post_id for post in posts], [fingerprint_id, fallback_id])
            self.assertEqual(posts[0].title, "Original title")
            self.assertEqual(posts[1].detail_fingerprint, "")

    def test_media_assets_and_evidences_are_listed_for_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            repo.create_collection_run(
                CollectionRun(
                    run_id="run-assets",
                    platform="xiaohongshu",
                    keyword="cover design",
                    profile="default",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="run-assets",
                    platform="xiaohongshu",
                    keyword="cover design",
                    title="Asset post",
                    content="Asset content",
                    url="https://example.test/post/assets",
                    detail_fingerprint="asset-fp",
                )
            )

            asset_id = repo.save_media_asset(
                MediaAsset(
                    run_id="run-assets",
                    post_id=post_id,
                    path="runtime/collector/run-assets/media/cover.jpg",
                    asset_type="image",
                    url="https://example.test/cover.jpg",
                    sha256="abc123",
                )
            )
            evidence_id = repo.save_evidence(
                Evidence(
                    run_id="run-assets",
                    evidence_type="screenshot",
                    path="runtime/collector/run-assets/evidence/search.png",
                    scope="search",
                    payload_json='{"step":"search"}',
                )
            )

            assets = repo.list_media_assets("run-assets")
            evidences = repo.list_evidences("run-assets")

            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0].asset_id, asset_id)
            self.assertEqual(assets[0].post_id, post_id)
            self.assertEqual(assets[0].asset_type, "image")
            self.assertEqual(len(evidences), 1)
            self.assertEqual(evidences[0].evidence_id, evidence_id)
            self.assertEqual(evidences[0].scope, "search")

    def test_collected_posts_and_comments_store_collects_and_reply_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            repo.create_collection_run(
                CollectionRun(
                    run_id="run-replies",
                    platform="xiaohongshu",
                    keyword="cover design",
                    profile="default",
                )
            )
            post_id = repo.save_collected_post(
                CollectedPost(
                    run_id="run-replies",
                    platform="xiaohongshu",
                    keyword="cover design",
                    title="Reply post",
                    content="Post content",
                    url="https://example.test/post/replies",
                    like_count="24",
                    collect_count="10",
                    comment_count="37",
                    detail_fingerprint="reply-fp",
                )
            )

            comment_id = repo.save_collected_comment(
                CollectedComment(
                    post_id=post_id,
                    run_id="run-replies",
                    commenter="replyer",
                    content="nested reply content",
                    like_count="1",
                    comment_rank="2",
                    comment_type="reply",
                    reply_to="target user",
                )
            )

            post = repo.get_collected_post(post_id)
            comments = repo.list_collected_comments(run_id="run-replies", post_id=post_id)

            self.assertEqual(post.collect_count, "10")
            self.assertEqual(comments[0].comment_id, comment_id)
            self.assertEqual(comments[0].comment_type, "reply")
            self.assertEqual(comments[0].reply_to, "target user")


if __name__ == "__main__":
    unittest.main()
