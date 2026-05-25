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
        "content_performance": [
            "内容表现",
            "标题",
            "封面",
            "首图",
            "点击率",
            "转化率",
            "没人看",
            "没人点",
            "爆款",
            "笔记封面",
        ],
        "marketing_asset": ["海报", "活动", "促销", "门店", "开业", "团购", "课程", "素材", "落地页"],
        "brand_asset": ["品牌图", "主视觉", "logo", "Logo", "账号形象", "品牌形象", "视觉风格"],
        "audience_growth": ["粉丝", "涨粉", "互动", "评论", "私域", "社群", "转化", "留资"],
        "tool_workflow": ["工具", "模板", "流程", "工作流", "自动化", "批量", "数据", "采集", "分析", "报表"],
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
        if scene_tag == "content_performance":
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
        if scene_tag == "content_performance" and intent_score >= 80:
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
        if scene_tag == "content_performance":
            return "内容点击率、表达结构或转化表现问题"
        if scene_tag == "marketing_asset":
            return "需要快速整理可发布的营销素材"
        if scene_tag == "brand_asset":
            return "需要统一品牌视觉或账号形象"
        if scene_tag == "audience_growth":
            return "需要提升互动、转化或用户沉淀效率"
        if scene_tag == "tool_workflow":
            return "需要更高效的工具流程或自动化方案"
        if pain_hits:
            return "表达了明确的运营痛点"
        return "暂无明确痛点"

    def _suggested_topic(self, scene_tag: str, pain_point: str) -> str:
        topics = {
            "content_performance": "内容没人点？先检查标题、首图和利益点",
            "marketing_asset": "活动素材怎么做？先把目标、利益点和行动入口说清楚",
            "brand_asset": "账号视觉怎么统一？先建立可复用的品牌表达规范",
            "audience_growth": "互动和转化怎么提升？先拆评论需求和行动路径",
            "tool_workflow": "运营流程太慢？先找出可自动化的重复步骤",
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
