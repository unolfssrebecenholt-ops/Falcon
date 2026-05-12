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
    ("小红书封面", "cover", 10, 20),
    ("小红书标题图", "cover", 9, 15),
    ("封面怎么做", "cover", 8, 15),
    ("爆款封面", "cover", 8, 15),
    ("AI头像", "avatar", 4, 10),
    ("活动海报", "poster", 3, 10),
    ("朋友圈背景图", "background", 3, 10),
]

PROGRAM_INTENT_PATTERNS = [
    ("{program_name}不好用", "tool_pain", 10, 10),
    ("求推荐更好用的生图工具", "tool_recommendation", 10, 10),
    ("有没有好用的{program_name}", "tool_recommendation", 9, 10),
    ("{program_name}平替", "tool_alternative", 8, 8),
    ("{program_name}教程", "tutorial", 7, 8),
    ("小红书封面生图工具", "cover", 9, 10),
    ("活动海报生图工具", "poster", 6, 8),
    ("AI头像生图工具", "avatar", 5, 8),
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
