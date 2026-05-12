import unittest

from falcon.analysis import HeuristicAnalyzer
from falcon.models import RawItem


class HeuristicAnalyzerTest(unittest.TestCase):
    def test_scores_xhs_cover_help_request_as_high_intent_comment_reply(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="小红书封面",
            source_type="comment",
            title="笔记没人看",
            content="小红书封面怎么做才有人点？有没有自动生成标题图的工具，排版太难了",
            url="https://example.com/note/1",
            published_at="2026-05-11",
        )

        result = HeuristicAnalyzer().analyze(item)

        self.assertEqual(result.scene_tag, "xhs_cover")
        self.assertGreaterEqual(result.intent_score, 80)
        self.assertGreaterEqual(result.content_value_score, 70)
        self.assertEqual(result.recommended_action, "comment_reply")
        self.assertEqual(result.outreach_type, "comment_reply")
        self.assertIn("小红书封面", result.suggested_topic)

    def test_downgrades_generic_chatter_to_ignore(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="小红书封面",
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

    def test_detects_probe_scene_for_avatar_requests(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="AI头像",
            source_type="post",
            title="想换一个微信头像",
            content="有没有能做可爱头像的 AI 工具，最好可以直接生成微信头像",
            url="https://example.com/note/3",
            published_at="2026-05-11",
        )

        result = HeuristicAnalyzer().analyze(item)

        self.assertEqual(result.scene_tag, "avatar")
        self.assertGreaterEqual(result.intent_score, 60)

    def test_scores_tool_recommendation_comment_as_high_intent(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="生图小程序",
            source_type="comment",
            title="生图工具测评",
            content="现在这个生图工具不好用，求推荐更好用的生图工具，有没有平替？",
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
