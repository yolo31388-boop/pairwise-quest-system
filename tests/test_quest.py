"""任务链剧情分支 - 测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quest.system import QuestSystem, Quest


class TestPrerequisiteCheck:
    def test_cannot_accept_without_prerequisite(self):
        qs = QuestSystem()
        qs.quests["q2"] = Quest("q2", prerequisites=["q1"])
        result = qs.accept_quest("q2")
        assert result == False

    def test_can_accept_after_completing_prerequisite(self):
        qs = QuestSystem()
        qs.quests["q2"] = Quest("q2", prerequisites=["q1"])
        assert qs.accept_quest("q1") == True
        assert qs.update_quest_status("q1", "completed") == True
        assert qs.accept_quest("q2") == True

    def test_cannot_accept_same_quest_twice(self):
        qs = QuestSystem()
        assert qs.accept_quest("q1") == True
        assert qs.accept_quest("q1") == False
        assert qs.quests["q1"].status == "active"


class TestStatusMachine:
    def test_cannot_complete_unaccepted_quest(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="not_accepted")
        result = qs.update_quest_status("q1", "completed")
        assert result == False

    def test_active_quest_can_complete(self):
        qs = QuestSystem()
        qs.accept_quest("q1")
        assert qs.update_quest_status("q1", "completed") == True
        assert qs.quests["q1"].status == "completed"

    def test_completed_quest_cannot_reaccept(self):
        qs = QuestSystem()
        qs.accept_quest("q1")
        qs.update_quest_status("q1", "completed")
        assert qs.accept_quest("q1") == False
        assert qs.update_quest_status("q1", "active") == False

    def test_failed_quest_retry_with_limit(self):
        qs = QuestSystem(max_retries=2)
        qs.accept_quest("q1")
        assert qs.update_quest_status("q1", "failed") == True
        assert qs.update_quest_status("q1", "completed") == False  # 失败不能直接交任务
        assert qs.update_quest_status("q1", "active") == True      # 第1次重试
        qs.update_quest_status("q1", "failed")
        assert qs.update_quest_status("q1", "active") == True      # 第2次重试
        qs.update_quest_status("q1", "failed")
        assert qs.update_quest_status("q1", "active") == False     # 重试次数耗尽
        assert qs.quests["q1"].fail_count == 3


class TestBranchPersistence:
    def test_branch_choices_persist(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.check_branch("q1", "evil", {"karma": -100})
        assert len(qs.player_choices) == 1

    def test_branch_considers_stats_and_history(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", branch_conditions={
            "evil": {"stats": {"karma": ("<=", -50)}, "choices": ["betray"]},
        })
        # 属性不满足：善良玩家选邪恶选项不生效
        assert qs.check_branch("q1", "evil", {"karma": 100}) == False
        # 属性满足但缺少前置选择
        assert qs.check_branch("q1", "evil", {"karma": -100}) == False
        # 属性和历史选择都满足，邪恶分支生效
        qs.player_choices.append("betray")
        assert qs.check_branch("q1", "evil", {"karma": -100}) == True

    def test_branch_choices_survive_reload(self, tmp_path):
        save_file = str(tmp_path / "save.json")
        qs = QuestSystem(save_path=save_file)
        qs.quests["q1"] = Quest("q1")
        qs.check_branch("q1", "evil", {"karma": -100})
        qs2 = QuestSystem(save_path=save_file)
        assert qs2.player_choices == ["evil"]
        assert qs2.quests["q1"].branch_choices == {"evil": True}


class TestQuestItemBinding:
    def test_quest_items_bound_to_quest(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.give_quest_item("q1", "key")
        assert "key" in qs.quests["q1"].quest_items

    def test_quest_items_recycled_on_completion(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="active")
        qs.give_quest_item("q1", "key")
        qs.update_quest_status("q1", "completed")
        assert qs.quests["q1"].quest_items == []


class TestQuestTracking:
    def test_tracking_shows_objective_location(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="active", location="城镇广场",
                                objectives=[{"desc": "击败盗贼", "target": 5, "current": 2}])
        info = qs.track_quest("q1")
        assert "location" in info
        assert info["location"] == "城镇广场"
        assert info["progress"] == pytest.approx(0.4)

    def test_multi_quest_tracking(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="active", location="东城门")
        qs.quests["q2"] = Quest("q2", status="active", location="西城门")
        qs.track_quest("q1")
        qs.track_quest("q2")
        tracked = qs.get_tracked_quests()
        assert len(tracked) == 2
        assert {t["location"] for t in tracked} == {"东城门", "西城门"}
