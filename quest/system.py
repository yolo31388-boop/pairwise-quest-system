"""任务链剧情分支系统"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

# 合法的任务状态转换
ALLOWED_TRANSITIONS = {
    "not_accepted": {"active"},
    "active": {"completed", "failed"},
    "failed": {"active"},   # 失败后可重试
    "completed": set(),     # 已完成是终态
}

_STAT_OPS = {
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


@dataclass
class Quest:
    qid: str
    status: str = "not_accepted"  # not_accepted/active/completed/failed
    prerequisites: list = field(default_factory=list)
    quest_items: list = field(default_factory=list)
    branch_choices: dict = field(default_factory=dict)
    branch_conditions: dict = field(default_factory=dict)
    location: str = ""
    objectives: list = field(default_factory=list)
    fail_count: int = 0


class QuestSystem:
    def __init__(self, save_path: str | None = None, max_retries: int = 3):
        self.quests: dict[str, Quest] = {}
        self.player_choices: list = []
        self.tracked_quests: list[str] = []
        self.max_retries = max_retries
        self.save_path = save_path
        if save_path and os.path.exists(save_path):
            self.load(save_path)

    # ---- 接任务：前置检查 + 防重复 ----
    def accept_quest(self, qid: str) -> bool:
        quest = self.quests.get(qid)
        if quest is None:
            quest = Quest(qid)
            self.quests[qid] = quest
        if quest.status != "not_accepted":
            return False  # 已接/已完成/失败中的任务不能重复接
        for pre in quest.prerequisites:
            pre_quest = self.quests.get(pre)
            if pre_quest is None or pre_quest.status != "completed":
                return False  # 前置任务未完成
        quest.status = "active"
        self.save()
        return True

    # ---- 状态机：合法转换 + 失败处理 ----
    def update_quest_status(self, qid: str, new_status: str) -> bool:
        quest = self.quests.get(qid)
        if quest is None:
            return False
        if new_status not in ALLOWED_TRANSITIONS.get(quest.status, set()):
            return False
        if quest.status == "failed" and new_status == "active":
            if quest.fail_count > self.max_retries:
                return False  # 重试次数耗尽，不能无限重试
        quest.status = new_status
        if new_status == "failed":
            self._on_quest_failed(quest)
        elif new_status == "completed":
            self._recycle_quest_items(quest)
        self.save()
        return True

    def _on_quest_failed(self, quest: Quest) -> None:
        quest.fail_count += 1
        quest.quest_items.clear()  # 失败回收任务物品
        for obj in quest.objectives:
            obj["current"] = 0  # 重置目标进度

    def _recycle_quest_items(self, quest: Quest) -> None:
        quest.quest_items.clear()

    # ---- 剧情分支：综合判断 + 持久化 ----
    def check_branch(self, qid: str, choice: str, player_stats: dict) -> bool:
        quest = self.quests.get(qid)
        if quest is None:
            return False
        taken = self._branch_condition_met(quest, choice, player_stats)
        self.player_choices.append(choice)
        quest.branch_choices[choice] = taken
        self.save()
        return taken

    def _branch_condition_met(self, quest: Quest, choice: str, player_stats: dict) -> bool:
        cond = quest.branch_conditions.get(choice)
        if not cond:
            return True
        for stat, requirement in cond.get("stats", {}).items():
            op, value = requirement
            actual = player_stats.get(stat)
            if actual is None or not _STAT_OPS[op](actual, value):
                return False
        for needed in cond.get("choices", []):
            if needed not in self.player_choices:
                return False
        return True

    # ---- 任务物品：绑定 + 自动回收 ----
    def give_quest_item(self, qid: str, item_id: str) -> bool:
        quest = self.quests.get(qid)
        if quest is None:
            return False
        if item_id in quest.quest_items:
            return False  # 防重复获得
        quest.quest_items.append(item_id)
        return True

    def can_drop_item(self, item_id: str) -> bool:
        # 绑定到未完成任务的任务物品不能丢弃/出售
        for quest in self.quests.values():
            if item_id in quest.quest_items and quest.status in ("active", "failed"):
                return False
        return True

    # ---- 任务追踪：位置 + 进度 + 多任务 ----
    def track_quest(self, qid: str) -> dict:
        quest = self.quests.get(qid)
        if quest is None:
            return {}
        if qid not in self.tracked_quests:
            self.tracked_quests.append(qid)
        return self._tracking_info(quest)

    def untrack_quest(self, qid: str) -> bool:
        if qid in self.tracked_quests:
            self.tracked_quests.remove(qid)
            return True
        return False

    def get_tracked_quests(self) -> list:
        return [self._tracking_info(self.quests[qid])
                for qid in self.tracked_quests if qid in self.quests]

    def _tracking_info(self, quest: Quest) -> dict:
        total = sum(o.get("target", 1) for o in quest.objectives)
        done = sum(min(o.get("current", 0), o.get("target", 1)) for o in quest.objectives)
        if total > 0:
            progress = done / total
        else:
            progress = 1.0 if quest.status == "completed" else 0.0
        return {
            "qid": quest.qid,
            "status": quest.status,
            "location": quest.location,
            "progress": progress,
            "objectives": [dict(o) for o in quest.objectives],
        }

    # ---- 持久化 ----
    def save(self, path: str | None = None) -> None:
        path = path or self.save_path
        if not path:
            return
        data = {
            "player_choices": list(self.player_choices),
            "quests": {
                qid: {
                    "status": q.status,
                    "quest_items": list(q.quest_items),
                    "branch_choices": dict(q.branch_choices),
                    "fail_count": q.fail_count,
                }
                for qid, q in self.quests.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str | None = None) -> None:
        path = path or self.save_path
        if not path or not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.player_choices = list(data.get("player_choices", []))
        for qid, state in data.get("quests", {}).items():
            quest = self.quests.setdefault(qid, Quest(qid))
            quest.status = state.get("status", quest.status)
            quest.quest_items = list(state.get("quest_items", []))
            quest.branch_choices = dict(state.get("branch_choices", {}))
            quest.fail_count = state.get("fail_count", 0)
