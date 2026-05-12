from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Tuple

from .models import RawItem


@dataclass
class AnalysisResult:
    scene_tag: str
    intent_score: int
    content_value_score: int
    pain_point: str
    suggested_topic: str
    recommended_action: str
    outreach_type: str
    outreach_priority: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class HeuristicAnalyzer:
    """Deterministic first-pass analyzer for low-volume MVP validation.

    GPT can replace or augment this later, but the MVP keeps a predictable
    fallback so imports, reports, and reviews work without a configured key.
    """

    SCENE_KEYWORDS: Dict[str, List[str]] = {
        "xhs_cover": [
            "小红书封面",
            "封面",
            "标题图",
            "首图",
            "笔记没人看",
            "点击率",
            "爆款封面",
            "笔记封面",
        ],
        "poster": ["海报", "活动", "促销", "门店", "开业", "团购", "课程"],
        "avatar": ["头像", "微信头像", "ai头像", "AI头像", "情侣头像", "宠物头像"],
        "moments": ["朋友圈背景", "朋友圈封面", "背景图", "朋友圈主页"],
        "free": ["生图", "画画", "AI绘画", "ai绘画", "生成图片", "图片生成"],
    }

    ACTION_SIGNALS = [
        "怎么",
        "有没有",
        "求",
        "推荐",
        "工具",
        "模板",
        "教程",
        "不会",
        "太难",
        "自动生成",
        "生成",
        "平替",
        "替代",
        "更好用",
        "?",
        "？",
    ]

    PAIN_SIGNALS = ["没人看", "没人点", "点击", "排版", "不好看", "不好用", "不会做", "难", "救命", "求助"]
    NOISE_SIGNALS = ["哈哈", "路过", "围观", "好可爱", "好看", "蹲", "收藏了"]

    def analyze(self, item: RawItem) -> AnalysisResult:
        text = self._normalize(" ".join([item.keyword, item.title, item.content]))
        scene_tag, scene_hits = self._detect_scene(text)
        action_hits = self._hits(text, self.ACTION_SIGNALS)
        pain_hits = self._hits(text, self.PAIN_SIGNALS)
        noise_hits = self._hits(text, self.NOISE_SIGNALS)

        score = 20
        if scene_hits:
            score += min(35, 18 + len(scene_hits) * 8)
        if action_hits:
            score += min(30, 12 + len(action_hits) * 6)
        if pain_hits:
            score += min(20, 8 + len(pain_hits) * 5)
        if item.source_type == "comment":
            score += 5
        if noise_hits and not action_hits:
            score -= 25
        if not scene_hits:
            score -= 20

        intent_score = self._clamp(score)
        content_value_score = self._content_value(intent_score, scene_tag, action_hits, pain_hits)
        recommended_action = self._recommended_action(item, scene_tag, intent_score, content_value_score)
        outreach_type = self._outreach_type(recommended_action)
        outreach_priority = self._priority(intent_score)
        pain_point = self._pain_point(scene_tag, pain_hits)
        suggested_topic = self._suggested_topic(scene_tag, pain_point)
        reason = self._reason(scene_tag, scene_hits, action_hits, pain_hits, intent_score)

        return AnalysisResult(
            scene_tag=scene_tag,
            intent_score=intent_score,
            content_value_score=content_value_score,
            pain_point=pain_point,
            suggested_topic=suggested_topic,
            recommended_action=recommended_action,
            outreach_type=outreach_type,
            outreach_priority=outreach_priority,
            reason=reason,
        )

    def _detect_scene(self, text: str) -> Tuple[str, List[str]]:
        best_scene = "unknown"
        best_hits: List[str] = []
        for scene, keywords in self.SCENE_KEYWORDS.items():
            hits = self._hits(text, keywords)
            if len(hits) > len(best_hits):
                best_scene = scene
                best_hits = hits
        return best_scene, best_hits

    def _content_value(self, intent_score: int, scene_tag: str, action_hits: Iterable[str], pain_hits: Iterable[str]) -> int:
        value = intent_score - 8
        if scene_tag == "xhs_cover":
            value += 8
        if action_hits:
            value += 5
        if pain_hits:
            value += 5
        return self._clamp(value)

    def _recommended_action(self, item: RawItem, scene_tag: str, intent_score: int, content_value_score: int) -> str:
        if intent_score < 60:
            return "ignore"
        if item.source_type == "comment" and intent_score >= 75:
            return "comment_reply"
        if scene_tag == "xhs_cover" and intent_score >= 80:
            return "comment_reply" if item.source_type == "comment" else "topic_only"
        if content_value_score >= 75:
            return "topic_only"
        return "topic_only" if intent_score >= 60 else "ignore"

    def _outreach_type(self, recommended_action: str) -> str:
        if recommended_action == "comment_reply":
            return "comment_reply"
        if recommended_action == "private_message":
            return "private_message"
        if recommended_action == "topic_only":
            return "topic_only"
        return "ignore"

    def _priority(self, intent_score: int) -> str:
        if intent_score >= 85:
            return "high"
        if intent_score >= 70:
            return "medium"
        return "low"

    def _pain_point(self, scene_tag: str, pain_hits: Iterable[str]) -> str:
        if scene_tag == "xhs_cover":
            return "小红书封面点击率或排版问题"
        if scene_tag == "poster":
            return "需要快速生成可发布活动海报"
        if scene_tag == "avatar":
            return "想快速生成可用微信头像"
        if scene_tag == "moments":
            return "想生成朋友圈背景表达状态"
        if scene_tag == "free":
            return "想用一句话生成图片"
        if pain_hits:
            return "表达了图片生成相关痛点"
        return "暂无明确痛点"

    def _suggested_topic(self, scene_tag: str, pain_point: str) -> str:
        topics = {
            "xhs_cover": "小红书封面没人点？3 个标题图排版方法",
            "poster": "门店活动海报怎么做？一张图说清优惠信息",
            "avatar": "想换微信头像？3 种 AI 头像风格可以先试",
            "moments": "朋友圈背景图怎么做得有氛围感？",
            "free": "一句话生图怎么玩？把脑洞变成可保存图片",
        }
        return topics.get(scene_tag, pain_point)

    def _reason(
        self,
        scene_tag: str,
        scene_hits: Iterable[str],
        action_hits: Iterable[str],
        pain_hits: Iterable[str],
        intent_score: int,
    ) -> str:
        parts = [f"场景={scene_tag}", f"意图分={intent_score}"]
        if scene_hits:
            parts.append("命中场景词：" + "、".join(scene_hits))
        if action_hits:
            parts.append("命中行动词：" + "、".join(action_hits))
        if pain_hits:
            parts.append("命中痛点词：" + "、".join(pain_hits))
        return "；".join(parts)

    def _hits(self, text: str, keywords: Iterable[str]) -> List[str]:
        return [keyword for keyword in keywords if self._normalize(keyword) in text]

    def _normalize(self, value: str) -> str:
        return value.lower().strip()

    def _clamp(self, value: int) -> int:
        return max(0, min(100, int(value)))
