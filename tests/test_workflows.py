import tempfile
import unittest
from pathlib import Path

from falcon.db import FalconRepository
from falcon.models import CollectedPost, CollectionRun, RawItem
from falcon.workflows import analyze_unanalyzed, promote_collected_posts, score_collected_posts, write_report


class WorkflowTest(unittest.TestCase):
    def test_analyze_and_report_workflow_uses_repository_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "falcon.sqlite3"
            report_path = tmp_path / "daily-report.md"
            repo = FalconRepository(db_path)
            repo.init_schema()
            repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    source_type="post",
                    title="小红书封面怎么做才有人点？",
                    content="想找一个能直接生成封面标题图的工具。",
                    url="local://seed/1",
                )
            )

            result = analyze_unanalyzed(repo, drafts_mode="template")
            output = write_report(repo, report_path)

            self.assertEqual(result.analyzed_count, 1)
            self.assertEqual(output, report_path)
            self.assertTrue(report_path.exists())
            self.assertIn("Falcon 日报", report_path.read_text(encoding="utf-8"))

    def test_promote_collected_posts_feeds_existing_analysis_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-analysis",
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    profile="default",
                    status="completed",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-analysis",
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    title="小红书封面怎么做才有人点？",
                    content="想找一个能直接生成封面标题图的工具。",
                    url="local://collector/xhs-analysis/post-1",
                    author="小红书用户",
                    like_count="128",
                    comment_count="6",
                    detail_fingerprint="analysis-post-1",
                )
            )

            score_collected_posts(repo, run_id="xhs-analysis")
            promoted = promote_collected_posts(repo, run_id="xhs-analysis")
            result = analyze_unanalyzed(repo, drafts_mode="template")

            self.assertEqual(promoted, 1)
            self.assertEqual(result.analyzed_count, 1)
            self.assertEqual(result.task_count, 1)
            raw_item = repo.list_raw_items()[0]
            self.assertEqual(raw_item.platform, "xiaohongshu")
            self.assertEqual(raw_item.author, "小红书用户")
            self.assertEqual(raw_item.like_count, "128")

    def test_promote_collected_posts_defaults_all_samples_to_primary_unless_manual_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            repo.create_collection_run(
                CollectionRun(
                    run_id="xhs-relevance",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    profile="default",
                    status="completed",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-relevance",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    title="AI头像生成工具测评",
                    content="这篇笔记完整对比了 AI头像 的风格、价格和使用场景，适合做需求分析。",
                    url="local://collector/xhs-relevance/post-1",
                    author="creator",
                    like_count="128",
                    comment_count="6",
                    detail_fingerprint="relevance-post-1",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-relevance",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    title="AI绘画头像风格整理",
                    content="整理一些头像风格和关键词，可作为选题参考。",
                    url="local://collector/xhs-relevance/post-2",
                    author="creator",
                    detail_fingerprint="relevance-post-2",
                )
            )
            repo.save_collected_post(
                CollectedPost(
                    run_id="xhs-relevance",
                    platform="xiaohongshu",
                    keyword="AI头像",
                    title="宇宙壁纸真的太好看了",
                    content="收藏一些星空壁纸，完全没有头像制作或 AI 生成需求。",
                    url="local://collector/xhs-relevance/post-3",
                    author="creator",
                    like_count="9999",
                    detail_fingerprint="relevance-post-3",
                )
            )

            score_collected_posts(repo, run_id="xhs-relevance")
            promoted = promote_collected_posts(repo, run_id="xhs-relevance", return_summary=True)
            result = analyze_unanalyzed(repo, drafts_mode="template")

            self.assertEqual(promoted.primary_count, 3)
            self.assertEqual(promoted.reference_count, 0)
            self.assertEqual(promoted.discarded_count, 0)
            self.assertEqual(promoted.promoted_count, 3)
            raw_items = repo.list_raw_items()
            self.assertEqual([item.relevance_role for item in raw_items], ["primary", "primary", "primary"])
            self.assertEqual([item.relevance_score for item in raw_items], [100, 100, 100])
            self.assertEqual(result.analyzed_count, 3)
            self.assertEqual(result.task_count, 2)


if __name__ == "__main__":
    unittest.main()
