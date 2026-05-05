"""Integration tests for state.py — JSON file persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_research.models import AgentInfo, AgentStatus, Phase, ResearchState
from deep_research.state import StateManager


@pytest.fixture
def sm(project_dir: Path) -> StateManager:
    return StateManager(project_dir)


@pytest.fixture
def seeded_state(sm: StateManager) -> ResearchState:
    state = ResearchState.new(topic="test", output_dir=sm.research_dir)
    sm.save(state)
    return state


class TestStateManagerInit:
    def test_creates_paths(self, sm: StateManager):
        assert sm.research_dir.exists()
        assert sm.state_path.name == ".deep-research-state.json"

    def test_exists_returns_false_initially(self, sm: StateManager):
        assert not sm.exists()

    def test_load_raises_when_missing(self, sm: StateManager):
        with pytest.raises(FileNotFoundError):
            sm.load()


class TestStateManagerSaveLoad:
    def test_save_creates_file(self, sm: StateManager, seeded_state: ResearchState):
        assert sm.state_path.exists()

    def test_load_returns_same_data(self, sm: StateManager, seeded_state: ResearchState):
        loaded = sm.load()
        assert loaded.topic == "test"
        assert loaded.phase == Phase.initialized

    def test_save_updates_timestamp(self, sm: StateManager):
        s1 = ResearchState.new(topic="t", output_dir=sm.research_dir)
        sm.save(s1)
        t1 = s1.updated_at

        s2 = sm.load()
        s2.topic = "updated"
        sm.save(s2)
        t2 = s2.updated_at

        assert t2 >= t1

    def test_clear_removes_file(self, sm: StateManager, seeded_state: ResearchState):
        assert sm.exists()
        sm.clear()
        assert not sm.exists()

    def test_clear_resets_cache(self, sm: StateManager, seeded_state: ResearchState):
        sm.clear()
        assert sm._state is None


class TestStateTransitions:
    def test_transition_forward(self, sm: StateManager, seeded_state: ResearchState):
        sm.transition(Phase.planned)
        assert sm.load().phase == Phase.planned

    def test_transition_backward_raises(self, sm: StateManager, seeded_state: ResearchState):
        sm.transition(Phase.planned)
        with pytest.raises(ValueError, match="Cannot transition"):
            sm.transition(Phase.initialized)

    def test_transition_to_error_allowed_anytime(self, sm: StateManager, seeded_state: ResearchState):
        sm.transition(Phase.planned)
        sm.set_error("something broke")
        assert sm.load().phase == Phase.error
        assert sm.load().error == "something broke"

    def test_transition_clears_error(self, sm: StateManager, seeded_state: ResearchState):
        sm.set_error("broken")
        sm.transition(Phase.planned)
        assert sm.load().error is None


class TestStateAgents:
    def test_add_agents(self, sm: StateManager, seeded_state: ResearchState):
        agents = [AgentInfo(id=1, topic="t1", description="d1", output_dir="/tmp/a")]
        sm.add_agents(agents)
        assert len(sm.load().agents) == 1

    def test_update_agent(self, sm: StateManager, seeded_state: ResearchState):
        agents = [AgentInfo(id=1, topic="t1", description="d1", output_dir="/tmp/a")]
        sm.add_agents(agents)

        sm.update_agent(1, AgentStatus.complete, report_path="/tmp/a/report.md")
        updated = sm.load().agents[0]
        assert updated.status == AgentStatus.complete
        assert updated.report_path == "/tmp/a/report.md"


class TestStateQuery:
    def test_summary_keys(self, sm: StateManager, seeded_state: ResearchState):
        s = sm.summary()
        assert "topic" in s
        assert "phase" in s
        assert "agent_count" in s

    def test_next_phase_returns_first_incomplete(self, sm: StateManager, seeded_state: ResearchState):
        assert sm.next_phase() == "plan"

    def test_next_phase_none_when_all_complete(self, sm: StateManager, seeded_state: ResearchState):
        state = sm.load()
        for name in state.phases:
            state.phases[name].status = "complete"
        sm.save(state)
        assert sm.next_phase() is None

    def test_update_phase_adds_new(self, sm: StateManager, seeded_state: ResearchState):
        sm.update_phase("custom", "in_progress")
        assert sm.load().phases["custom"].status == "in_progress"
