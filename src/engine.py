"""任务系统"""
import threading
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
    reward_claimed: bool = False
    cooldown_until: float = 0.0

class QuestManager:
    def __init__(self):
        self.quests: dict[str, Quest] = {}
        self.active = []
        self.world_progress = {}
        self._world_lock = threading.Lock()
        self._frame = 0
        self._frame_settled = set()
        self.game_time = 0.0
        self.paused = False

    # ---- 游戏内时间（暂停/下线时冻结） ----
    def tick(self, dt):
        if not self.paused:
            self.game_time += dt

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    # ---- 目标进度 ----
    def update_objective(self, qid, obj_idx, amount):
        """增量更新目标进度"""
        q = self.quests[qid]
        obj = q.objectives[obj_idx]
        obj.progress = min(obj.target, obj.progress + amount)

    def set_objective(self, qid, obj_idx, value):
        """设置目标进度的绝对值"""
        q = self.quests[qid]
        obj = q.objectives[obj_idx]
        obj.progress = max(0, min(obj.target, value))

    # ---- 任务接取/完成/放弃 ----
    def accept_quest(self, qid):
        q = self.quests[qid]
        # 前置任务必须完成；失败状态同样阻塞，需重新完成
        for pre in q.prerequisites:
            if self.quests[pre].status != "completed":
                return False
        # 可重复任务冷却按游戏内时间计算
        if q.repeatable and self.game_time < q.cooldown_until:
            return False
        q.status = "active"
        if q not in self.active:
            self.active.append(q)
        return True

    def complete_quest(self, qid):
        q = self.quests[qid]
        q.status = "completed"
        if q.repeatable:
            q.cooldown_until = self.game_time + q.cooldown
        # 完成时才发放奖励，且只发一次
        if q.reward_claimed:
            return None
        q.reward_claimed = True
        return q.reward

    def abandon_quest(self, qid):
        """放弃任务：不发放奖励"""
        q = self.quests[qid]
        q.status = "available"
        if q in self.active:
            self.active.remove(q)

    # ---- 世界任务进度（原子操作 + 同帧去重） ----
    def advance_frame(self):
        self._frame += 1
        self._frame_settled.clear()

    def update_world_objective(self, obj_id, amount):
        with self._world_lock:
            key = (self._frame, obj_id)
            if key in self._frame_settled:
                return  # 同一目标同一帧只结算一次
            self._frame_settled.add(key)
            self.world_progress[obj_id] = self.world_progress.get(obj_id, 0) + amount

    # ---- 任务日志：按状态分组，进行中在前，已完成沉底 ----
    def sort_log(self):
        order = {"active": 0, "available": 1, "failed": 2, "completed": 3}
        return sorted(self.active, key=lambda q: order.get(q.status, 1))
