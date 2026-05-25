import unittest

from falcon.analysis import HeuristicAnalyzer
from falcon.models import RawItem


class HeuristicAnalyzerTest(unittest.TestCase):
    def test_scores_content_performance_help_request_as_high_intent_comment_reply(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="内容表现",
            source_type="comment",
            title="内容没人看",
            content="标题和首图怎么做才有人点？有没有自动化分析工具，排版和表达太难了",
            url="https://example.com/note/1",
            published_at="2026-05-11",
        )

        result = HeuristicAnalyzer().analyze(item)

        self.assertEqual(result.scene_tag, "content_performance")
        self.assertGreaterEqual(result.intent_score, 80)
        self.assertGreaterEqual(result.content_value_score, 70)
        self.assertEqual(result.recommended_action, "comment_reply")
        self.assertEqual(result.outreach_type, "comment_reply")
        self.assertIn("内容", result.suggested_topic)

    def test_downgrades_generic_chatter_to_ignore(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="内容表现",
            source_type="comment",
            title="随便聊聊",
            content="哈哈这个颜色好可爱，路过看看",
            url="https://example.com/note/2",
            published_at="2026-05-11",
        )

        result = HeuristicAnalyzer().analyze(item)

        self.assertLess(result.intent_score, 60)
        self.assertEqual(result.recommended_action, "ignore")
        self.assertEqual(result.outreach_type, "ignore")

    def test_detects_brand_asset_requests(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="账号增长",
            source_type="post",
            title="想统一账号形象",
            content="有没有能管理品牌图和视觉风格的工具，最好可以沉淀成模板",
            url="https://example.com/note/3",
            published_at="2026-05-11",
        )

        result = HeuristicAnalyzer().analyze(item)

        self.assertEqual(result.scene_tag, "brand_asset")
        self.assertGreaterEqual(result.intent_score, 60)

    def test_scores_tool_recommendation_comment_as_high_intent(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="内容运营",
            source_type="comment",
            title="运营工具测评",
            content="现在这个运营工具不好用，求推荐更好用的自动化工具，有没有替代方案？",
            url="https://example.com/note/4?comment=1",
            parent_url="https://example.com/note/4",
        )

        result = HeuristicAnalyzer().analyze(item)

        self.assertGreaterEqual(result.intent_score, 80)
        self.assertEqual(result.recommended_action, "comment_reply")
        self.assertEqual(result.outreach_type, "comment_reply")
        self.assertIn("工具", result.reason)


if __name__ == "__main__":
    unittest.main()
