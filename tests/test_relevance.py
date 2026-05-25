import unittest

from falcon.models import CollectedComment, CollectedPost
from falcon.relevance import default_relevance_result, effective_relevance_level, effective_relevance_role


class DefaultRelevanceTest(unittest.TestCase):
    def test_defaults_collected_posts_to_excellent_primary(self):
        post = CollectedPost(
            run_id="run-1",
            platform="xiaohongshu",
            keyword="账号增长",
            title="周末随手拍真的太好看了",
            content="收藏一些星空壁纸。",
            url="local://post/1",
            author="creator",
        )
        comments = [
            CollectedComment(post_id=1, run_id="run-1", commenter="u", content="好看，收藏了")
        ]

        result = default_relevance_result(post, comments=comments, asset_count=2)

        self.assertEqual(result.score, 100)
        self.assertEqual(result.level, "excellent")
        self.assertEqual(result.analysis_role, "primary")
        self.assertEqual(result.breakdown["default_quality"], 100)
        self.assertIn("默认优质", result.reason)

    def test_manual_relevance_overrides_default_level_and_role(self):
        post = CollectedPost(
            run_id="run-1",
            platform="xiaohongshu",
            keyword="账号增长",
            title="默认优质样本",
            content="采集后默认进入主分析。",
            url="local://post/2",
            author="creator",
            relevance_score=100,
            relevance_level="excellent",
            relevance_role="primary",
            manual_relevance_level="poor",
        )

        self.assertEqual(effective_relevance_level(post), "poor")
        self.assertEqual(effective_relevance_role(post), "discard")


if __name__ == "__main__":
    unittest.main()
