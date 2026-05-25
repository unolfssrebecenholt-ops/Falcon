import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List


FIELDNAMES = ["theme", "keyword", "scene", "weight", "daily_limit"]


@dataclass
class KeywordTask:
    theme: str
    keyword: str
    scene: str
    weight: int
    daily_limit: int


DEFAULT_KEYWORDS = [
    ("内容运营自动化", "workflow", 10, 20),
    ("竞品内容分析", "analysis", 9, 15),
    ("账号增长策略", "growth", 8, 15),
    ("爆款内容拆解", "content_performance", 8, 15),
    ("用户评论分析", "audience_growth", 7, 12),
    ("营销素材管理", "marketing_asset", 6, 10),
    ("运营日报自动化", "reporting", 5, 10),
]

PROGRAM_INTENT_PATTERNS = [
    ("{program_name}怎么做", "workflow", 10, 10),
    ("{program_name}工具推荐", "tool_recommendation", 10, 10),
    ("有没有好用的{program_name}工具", "tool_recommendation", 9, 10),
    ("{program_name}自动化", "automation", 8, 8),
    ("{program_name}教程", "tutorial", 7, 8),
    ("{program_name}案例", "case_study", 7, 8),
    ("{program_name}数据分析", "analysis", 8, 8),
    ("{program_name}复盘模板", "reporting", 6, 8),
]


def default_keyword_tasks(theme: str) -> List[KeywordTask]:
    scenario_tasks = [
        KeywordTask(
            theme=theme,
            keyword=keyword,
            scene=scene,
            weight=weight,
            daily_limit=daily_limit,
        )
        for keyword, scene, weight, daily_limit in DEFAULT_KEYWORDS
    ]
    return scenario_tasks + generate_program_keyword_tasks(theme)


def generate_program_keyword_tasks(program_name: str) -> List[KeywordTask]:
    program_name = program_name.strip()
    return [
        KeywordTask(
            theme=program_name,
            keyword=pattern.format(program_name=program_name),
            scene=scene,
            weight=weight,
            daily_limit=daily_limit,
        )
        for pattern, scene, weight, daily_limit in PROGRAM_INTENT_PATTERNS
    ]


def write_default_keyword_pool(path: Path, theme: str) -> List[KeywordTask]:
    tasks = default_keyword_tasks(theme)
    write_keyword_tasks(path, tasks)
    return tasks


def write_keyword_tasks(path: Path, tasks: List[KeywordTask]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for task in tasks:
            writer.writerow(
                {
                    "theme": task.theme,
                    "keyword": task.keyword,
                    "scene": task.scene,
                    "weight": task.weight,
                    "daily_limit": task.daily_limit,
                }
            )


def load_keyword_tasks(path: Path) -> List[KeywordTask]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [_row_to_task(row) for row in reader if row.get("keyword")]


def _row_to_task(row: dict) -> KeywordTask:
    return KeywordTask(
        theme=(row.get("theme") or "").strip(),
        keyword=(row.get("keyword") or "").strip(),
        scene=(row.get("scene") or "").strip(),
        weight=int(row.get("weight") or 0),
        daily_limit=int(row.get("daily_limit") or 0),
    )
