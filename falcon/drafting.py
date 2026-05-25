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
        if analysis.scene_tag == "brand_asset":
            return [
                ("comment_reply", f"品牌视觉可以先定主色、语气和核心元素，再做几版对比。{topic}这个方向适合整理成规范。"),
                ("private_message", "看到你在梳理账号形象，可以先从主色、关键词和参考样式入手，后续再扩展成素材模板。"),
                ("soft_advice", "先固定 2-3 个视觉关键词，再补充使用场景，产出的素材会更统一。"),
            ]
        if analysis.scene_tag == "marketing_asset":
            return [
                ("comment_reply", f"营销素材可以先把目标用户、利益点和行动入口写清楚，再补版式。{topic}这个方向可以做成模板。"),
                ("private_message", "看到你在准备营销素材，我建议先把核心利益点压缩成一句话，再围绕渠道尺寸做适配。"),
                ("soft_advice", "先突出最重要的一句利益点，次要信息放到下方，用户会更容易判断要不要行动。"),
            ]
        if analysis.scene_tag == "audience_growth":
            return [
                ("comment_reply", f"可以先把用户问题按频率分组，再给每类准备不同回复路径。{topic}这个方向适合做成复盘表。"),
                ("private_message", "看到你在看互动和转化，可以先统计评论里重复出现的问题，再决定内容和跟进优先级。"),
                ("soft_advice", "先把高频问题、行动意图和可承接动作分开，后面判断优先级会更清楚。"),
            ]
        if analysis.scene_tag == "tool_workflow":
            return [
                ("comment_reply", f"可以先把重复动作拆成采集、整理、判断和执行四段，再看哪一段最值得自动化。{topic}"),
                ("private_message", "看到你在找更顺的工具流程，可以先列出每天重复做的 3 个动作，再判断是否需要自动化。"),
                ("soft_advice", "先自动化低风险的整理和预览动作，高风险执行动作保留人工确认。"),
            ]
        return [
            (
                "comment_reply",
                f"可以先从目标、用户问题和行动入口入手，把信息层级排清楚。{topic}这个方向也适合整理成复用模板。",
            ),
            (
                "private_message",
                "看到你在研究内容运营流程，我这边建议先把目标、样本和判断标准拆开，再决定下一步动作。",
            ),
            (
                "soft_advice",
                "先不急着扩大动作规模，可以用少量样本验证判断标准，再逐步固化流程。",
            ),
        ]

    def _system_prompt(self) -> str:
        return (
            "你是 Falcon 平台里的内容运营分析助手。你只生成待人工确认的评论、私信或跟进草稿，"
            "不能假装已经发送，不能承诺必爆款，不能制造骚扰感。语气像真实用户给建议，"
            "先给一个可执行建议，再自然说明可以用工具或流程提高效率。输出 JSON。"
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
