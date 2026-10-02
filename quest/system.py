"""任务链剧情分支 - 含5个bug"""
from dataclasses import dataclass, field

@dataclass
class Quest:
    qid: str
    status: str = "not_accepted"  # not_accepted/active/completed/failed
    prerequisites: list = field(default_factory=list)
    quest_items: list = field(default_factory=list)
    branch_choices: dict = field(default_factory=dict)  # bug3: 不持久化

class QuestSystem:
    def __init__(self):
        self.quests: dict[str, Quest] = {}
        self.player_choices: list = []  # bug3: 不持久化

    def accept_quest(self, qid: str) -> bool:
        # bug1: 不检查前置，不防重复
        if qid not in self.quests:
            self.quests[qid] = Quest(qid)
        self.quests[qid].status = "active"
        return True

    def update_quest_status(self, qid: str, new_status: str) -> bool:
        # bug2: 状态转换不合法
        if qid in self.quests:
            self.quests[qid].status = new_status
        return True

    def check_branch(self, qid: str, choice: str, player_stats: dict) -> bool:
        # bug3: 只看选择不看属性
        self.player_choices.append(choice)
        return True

    def give_quest_item(self, qid: str, item_id: str) -> bool:
        # bug4: 任务物品不绑定
        if qid in self.quests:
            self.quests[qid].quest_items.append(item_id)
        return True

    def track_quest(self, qid: str) -> dict:
        # bug5: 不显示位置进度
        quest = self.quests.get(qid)
        if quest:
            return {"status": quest.status}
        return {}
