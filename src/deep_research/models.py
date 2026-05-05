from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class Phase(StrEnum):
    initialized = "initialized"
    planned = "planned"
    researching = "researching"
    synthesized = "synthesized"
    reviewed = "reviewed"
    generated = "generated"
    complete = "complete"
    error = "error"


class AgentStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    complete = "complete"
    failed = "failed"


@dataclass
class AgentInfo:
    id: int
    topic: str
    description: str
    output_dir: str
    status: AgentStatus = AgentStatus.pending
    report_path: str | None = None


@dataclass
class PhaseState:
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ResearchState:
    version: str = "1"
    project_name: str = ""
    topic: str = ""
    language: str = "zh"
    output_dir: str = ""
    phase: Phase = Phase.initialized
    created_at: str = ""
    updated_at: str = ""
    phases: dict[str, PhaseState] = field(
        default_factory=lambda: {
            name: PhaseState()
            for name in ["plan", "agents", "synthesize", "reviewed", "generate"]
        }
    )
    agents: list[AgentInfo] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def new(
        cls, topic: str, output_dir: Path, language: str = "zh"
    ) -> ResearchState:
        now = datetime.now(UTC).isoformat()
        return cls(
            project_name=output_dir.name,
            topic=topic,
            language=language,
            output_dir=str(output_dir.resolve()),
            phase=Phase.initialized,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["phase"] = self.phase.value
        d["agents"] = [asdict(a) for a in self.agents]
        d["phases"] = {k: v.to_dict() for k, v in self.phases.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ResearchState:
        agents = []
        for a in d.get("agents", []):
            a["status"] = AgentStatus(a.get("status", "pending"))
            agents.append(AgentInfo(**a))

        phases = {}
        for name, ps in d.get("phases", {}).items():
            phases[name] = PhaseState(**ps)

        raw_phase = d.get("phase", "initialized")
        try:
            phase = Phase(raw_phase)
        except ValueError:
            import warnings

            warnings.warn(
                f"Unknown phase '{raw_phase}' in state file, falling back to 'initialized'",
                RuntimeWarning,
                stacklevel=2,
            )
            phase = Phase.initialized

        return cls(
            version=d.get("version", "1"),
            project_name=d.get("project_name", ""),
            topic=d.get("topic", ""),
            language=d.get("language", "zh"),
            output_dir=d.get("output_dir", ""),
            phase=phase,
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            phases=phases,
            agents=agents,
            error=d.get("error"),
        )


DEFAULT_AGENT_COUNT = 8
