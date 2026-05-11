from typing import List, Optional, Tuple

from .analysis import AnalysisResult
from .models import Draft, RawItem


class DraftingService:
    def __init__(self, client=None):
        self.client = client

    def generate(self, item: RawItem, analysis: AnalysisResult) -> Tuple[List[Draft], str]:
        if analysis.outreach_type == "ignore":
            return [], "低意图样本，不建议触达。"
        if self.client is None:
            return self._fallback(item, analysis)

        payload = self.client.complete_json(
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(item, analysis),
        )
        drafts = [
            Draft(kind="comment_reply", text=self._clean(payload.get("comment_reply"))),
            Draft(kind="private_message", text=self._clean(payload.get("private_message"))),
            Draft(kind="soft_advice", text=self._clean(payload.get("soft_advice"))),
        ]
        risk_note = self._clean(payload.get("risk_note")) or "发送前需人工确认，避免广告感。"
        return drafts, risk_note

    def _fallback(self, item: RawItem, analysis: AnalysisResult) -> Tuple[List[Draft], str]:
        templates = self._fallback_templates(analysis)
        drafts = [Draft(kind=kind, text=text) for kind, text in templates]
        return drafts, "未配置 GPT-5.5 客户端，已使用保守模板；发送前必须人工确认。"

    def _fallback_templates(self, analysis: AnalysisResult) -> List[Tuple[str, str]]:
        topic = analysis.suggested_topic.rstrip("。")
        if analysis.scene_tag == "avatar":
            return [
                ("comment_reply", f"头像可以先定一个明确风格，比如治愈、软萌或轻复古，再生成几版对比。{topic}这个方向挺适合先试。"),
                ("private_message", "看到你在找头像工具，可以先从风格关键词入手，不一定要复杂描述。需要的话我可以发你一个轻量生成思路。"),
                ("soft_advice", "先选一个主风格，再补充人物/宠物/颜色氛围，头像会更稳定。"),
            ]
        if analysis.scene_tag == "poster":
            return [
                ("comment_reply", f"活动海报可以先把优惠、时间、地点三件事排清楚，再补风格。{topic}这个方向可以直接做成模板。"),
                ("private_message", "看到你在做活动海报，我建议先把核心优惠写短，再生成竖版海报，会更适合转发。"),
                ("soft_advice", "先把最重要的一句优惠放大，其他信息收在下面，海报会更清楚。"),
            ]
        if analysis.scene_tag == "moments":
            return [
                ("comment_reply", f"朋友圈背景可以先写情绪关键词，再补场景和色调。{topic}这个方向挺容易出氛围。"),
                ("private_message", "看到你在找朋友圈背景图，可以先用情绪词 + 场景词生成，比如松弛、海边、傍晚。"),
                ("soft_advice", "先选情绪，再选场景，最后补一个主色调，背景图会更统一。"),
            ]
        if analysis.scene_tag == "free":
            return [
                ("comment_reply", f"一句话生图可以把主体、场景、风格三个信息写清楚。{topic}这个方向适合先试。"),
                ("private_message", "看到你在试 AI 生图，可以先用“主体 + 场景 + 风格”的句式，效果通常更稳定。"),
                ("soft_advice", "描述里别只写风格，补上主体和场景会更容易出想要的画面。"),
            ]
        return [
            (
                "comment_reply",
                f"可以先从标题和主体层级入手：标题短一点、主体大一点，会更容易判断封面点击感。{topic}这个方向也挺适合整理成模板。",
            ),
            (
                "private_message",
                "看到你在研究小红书封面，我这边整理过一个轻量做法：先定标题重点，再选风格生成首图。你需要的话我可以发你参考。",
            ),
            (
                "soft_advice",
                "先不急着追求复杂设计，可以试试一个明确标题 + 一个大主体 + 少量贴纸元素，先看点击反馈。",
            ),
        ]

    def _system_prompt(self) -> str:
        return (
            "你是 AI出图助手 的小红书运营助理。你只生成待人工确认的评论/私信草稿，"
            "不能假装已经发送，不能承诺必爆款，不能制造骚扰感。语气像真实用户给建议，"
            "先给一个可执行建议，再自然提到可以用工具生成。输出 JSON。"
        )

    def _user_prompt(self, item: RawItem, analysis: AnalysisResult) -> str:
        return (
            "请基于以下小红书公开内容生成 3 条草稿：\n"
            "1. comment_reply：公开评论区回复，克制、短。\n"
            "2. private_message：私信草稿，更克制，不强推。\n"
            "3. soft_advice：只给建议、不引流。\n"
            "同时给出 risk_note。\n\n"
            f"关键词：{item.keyword}\n"
            f"标题：{item.title}\n"
            f"内容：{item.content}\n"
            f"痛点：{analysis.pain_point}\n"
            f"建议选题：{analysis.suggested_topic}\n"
            f"意图分：{analysis.intent_score}\n"
        )

    def _clean(self, value: Optional[str]) -> str:
        return str(value or "").strip()
