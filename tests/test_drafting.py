import unittest

from falcon.analysis import AnalysisResult
from falcon.drafting import DraftingService
from falcon.models import RawItem


class FakeClient:
    def complete_json(self, system_prompt, user_prompt):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return {
            "comment_reply": "封面可以先把标题压到 12 个字以内，再做强对比。",
            "private_message": "看到你在研究小红书封面，我整理过一个轻量做法，可以发你参考。",
            "soft_advice": "先试试标题短一点、主体更大一点，点击率通常更容易判断。",
            "risk_note": "不要承诺爆款，避免广告感。",
        }


class DraftingServiceTest(unittest.TestCase):
    def test_generates_three_drafts_from_gpt55_client(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="小红书封面",
            source_type="comment",
            title="封面怎么做",
            content="小红书封面没人点，有没有工具可以生成？",
            url="https://example.com/note/1",
            published_at="2026-05-11",
        )
        analysis = AnalysisResult(
            scene_tag="xhs_cover",
            intent_score=90,
            content_value_score=86,
            pain_point="封面点击率低",
            suggested_topic="小红书封面没人点？3 个标题图方法",
            recommended_action="comment_reply",
            outreach_type="comment_reply",
            outreach_priority="high",
            reason="明确求工具",
        )

        service = DraftingService(client=FakeClient())
        drafts, risk_note = service.generate(item, analysis)

        self.assertEqual([draft.kind for draft in drafts], ["comment_reply", "private_message", "soft_advice"])
        self.assertIn("标题", drafts[0].text)
        self.assertIn("不要承诺爆款", risk_note)

    def test_falls_back_to_safe_templates_without_client(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="小红书封面",
            source_type="comment",
            title="封面怎么做",
            content="小红书封面没人点",
            url="https://example.com/note/1",
            published_at="2026-05-11",
        )
        analysis = AnalysisResult(
            scene_tag="xhs_cover",
            intent_score=82,
            content_value_score=78,
            pain_point="封面点击率低",
            suggested_topic="小红书封面没人点？",
            recommended_action="comment_reply",
            outreach_type="comment_reply",
            outreach_priority="high",
            reason="明确求助",
        )

        drafts, risk_note = DraftingService(client=None).generate(item, analysis)

        self.assertEqual(len(drafts), 3)
        self.assertTrue(all(draft.text for draft in drafts))
        self.assertIn("人工确认", risk_note)

    def test_fallback_templates_match_probe_scene(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="AI头像",
            source_type="comment",
            title="想换头像",
            content="有没有能做可爱头像的 AI 工具",
            url="https://example.com/note/2",
            published_at="2026-05-11",
        )
        analysis = AnalysisResult(
            scene_tag="avatar",
            intent_score=86,
            content_value_score=80,
            pain_point="想快速生成可用微信头像",
            suggested_topic="想换微信头像？3 种 AI 头像风格可以先试",
            recommended_action="topic_only",
            outreach_type="topic_only",
            outreach_priority="high",
            reason="头像需求",
        )

        drafts, _risk_note = DraftingService(client=None).generate(item, analysis)
        combined = "\n".join(draft.text for draft in drafts)

        self.assertIn("头像", combined)
        self.assertNotIn("小红书封面", combined)


if __name__ == "__main__":
    unittest.main()
