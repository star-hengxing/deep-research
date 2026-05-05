"""Unit tests for models.py — pure data, no I/O."""

from __future__ import annotations

from pathlib import Path

from deep_research.models import (
    AgentInfo,
    AgentStatus,
    Phase,
    PhaseState,
    ResearchState,
)


class TestAgentStatus:
    def test_values(self):
        assert AgentStatus.pending.value == "pending"
        assert AgentStatus.in_progress.value == "in_progress"
        assert AgentStatus.complete.value == "complete"
        assert AgentStatus.failed.value == "failed"


class TestPhase:
    def test_order(self):
        phases = [
            Phase.initialized,
            Phase.planned,
            Phase.researching,
            Phase.synthesized,
            Phase.reviewed,
            Phase.generated,
            Phase.complete,
            Phase.error,
        ]
        assert all(isinstance(p, Phase) for p in phases)


class TestAgentInfo:
    def test_default_status_is_pending(self):
        agent = AgentInfo(id=1, topic="test", description="desc", output_dir="/tmp")
        assert agent.status == AgentStatus.pending

    def test_repr(self):
        agent = AgentInfo(id=1, topic="pricing", description="Pricing analysis", output_dir="/tmp")
        assert agent.id == 1
        assert agent.topic == "pricing"


class TestPhaseState:
    def test_default_status(self):
        ps = PhaseState()
        assert ps.status == "pending"

    def test_to_dict_skips_none(self):
        ps = PhaseState(status="complete", completed_at="now")
        d = ps.to_dict()
        assert "started_at" not in d
        assert d["status"] == "complete"
        assert d["completed_at"] == "now"


class TestResearchState:
    def test_new_creates_initial_state(self):
        state = ResearchState.new(
            topic="AI APIs",
            output_dir=Path("/tmp/test"),
            language="en",
        )
        assert state.topic == "AI APIs"
        assert state.language == "en"
        assert state.phase == Phase.initialized
        assert state.created_at == state.updated_at

    def test_new_default_language(self):
        state = ResearchState.new(topic="test", output_dir=Path("/tmp/test"))
        assert state.language == "zh"

    def test_to_dict_from_dict_roundtrip(self):
        original = ResearchState.new(
            topic="AI APIs",
            output_dir=Path("/tmp/test"),
            language="en",
        )
        original.phases["plan"].status = "complete"
        original.agents = [
            AgentInfo(id=1, topic="pricing", description="Pricing", output_dir="/tmp/a"),
        ]

        d = original.to_dict()
        restored = ResearchState.from_dict(d)

        assert restored.topic == original.topic
        assert restored.phase == original.phase
        assert len(restored.agents) == 1
        assert restored.agents[0].topic == "pricing"
        assert restored.phases["plan"].status == "complete"

    def test_to_dict_serializes_enum(self):
        state = ResearchState.new(topic="t", output_dir=Path("/tmp/t"))
        d = state.to_dict()
        assert isinstance(d["phase"], str)

    def test_from_dict_restores_enums(self):
        d = {
            "version": "1",
            "project_name": "test",
            "topic": "test",
            "mode": "deep",
            "language": "zh",
            "output_dir": "/tmp/test",
            "phase": "planned",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "phases": {},
            "agents": [],
        }
        state = ResearchState.from_dict(d)
        assert state.phase == Phase.planned
