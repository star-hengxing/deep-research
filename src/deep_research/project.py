"""Research project lifecycle management."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from deep_research.models import DEFAULT_AGENT_COUNT, AgentInfo, AgentStatus, Phase, ResearchState
from deep_research.state import StateManager


def _create_meta_template(agent_dir: Path, direction: str) -> None:
    """Pre-create .meta.json so agents only need to edit values, not remember the schema."""
    meta_path = agent_dir / ".meta.json"
    if not meta_path.exists():
        meta = {
            "direction": direction,
            "searched_links": [],
            "model_id": "",
            "tokens_total": 0,
            "duration": "",
            "research_started_at": datetime.now(UTC).isoformat(),
            "research_completed_at": "",
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _format_tokens(count: object) -> str:
    if not isinstance(count, (int, float, str)):
        return "-"
    try:
        n = int(count)
    except (ValueError, TypeError):
        return "-"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _format_duration(meta: dict) -> str:
    """Compute duration from timestamps. Falls back to agent-written field.

    Only uses timestamps when BOTH include time components (T/HH:MM:SS).
    Date-only timestamps are too coarse for duration calculation.
    """
    started = meta.get("research_started_at", "")
    completed = meta.get("research_completed_at", "")

    if isinstance(started, str) and isinstance(completed, str) and "T" in completed:
        try:
            from datetime import datetime

            s = started.replace("Z", "+00:00")
            if "T" not in s:
                s = s + "T00:00:00+00:00"
            c = completed.replace("Z", "+00:00")
            if "T" not in c:
                c = c + "T00:00:00+00:00"

            t0 = datetime.fromisoformat(s)
            t1 = datetime.fromisoformat(c)

            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=UTC)
            if t1.tzinfo is None:
                t1 = t1.replace(tzinfo=UTC)

            seconds = int((t1 - t0).total_seconds())
            if seconds < 0:
                seconds = 0
            # If computed > 3h and agent wrote a duration, the timestamp
            # likely has a placeholder T00:00:00 — use agent value instead
            agent_dur = meta.get("duration", "")
            if seconds > 10800 and agent_dur:
                return str(agent_dur)
            if seconds < 60:
                return f"{seconds}s"
            minutes = seconds // 60
            if minutes < 60:
                return f"{minutes}m"
            hours = minutes // 60
            remaining = minutes % 60
            if remaining == 0:
                return f"{hours}h"
            return f"{hours}h {remaining}m"
        except (ValueError, TypeError, OSError):
            pass

    # Fallback to agent-written duration (keep it as-is)
    duration = meta.get("duration", "")
    return str(duration) if duration else "-"


def slugify(text: str) -> str:
    import re

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].rstrip("-")


def default_output_dir(topic: str, base: Path | None = None) -> Path:
    base = base or Path.cwd()
    return base / "docs" / "research" / slugify(topic)


class ResearchProject:
    """Manages a single research project lifecycle."""

    def __init__(self, research_dir: Path):
        self.research_dir = research_dir.resolve()
        self.state = StateManager(self.research_dir)

    @classmethod
    def init(
        cls,
        topic: str,
        language: str = "zh",
        output_dir: Path | None = None,
        fast: bool = False,
    ) -> ResearchProject:
        output_dir = output_dir or default_output_dir(topic)
        output_dir.mkdir(parents=True, exist_ok=True)

        state = ResearchState.new(topic, output_dir, language)
        sm = StateManager(output_dir)
        sm.save(state)

        # Create requirements file unless fast mode
        if not fast:
            req_path = output_dir / "requirements.md"
            if not req_path.exists():
                req_path.write_text(
                    f"# Requirements: {topic}\n\n"
                    f"## User Requirements\n(TBD — LLM writes interpreted requirements here, user confirms)\n\n"
                    f"## Scope & Constraints\n(TBD)\n\n"
                    f"## Success Criteria\n(TBD)\n",
                    encoding="utf-8",
                )

        return cls(output_dir)

    # --- Plan ---

    def create_plan(self, directions: list[str] | None = None, agent_count: int | None = None) -> Path:
        """Generate the research plan file and create agent definitions."""
        state = self.state.load()

        if directions:
            names = [slugify(d) for d in directions]
        else:
            count = agent_count or DEFAULT_AGENT_COUNT
            names = [f"direction-{i:02d}" for i in range(1, count + 1)]

        agents = []
        for i, name in enumerate(names, 1):
            agent_dir_path = self.research_dir / name
            agent_dir_path.mkdir(parents=True, exist_ok=True)
            direction_label = directions[i - 1] if directions else name
            _create_meta_template(agent_dir_path, direction_label)

            agents.append(
                AgentInfo(
                    id=i,
                    topic=name,
                    description=f"Research direction: {direction_label}",
                    output_dir=str(agent_dir_path.resolve()),
                )
            )

        plan_lines = [
            f"# Research Plan: {state.topic}",
            "",
            "## Directions",
            "| Agent | Direction | Sub-topics |",
            "|-------|-----------|------------|",
        ]
        for a in agents:
            plan_lines.append(f"| {Path(a.output_dir).name} | {a.topic} | (TBD) |")

        plan_lines.extend(["", "Fill in sub-topics above. Each agent writes `.md` files in its own directory."])

        plan_path = self.research_dir / "plan.md"
        plan_path.write_text("\n".join(plan_lines) + "\n", encoding="utf-8")

        self.state.add_agents(agents)
        self.state.update_phase("plan", "complete")
        self.state.transition(Phase.planned)

        return plan_path

    # --- Directions ---

    def add_direction(self, name: str) -> AgentInfo:
        """Add a new research direction. Returns the new agent."""
        state = self.state.load()
        next_id = max((a.id for a in state.agents), default=0) + 1
        dir_name = slugify(name)
        agent_dir_path = self.research_dir / dir_name
        agent_dir_path.mkdir(parents=True, exist_ok=True)
        _create_meta_template(agent_dir_path, name)

        agent = AgentInfo(
            id=next_id,
            topic=slugify(name),
            description=name,
            output_dir=str(agent_dir_path.resolve()),
        )
        self.state.add_agents(state.agents + [agent])
        return agent

    # --- Agents ---

    def format_agent_prompt(self, agent: AgentInfo) -> str:
        """Format a research prompt for a sub-agent."""
        state = self.state.load()
        today = date.today().isoformat()

        return (
            f"Research **{agent.topic}** for the report on **{state.topic}**.\n"
            f"Date: {today}. Write in {state.language.upper()}.\n\n"
            f"## Task\n"
            f"Investigate **{agent.topic}** thoroughly. Write findings as `.md` files in:\n"
            f"`{agent.output_dir}/`\n\n"
            f"- Multiple files for distinct sub-topics, or single `report.md`\n"
            f"- Every file needs `## References` section\n"
            f"- Every factual claim must cite a source as [N]\n\n"
            f"## Meta\n"
            f"A `.meta.json` template already exists in your output directory.\n"
            f"After writing reports, edit it to fill in: `searched_links`, `model_id`,\n"
            f"`tokens_total`, `duration`, `research_completed_at`.\n\n"
            f"## Report structure\n"
            f"`## Overview` → `## Key Findings` → `## Detailed Analysis` →\n"
            f'`## Limitations` → `## References` ([N] Author. "Title." URL)\n\n'
            f"## Approach\n"
            f"1. Search broadly, then narrow. 10+ sources preferred.\n"
            f"2. Use WebSearch for discovery, WebFetch for deep extraction.\n"
            f"3. Search in English and {state.language}.\n"
        )

    def list_agents(self) -> list[AgentInfo]:
        return self.state.load().agents

    def get_agent(self, agent_id: int) -> AgentInfo | None:
        state = self.state.load()
        for a in state.agents:
            if a.id == agent_id:
                return a
        return None

    # --- Meta Integrity ---

    def check_meta_integrity(self) -> tuple[list[str], list[str]]:
        """Scan all agent dirs for .meta.json completeness.

        Returns (errors, warnings). Errors are blocking — agent dirs with .md
        reports but missing or unreadable .meta.json. Warnings are non-blocking.
        """
        import json

        errors: list[str] = []
        warnings: list[str] = []
        for agent_dir in sorted(self.research_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name == "output":
                continue
            meta_path = agent_dir / ".meta.json"
            md_files = list(agent_dir.glob("*.md"))
            if not meta_path.exists():
                if md_files:
                    errors.append(f"  {agent_dir.name}/: has {len(md_files)} report(s) but missing .meta.json")
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                errors.append(f"  {agent_dir.name}/.meta.json: unreadable")
                continue
            # Required fields that must be non-empty
            required = ["direction", "searched_links", "model_id", "tokens_total"]
            for field in required:
                val = data.get(field)
                if val is None or val == "" or val == []:
                    warnings.append(f"  {agent_dir.name}/.meta.json: '{field}' is empty")
                    break
            known = {
                "direction",
                "searched_links",
                "tokens_total",
                "model_id",
                "temperature",
                "thinking_level",
                "duration",
                "research_started_at",
                "research_completed_at",
            }
            extra = set(data) - known
            if extra:
                warnings.append(f"  {agent_dir.name}/.meta.json: unknown fields {sorted(extra)}")
        return errors, warnings

    # --- Appendix ---

    def generate_appendix(self) -> tuple[str | None, list[str]]:
        """Scan all agent-XX/.meta.json and generate an appendix markdown.

        Returns (appendix_content, warnings).
        appendix_content is None if no meta files found.
        """
        import json

        entries = []
        warnings: list[str] = []
        for agent_dir in sorted(self.research_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name == "output":
                continue
            meta_path = agent_dir / ".meta.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    warnings.append(f"  {agent_dir.name}/.meta.json: unreadable, skipped")
                    continue
                known = {
                    "direction",
                    "searched_links",
                    "tokens_total",
                    "model_id",
                    "temperature",
                    "thinking_level",
                    "duration",
                    "research_started_at",
                    "research_completed_at",
                }
                extra = set(data) - known
                if extra:
                    warnings.append(f"  {agent_dir.name}/.meta.json: unknown fields {sorted(extra)}")
                entries.append(data)
            else:
                md_files = list(agent_dir.glob("*.md"))
                if md_files:
                    warnings.append(f"  {agent_dir.name}/: has reports but missing .meta.json")

        if not entries:
            return None, warnings

        lines = [
            "---",
            'pagetitle: "Research Appendix"',
            "---",
            "",
            "# Appendix: Research Methodology",
            "",
            "| Direction | Model | Duration | Tokens | Links |",
            "|-----------|-------|----------|--------|-------|",
        ]
        for e in entries:
            raw = e.get("tokens_total", 0)
            links = len(e.get("searched_links", []))
            lines.append(
                f"| {e.get('direction', '?')} "
                f"| {e.get('model_id', '-')} "
                f"| {_format_duration(e)} "
                f"| {_format_tokens(raw)} "
                f"| {links} |"
            )

        lines.append("")
        lines.append("## Searched Links by Direction")
        lines.append("")
        for e in entries:
            links = e.get("searched_links", [])
            if links:
                lines.append(f"### {e.get('direction', '?')}")
                for url in links:
                    lines.append(f"- <{url}>")
                lines.append("")

        return "\n".join(lines), warnings

    # --- Generate ---

    @staticmethod
    def check_horizontal_rules(report_path: Path) -> list[str]:
        """Scan a report for --- horizontal rules in the body (not YAML frontmatter).

        Returns warning messages about any found. The Lua filter in pdf.py converts
        them to page breaks, but explicit section breaks (headings) are preferred.
        """
        text = report_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        warnings: list[str] = []
        frontmatter_closed = False
        frontmatter_open = False
        hr_lines: list[int] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped != "---":
                continue
            if not frontmatter_closed and i == 0:
                frontmatter_open = True
                continue
            if frontmatter_open and not frontmatter_closed:
                frontmatter_closed = True
                frontmatter_open = False
                continue
            hr_lines.append(i + 1)

        if hr_lines:
            warnings.append(
                f"  Found {len(hr_lines)} '---' horizontal rule(s) at lines {hr_lines[:5]}"
                f"{'...' if len(hr_lines) > 5 else ''}. "
                f"Will be converted to page breaks in PDF. "
                f"Consider using headings for section separation instead."
            )
        return warnings

    def generate_pdf(self, report_path: Path, appendix: str | None = None) -> tuple[bool, Path | str]:
        """Generate PDF from a markdown report. Returns (success, output_path)."""
        from deep_research.pdf import generate_pdf

        return generate_pdf(report_path, self.research_dir, appendix)

    def generate_html(self, report_path: Path, appendix: str | None = None) -> tuple[bool, Path | str]:
        """Generate HTML from a markdown report. Returns (success, output_path)."""
        from deep_research.pdf import generate_html

        return generate_html(report_path, self.research_dir, appendix)

    # --- Status ---

    def status(self) -> dict:
        return self.state.summary()

    def next_steps(self) -> list[str]:
        """Return human-readable next steps."""
        state = self.state.load()
        steps = []

        if state.phase == Phase.initialized:
            steps.append("Run `deep-research plan` to generate the research plan.")
        elif state.phase == Phase.planned:
            steps.append("Launch research agents in Claude Code. Use `deep-research agents --all` to get prompts.")
        elif state.phase == Phase.researching:
            pending = [a for a in state.agents if a.status == AgentStatus.pending]
            if pending:
                steps.append(f"Complete {len(pending)} pending research agents.")
            steps.append("Run `deep-research synthesize` when all agents are done.")
        elif state.phase == Phase.synthesized:
            steps.append("Run `deep-research validate` to check quality.")
            steps.append("Then run `deep-research generate` to produce the final PDF.")
        elif state.phase == Phase.reviewed:
            steps.append("Run `deep-research generate` to produce the final PDF.")
        elif state.phase == Phase.error:
            steps.append(f"Error: {state.error}")
            steps.append("Fix the issue and run `deep-research status` to resume.")
        else:
            steps.append("Research complete!")

        return steps
