"""任务系统 - 带6个bug"""
from dataclasses import dataclass, field

@dataclass
class QuestObjective:
    desc: str
    target: int
    progress: int = 0

@dataclass
class Quest:
    qid: str
    name: str
    objectives: list[QuestObjective] = field(default_factory=list)
    prerequisites: list = field(default_factory=list)
    status: str = "available"  # available/active/completed/failed
    reward: dict = field(default_factory=dict)
    repeatable: bool = False
    cooldown: float = 0

class QuestManager:
    def __init__(self):
        self.quests: dict[str, Quest] = {}
        self.active = []
        self.world_progress = {}  # bug5: 无并发控制

    def update_objective(self, qid, obj_idx, amount):
        q = self.quests[qid]
        q.objectives[obj_idx].progress = amount  # bug1: 覆盖式

    def accept_quest(self, qid):
        q = self.quests[qid]
        # bug3: 只看完成不看失败
        for pre in q.prerequisites:
            if self.quests[pre].status != "completed":
                return False
        q.status = "active"
        # bug4: 接受时发奖励
        return True

    def complete_quest(self, qid):
        q = self.quests[qid]
        q.status = "completed"
        return q.reward

    def update_world_objective(self, obj_id, amount):
        # bug5: 无原子操作
        self.world_progress[obj_id] = self.world_progress.get(obj_id, 0) + amount

    def sort_log(self):
        # bug6: 按接受时间固定排序
        return sorted(self.active, key=lambda q: q.qid)
