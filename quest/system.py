"""任务链剧情分支 - 任务系统核心。

状态机（合法转换）:
    not_accepted -> active
    active       -> completed | failed
    completed / failed 为终态，不能重新接，失败也不能无限重试。

剧情分支: 综合玩家当前选择、玩家属性(karma)与历史选择判定，并随存档持久化。
任务物品: 绑定任务，不可丢弃/变卖，任务终结（完成或失败）时自动回收。
任务追踪: 显示目标位置与进度，支持同时追踪多个任务。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional

# 合法状态转换表
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "not_accepted": frozenset({"active"}),
    "active": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}

TERMINAL_STATUSES = frozenset({"completed", "failed"})


@dataclass
class Objective:
    description: str
    location: str
    required: int = 1
    current: int = 0

    @property
    def progress(self) -> float:
        if self.required <= 0:
            return 1.0
        return min(1.0, self.current / self.required)

    @property
    def done(self) -> bool:
        return self.current >= self.required


@dataclass
class Quest:
    qid: str
    status: str = "not_accepted"  # not_accepted/active/completed/failed
    prerequisites: list = field(default_factory=list)
    quest_items: list = field(default_factory=list)       # 绑定到本任务的任务物品
    branch_choices: dict = field(default_factory=dict)   # {choice_id: outcome}，随存档持久化
    objectives: list = field(default_factory=list)       # list[Objective]
    reward: object = None


class QuestSystem:
    def __init__(self):
        self.quests: dict[str, Quest] = {}
        self.player_choices: list = []      # 历史分支选择，随存档持久化
        self.tracked_quests: list[str] = []  # 支持多任务追踪
        self.player_stats: dict = {}
        self.player_inventory: set = set()

    # ---------- 任务注册 ----------

    def register_quest(
        self,
        qid: str,
        prerequisites: Optional[list] = None,
        objectives: Optional[list] = None,
        reward=None,
    ) -> Quest:
        quest = Quest(
            qid,
            prerequisites=list(prerequisites or []),
            objectives=[
                obj if isinstance(obj, Objective) else Objective(**obj)
                for obj in (objectives or [])
            ],
            reward=reward,
        )
        self.quests[qid] = quest
        return quest

    # ---------- bug1: 接任务检查前置且防重复 ----------

    def accept_quest(self, qid: str) -> bool:
        quest = self.quests.get(qid)
        if quest is None:
            return False
        # 防重复：已接取/进行中/已终结的任务不能再次接取
        if quest.status != "not_accepted":
            return False
        # 前置条件：所有前置任务必须已完成
        for pre in quest.prerequisites:
            pre_quest = self.quests.get(pre)
            if pre_quest is None or pre_quest.status != "completed":
                return False
        quest.status = "active"
        return True

    # ---------- bug2: 任务状态机合法转换 ----------

    def update_quest_status(self, qid: str, new_status: str) -> bool:
        quest = self.quests.get(qid)
        if quest is None:
            return False
        if new_status not in VALID_TRANSITIONS.get(quest.status, frozenset()):
            return False
        quest.status = new_status
        if new_status == "completed":
            self._on_quest_completed(quest)
        elif new_status == "failed":
            self._on_quest_failed(quest)
        return True

    def _on_quest_completed(self, quest: Quest) -> None:
        # 任务完成：回收绑定的任务物品，发放奖励，移出追踪
        self._reclaim_quest_items(quest)
        self._grant_reward(quest)
        self.untrack_quest(quest.qid)

    def _on_quest_failed(self, quest: Quest) -> None:
        # 失败处理：回收任务物品并移出追踪；状态机禁止从 failed 重接，杜绝无限重试
        self._reclaim_quest_items(quest)
        self.untrack_quest(quest.qid)

    def _grant_reward(self, quest: Quest) -> None:
        if quest.reward is not None:
            self.player_stats.setdefault("rewards", []).append(quest.reward)

    # ---------- bug3: 分支条件综合判断且持久化 ----------

    def check_branch(self, qid: str, choice: str, player_stats: Optional[dict] = None) -> str:
        """综合当前选择、玩家属性与历史选择判定剧情分支，返回分支标识。"""
        stats = player_stats if player_stats is not None else self.player_stats
        outcome = self._resolve_branch(choice, stats)
        # 持久化：记录到全局历史与任务自身的分支记录
        self.player_choices.append(choice)
        quest = self.quests.get(qid)
        if quest is not None:
            quest.branch_choices[choice] = outcome
        return outcome

    # 兼容别名
    check_branch_condition = check_branch

    def _resolve_branch(self, choice: str, stats: dict) -> str:
        karma = stats.get("karma", 0)
        if choice == "evil":
            # 邪恶选项需要属性支撑（负 karma 或有邪恶前科），否则回到善良线
            if karma < 0 or "evil" in self.player_choices:
                return "evil_path"
            return "good_path"
        if choice == "good":
            if karma > 0 or "good" in self.player_choices:
                return "good_path"
            return "evil_path"
        return "neutral_path"

    # ---------- 存档：分支选择持久化 ----------

    def save_state(self, path: str) -> None:
        data = {
            "player_choices": list(self.player_choices),
            "tracked_quests": list(self.tracked_quests),
            "quests": {
                qid: {
                    "status": q.status,
                    "branch_choices": dict(q.branch_choices),
                    "quest_items": list(q.quest_items),
                    "objectives": [asdict(o) for o in q.objectives],
                }
                for qid, q in self.quests.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_state(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.player_choices = list(data.get("player_choices", []))
        self.tracked_quests = list(data.get("tracked_quests", []))
        for qid, qdata in data.get("quests", {}).items():
            quest = self.quests.get(qid)
            if quest is None:
                quest = Quest(qid)
                self.quests[qid] = quest
            quest.status = qdata.get("status", "not_accepted")
            quest.branch_choices = dict(qdata.get("branch_choices", {}))
            quest.quest_items = list(qdata.get("quest_items", []))
            quest.objectives = [Objective(**o) for o in qdata.get("objectives", [])]

    # ---------- bug4: 任务物品绑定且自动回收 ----------

    def give_quest_item(self, qid: str, item_id: str) -> bool:
        quest = self.quests.get(qid)
        if quest is None:
            return False
        if item_id not in quest.quest_items:  # 防重复获得
            quest.quest_items.append(item_id)
        self.player_inventory.add(item_id)
        return True

    def is_quest_item(self, item_id: str) -> bool:
        return any(item_id in q.quest_items for q in self.quests.values())

    def drop_item(self, item_id: str) -> bool:
        # 任务物品绑定任务，不能丢弃
        if self.is_quest_item(item_id):
            return False
        self.player_inventory.discard(item_id)
        return True

    def sell_item(self, item_id: str) -> bool:
        # 任务物品绑定任务，不能变卖
        if self.is_quest_item(item_id):
            return False
        self.player_inventory.discard(item_id)
        return True

    def _reclaim_quest_items(self, quest: Quest) -> None:
        for item_id in quest.quest_items:
            self.player_inventory.discard(item_id)
        quest.quest_items.clear()

    # ---------- bug5: 任务追踪显示位置进度且支持多任务 ----------

    def track_quest(self, qid: str) -> dict:
        quest = self.quests.get(qid)
        if quest is None:
            return {}
        if quest.status == "active" and qid not in self.tracked_quests:
            self.tracked_quests.append(qid)
        objectives = [
            {
                "description": o.description,
                "location": o.location,
                "current": o.current,
                "required": o.required,
                "progress": o.progress,
                "done": o.done,
            }
            for o in quest.objectives
        ]
        total_required = sum(o.required for o in quest.objectives)
        total_current = sum(o.current for o in quest.objectives)
        progress = min(1.0, total_current / total_required) if total_required > 0 else 0.0
        return {
            "qid": qid,
            "status": quest.status,
            "location": objectives[0]["location"] if objectives else None,
            "objectives": objectives,
            "progress": progress,
            "tracked_count": len(self.tracked_quests),
        }

    def untrack_quest(self, qid: str) -> None:
        if qid in self.tracked_quests:
            self.tracked_quests.remove(qid)

    def update_objective(self, qid: str, index: int, amount: int = 1) -> bool:
        quest = self.quests.get(qid)
        if quest is None or not (0 <= index < len(quest.objectives)):
            return False
        obj = quest.objectives[index]
        obj.current = min(obj.required, obj.current + amount)
        return True
