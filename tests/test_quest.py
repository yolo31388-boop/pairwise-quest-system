"""任务链剧情分支 - 红态测试（5类问题共14个用例）"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dataclasses import dataclass

from quest.system import QuestSystem, Quest

try:  # 旧实现没有 Objective，提供兜底以便完整展示 14 个红
    from quest.system import Objective
except ImportError:
    @dataclass
    class Objective:
        description: str
        location: str
        required: int = 1
        current: int = 0


# ---- bug1: 接任务检查前置且防重复 ----

class TestPrerequisiteCheck:
    def test_cannot_accept_without_prerequisite(self):
        qs = QuestSystem()
        qs.quests["q2"] = Quest("q2", prerequisites=["q1"])
        result = qs.accept_quest("q2")
        assert result is False
        assert qs.quests["q2"].status == "not_accepted"

    def test_can_accept_after_prerequisite_completed(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.quests["q2"] = Quest("q2", prerequisites=["q1"])
        # 前置未完成时不能接
        assert qs.accept_quest("q2") is False
        # 前置完成后才能接
        qs.quests["q1"].status = "completed"
        assert qs.accept_quest("q2") is True
        assert qs.quests["q2"].status == "active"

    def test_cannot_accept_same_quest_twice(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="active")
        # 进行中不能重接，已完成也不能重新接
        assert qs.accept_quest("q1") is False
        qs.quests["q2"] = Quest("q2", status="completed")
        assert qs.accept_quest("q2") is False


# ---- bug2: 任务状态机合法转换 + 失败处理 ----

class TestStatusMachine:
    def test_cannot_complete_unaccepted_quest(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="not_accepted")
        result = qs.update_quest_status("q1", "completed")
        assert result is False
        assert qs.quests["q1"].status == "not_accepted"

    def test_legal_transitions_active_to_completed_or_failed(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="active")
        assert qs.update_quest_status("q1", "completed") is True
        # completed 是终态，不能再转换
        assert qs.update_quest_status("q1", "active") is False
        qs.quests["q2"] = Quest("q2", status="active")
        assert qs.update_quest_status("q2", "failed") is True
        # failed 是终态，不能再转换
        assert qs.update_quest_status("q2", "active") is False

    def test_failed_quest_has_failure_handling_no_retry(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="failed")
        # failed 为终态：不能重新接，也不能改回 active，杜绝无限重试
        assert qs.accept_quest("q1") is False
        assert qs.update_quest_status("q1", "active") is False
        assert qs.update_quest_status("q1", "completed") is False


# ---- bug3: 分支条件综合判断且持久化 ----

class TestBranchPersistence:
    def test_branch_choices_persist(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.check_branch("q1", "evil", {"karma": -100})
        assert len(qs.player_choices) == 1
        assert qs.quests["q1"].branch_choices["evil"] == "evil_path"

    def test_evil_choice_needs_evil_stats_or_history(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.quests["q2"] = Quest("q2")
        # 属性是正 karma 又无邪恶前科：选 evil 仍走善良线
        assert qs.check_branch("q1", "evil", {"karma": 100}) == "good_path"
        # 负 karma 才走邪恶线
        assert qs.check_branch("q1", "evil", {"karma": -50}) == "evil_path"
        # 历史选择也影响后续分支：走过邪恶线后属性转正仍延续邪恶线
        assert qs.check_branch("q2", "evil", {"karma": 50}) == "evil_path"

    def test_branch_survives_save_load(self, tmp_path):
        save_file = tmp_path / "save.json"
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.check_branch("q1", "evil", {"karma": -100})
        qs.save_state(str(save_file))

        reloaded = QuestSystem()
        reloaded.quests["q1"] = Quest("q1")
        reloaded.load_state(str(save_file))
        assert reloaded.player_choices == ["evil"]
        assert reloaded.quests["q1"].branch_choices["evil"] == "evil_path"


# ---- bug4: 任务物品绑定且自动回收 ----

class TestQuestItemBinding:
    def test_quest_items_bound_to_quest(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.give_quest_item("q1", "key")
        assert "key" in qs.quests["q1"].quest_items
        assert qs.is_quest_item("key") is True

    def test_quest_item_cannot_drop_or_sell_and_no_duplicate(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1")
        qs.give_quest_item("q1", "key")
        assert qs.drop_item("key") is False
        assert qs.sell_item("key") is False
        # 重复给予不产生重复物品
        qs.give_quest_item("q1", "key")
        assert qs.quests["q1"].quest_items.count("key") == 1

    def test_quest_items_reclaimed_on_completion_and_failure(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest("q1", status="active", reward="gold")
        qs.give_quest_item("q1", "key")
        assert qs.update_quest_status("q1", "completed") is True
        assert qs.quests["q1"].quest_items == []
        assert "key" not in qs.player_inventory
        assert "gold" in qs.player_stats["rewards"]

        qs.quests["q2"] = Quest("q2", status="active")
        qs.give_quest_item("q2", "map")
        assert qs.update_quest_status("q2", "failed") is True
        assert qs.quests["q2"].quest_items == []
        assert "map" not in qs.player_inventory


# ---- bug5: 任务追踪显示位置进度且支持多任务 ----

class TestQuestTracking:
    def test_tracking_shows_objective_location(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest(
            "q1",
            status="active",
            objectives=[Objective("找到钥匙", "地下城", required=1)],
        )
        info = qs.track_quest("q1")
        assert "location" in info
        assert info["location"] == "地下城"

    def test_tracking_supports_multiple_quests_and_progress(self):
        qs = QuestSystem()
        qs.quests["q1"] = Quest(
            "q1",
            status="active",
            objectives=[Objective("击败哥布林", "森林", required=3)],
        )
        qs.quests["q2"] = Quest(
            "q2",
            status="active",
            objectives=[Objective("采集草药", "山谷", required=2)],
        )
        qs.track_quest("q1")
        qs.track_quest("q2")
        assert sorted(qs.tracked_quests) == ["q1", "q2"]

        qs.update_objective("q1", 0, 2)
        obj = qs.track_quest("q1")["objectives"][0]
        assert obj["current"] == 2
        assert obj["required"] == 3
        assert obj["progress"] == pytest.approx(2 / 3)

        # 任务终结后自动移出追踪，另一任务仍保留
        assert qs.update_quest_status("q1", "completed") is True
        assert "q1" not in qs.tracked_quests
        assert "q2" in qs.tracked_quests
