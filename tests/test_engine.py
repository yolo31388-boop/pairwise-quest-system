"""任务系统测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import QuestManager, Quest, QuestObjective

class TestProgress:
    def test_incremental_objective(self):
        qm = QuestManager()
        qm.quests["q"] = Quest("q", "test", [QuestObjective("kill", 10)])
        qm.update_objective("q", 0, 3)
        qm.update_objective("q", 0, 2)
        assert qm.quests["q"].objectives[0].progress == 5

class TestPrereq:
    def test_failed_prereq_blocked(self):
        qm = QuestManager()
        qm.quests["pre"] = Quest("pre", "pre", status="failed")
        qm.quests["next"] = Quest("next", "next", prerequisites=["pre"])
        result = qm.accept_quest("next")
        assert not result, "失败的前置任务未阻塞"
