import tempfile
import unittest
from pathlib import Path

from falcon.analysis import AnalysisResult
from falcon.db import FalconRepository
from falcon.models import Draft, RawItem
from falcon.reports import DailyReportBuilder


class DailyReportBuilderTest(unittest.TestCase):
    def test_builds_report_with_topics_keywords_and_outreach_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            raw_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="小红书封面",
                    source_type="comment",
                    title="笔记没人点",
                    content="小红书封面怎么做才有人点？",
                    url="https://example.com/note/1",
                    published_at="2026-05-11",
                )
            )
            analysis = AnalysisResult(
                scene_tag="xhs_cover",
                intent_score=90,
                content_value_score=85,
                pain_point="封面点击率低",
                suggested_topic="小红书封面没人点？3 个标题图方法",
                recommended_action="comment_reply",
                outreach_type="comment_reply",
                outreach_priority="high",
                reason="明确求助",
            )
            analysis_id = repo.save_analysis(raw_id, analysis)
            repo.create_outreach_task(
                raw_id,
                analysis_id,
                analysis,
                [Draft(kind="comment_reply", text="可以先试试标题短一点。")],
                risk_note="避免广告感",
            )

            report = DailyReportBuilder(repo).build_markdown()

            self.assertIn("Falcon 日报", report)
            self.assertIn("小红书封面主报告", report)
            self.assertIn("小红书封面没人点？3 个标题图方法", report)
            self.assertIn("触达任务箱", report)
            self.assertIn("https://example.com/note/1", report)
            self.assertIn(f"raw_id {raw_id}", report)

    def test_can_add_gpt55_summary_when_client_is_provided(self):
        class FakeSummaryClient:
            def complete_json(self, system_prompt, user_prompt):
                self.system_prompt = system_prompt
                self.user_prompt = user_prompt
                return {"summary": "今天优先围绕小红书封面点击率做一篇选题。"}

        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()

            report = DailyReportBuilder(repo, summary_client=FakeSummaryClient()).build_markdown()

            self.assertIn("GPT-5.5 总结", report)
            self.assertIn("今天优先围绕小红书封面点击率", report)

    def test_report_includes_post_content_and_comment_pain_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FalconRepository(Path(tmp) / "falcon.sqlite3")
            repo.init_schema()
            post_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    source_type="post",
                    title="生图工具测评",
                    content="正文：适合做小红书封面、活动海报和标题图。",
                    url="https://example.com/note/post1",
                    author="作者A",
                )
            )
            comment_id = repo.upsert_raw_item(
                RawItem(
                    platform="xiaohongshu",
                    keyword="生图小程序",
                    source_type="comment",
                    title="生图工具测评",
                    content="这个生图工具不好用，求推荐更好用的生图工具",
                    url="https://example.com/note/post1?comment=1",
                    parent_url="https://example.com/note/post1",
                    commenter="用户B",
                    comment_rank="1",
                )
            )
            post_analysis = AnalysisResult(
                scene_tag="xhs_cover",
                intent_score=82,
                content_value_score=88,
                pain_point="封面内容生产需求",
                suggested_topic="生图工具如何做小红书封面",
                recommended_action="topic_only",
                outreach_type="topic_only",
                outreach_priority="medium",
                reason="正文样本",
            )
            comment_analysis = AnalysisResult(
                scene_tag="free",
                intent_score=91,
                content_value_score=89,
                pain_point="当前生图工具不好用，正在求推荐替代工具",
                suggested_topic="比现有生图工具更好用的替代方案",
                recommended_action="comment_reply",
                outreach_type="comment_reply",
                outreach_priority="high",
                reason="评论痛点",
            )
            repo.save_analysis(post_id, post_analysis)
            repo.save_analysis(comment_id, comment_analysis)

            report = DailyReportBuilder(repo).build_markdown()

            self.assertIn("高价值笔记正文", report)
            self.assertIn("正文：适合做小红书封面", report)
            self.assertIn("评论痛点与求推荐信号", report)
            self.assertIn("求推荐更好用的生图工具", report)
            self.assertIn(
                "评论：这个生图工具不好用，求推荐更好用的生图工具（意图 91，来源 https://example.com/note/post1）",
                report,
            )


if __name__ == "__main__":
    unittest.main()
