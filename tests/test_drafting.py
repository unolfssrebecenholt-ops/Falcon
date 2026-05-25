import unittest

from falcon.analysis import AnalysisResult
from falcon.drafting import DraftingService
from falcon.models import RawItem


class FakeClient:
    def complete_json(self, system_prompt, user_prompt):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return {
            "comment_reply": "内容可以先把标题压到 12 个字以内，再明确利益点。",
            "private_message": "看到你在研究内容表现，我整理过一个轻量复盘方法，可以发你参考。",
            "soft_advice": "先试试标题短一点、行动入口更明确一点，点击率通常更容易判断。",
            "risk_note": "不要承诺爆款，避免广告感。",
        }


class DraftingServiceTest(unittest.TestCase):
    def test_generates_three_drafts_from_gpt55_client(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="内容表现",
            source_type="comment",
            title="标题怎么做",
            content="内容没人点，有没有工具可以分析？",
            url="https://example.com/note/1",
            published_at="2026-05-11",
        )
        analysis = AnalysisResult(
            scene_tag="content_performance",
            intent_score=90,
            content_value_score=86,
            pain_point="内容点击率低",
            suggested_topic="内容没人点？3 个表达结构方法",
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
            keyword="内容表现",
            source_type="comment",
            title="标题怎么做",
            content="内容没人点",
            url="https://example.com/note/1",
            published_at="2026-05-11",
        )
        analysis = AnalysisResult(
            scene_tag="content_performance",
            intent_score=82,
            content_value_score=78,
            pain_point="内容点击率低",
            suggested_topic="内容没人点？",
            recommended_action="comment_reply",
            outreach_type="comment_reply",
            outreach_priority="high",
            reason="明确求助",
        )

        drafts, risk_note = DraftingService(client=None).generate(item, analysis)

        self.assertEqual(len(drafts), 3)
        self.assertTrue(all(draft.text for draft in drafts))
        self.assertIn("人工确认", risk_note)

    def test_fallback_templates_match_brand_asset_scene(self):
        item = RawItem(
            platform="xiaohongshu",
            keyword="账号增长",
            source_type="comment",
            title="想统一账号形象",
            content="有没有能管理品牌图和视觉风格的工具",
            url="https://example.com/note/2",
            published_at="2026-05-11",
        )
        analysis = AnalysisResult(
            scene_tag="brand_asset",
            intent_score=86,
            content_value_score=80,
            pain_point="需要统一品牌视觉或账号形象",
            suggested_topic="账号视觉怎么统一？先建立可复用的品牌表达规范",
            recommended_action="topic_only",
            outreach_type="topic_only",
            outreach_priority="high",
            reason="账号形象需求",
        )

        drafts, _risk_note = DraftingService(client=None).generate(item, analysis)
        combined = "\n".join(draft.text for draft in drafts)

        self.assertIn("品牌", combined)
        self.assertNotIn("小红书封面", combined)


if __name__ == "__main__":
    unittest.main()
