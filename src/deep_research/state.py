"""State machine with JSON file persistence for checkpoint/resume."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from deep_research.models import (
    AgentInfo,
    AgentStatus,
    Phase,
    PhaseState,
    ResearchState,
)

STATE_FILENAME = ".deep-research-state.json"


class StateManager:
    """Manages research state with JSON file persistence."""

    def __init__(self, research_dir: Path):
        self.research_dir = research_dir.resolve()
        self.state_path = self.research_dir / STATE_FILENAME
        self._state: ResearchState | None = None

    # --- Load / Save ---

    def load(self) -> ResearchState:
        if self._state is None:
            if self.state_path.exists():
                import json

                with open(self.state_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._state = ResearchState.from_dict(data)
            else:
                raise FileNotFoundError(f"No state file found at {self.state_path}. Run `deep-research init` first.")
        return self._state

    def save(self, state: ResearchState) -> None:
        import json
        from datetime import datetime

        state.updated_at = datetime.now(UTC).isoformat()
        self.research_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        self._state = state

    def exists(self) -> bool:
        return self.state_path.exists()

    def clear(self) -> None:
        if self.state_path.exists():
            self.state_path.unlink()
        self._state = None

    # --- State Transitions ---

    def transition(self, target_phase: Phase) -> ResearchState:
        state = self.load()

        # Allow transition to error from any phase
        if target_phase == Phase.error:
            state.phase = Phase.error
            state.error = None
            self.save(state)
            return state

        # Allow transition from error to reset
        if state.phase == Phase.error:
            state.phase = target_phase
            state.error = None
            self.save(state)
            return state

        phase_order = [
            Phase.initialized,
            Phase.planned,
            Phase.researching,
            Phase.synthesized,
            Phase.reviewed,
            Phase.generated,
            Phase.complete,
        ]
        current_idx = phase_order.index(state.phase)
        target_idx = phase_order.index(target_phase)

        if target_idx <= current_idx and target_phase != Phase.error:
            raise ValueError(
                f"Cannot transition from {state.phase.value} to {target_phase.value}. "
                f"Target must be after current phase."
            )

        state.phase = target_phase
        state.error = None
        self.save(state)
        return state

    def set_error(self, error_msg: str) -> ResearchState:
        state = self.load()
        state.phase = Phase.error
        state.error = error_msg
        self.save(state)
        return state

    def update_phase(self, phase_name: str, status: str, error: str | None = None) -> ResearchState:
        state = self.load()
        if phase_name not in state.phases:
            state.phases[phase_name] = PhaseState()
        ps = state.phases[phase_name]
        ps.status = status
        if error:
            ps.error = error
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        if status == "in_progress":
            ps.started_at = now
        elif status == "complete":
            ps.completed_at = now
        self.save(state)
        return state

    def add_agents(self, agents: list[AgentInfo]) -> ResearchState:
        state = self.load()
        state.agents = agents
        self.save(state)
        return state

    def update_agent(self, agent_id: int, status: AgentStatus, report_path: str | None = None) -> ResearchState:
        state = self.load()
        for agent in state.agents:
            if agent.id == agent_id:
                agent.status = status
                if report_path:
                    agent.report_path = report_path
                break
        self.save(state)
        return state

    # --- Query ---

    def next_phase(self) -> str | None:
        """Return the name of the first incomplete phase, or None if complete."""
        state = self.load()
        ordered = ["plan", "agents", "synthesize", "reviewed", "generate"]
        for name in ordered:
            if name in state.phases and state.phases[name].status != "complete":
                return name
        return None

    def summary(self) -> dict:
        """Return a human-readable summary of current state."""
        state = self.load()
        agent_counts = {"pending": 0, "in_progress": 0, "complete": 0, "failed": 0}
        for a in state.agents:
            agent_counts[a.status.value] = agent_counts.get(a.status.value, 0) + 1

        return {
            "topic": state.topic,
            "phase": state.phase.value,
            "language": state.language,
            "output_dir": state.output_dir,
            "next_phase": self.next_phase(),
            "agent_count": len(state.agents),
            "agent_status": agent_counts,
            "phases": {k: v.status for k, v in state.phases.items()},
            "error": state.error,
        }
