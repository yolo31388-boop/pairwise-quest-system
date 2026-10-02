"""任务链剧情分支 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quest.system import QuestSystem, Quest

class TestPrerequisiteCheck:
    def test_cannot_accept_without_prerequisite(self):
        qs = QuestSystem()
        qs.quests["q2"] = Quest("q2", prerequisites=["q1"])
        result = qs.accept_quest("q2")
        assert result == False

class TestStatusMachine:
    def test_cannot_complete_unaccepted_quest(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="not_accepted")
        result = qs.update_quest_status("q1", "completed")
        assert result == False

class TestBranchPersistence:
    def test_branch_choices_persist(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.check_branch("q1", "evil", {"karma": -100})
        assert len(qs.player_choices) == 1

class TestQuestItemBinding:
    def test_quest_items_bound_to_quest(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.give_quest_item("q1", "key")
        assert "key" in qs.quests["q1"].quest_items

class TestQuestTracking:
    def test_tracking_shows_objective_location(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="active")
        info = qs.track_quest("q1")
        assert "location" in info
