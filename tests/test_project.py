"""Tests for project.py — lifecycle, formatting, appendix."""

from __future__ import annotations

import json
from pathlib import Path

from deep_research.models import Phase
from deep_research.project import (
    ResearchProject,
    _format_tokens,
    default_output_dir,
    slugify,
)

# ─── Pure unit tests (no I/O) ───


class TestSlugify:
    def test_basic(self):
        assert slugify("AI API Comparison") == "ai-api-comparison"

    def test_special_chars(self):
        assert slugify("Hello World! @#$") == "hello-world"

    def test_multiple_spaces(self):
        assert slugify("lots   of   spaces") == "lots-of-spaces"

    def test_truncated(self):
        long = "a" * 100
        assert len(slugify(long)) <= 80

    def test_trailing_dash_removed(self):
        assert slugify("hello-") == "hello"
        assert slugify("test   ") == "test"


class TestFormatTokens:
    def test_raw_number(self):
        assert _format_tokens(800) == "800"
        assert _format_tokens(0) == "0"

    def test_thousands(self):
        assert _format_tokens(120_300) == "120.3k"
        assert _format_tokens(1_000) == "1.0k"
        assert _format_tokens(1_500) == "1.5k"

    def test_millions(self):
        assert _format_tokens(1_500_000) == "1.5m"
        assert _format_tokens(2_100_000) == "2.1m"

    def test_none(self):
        assert _format_tokens(None) == "-"

    def test_string_input(self):
        assert _format_tokens("120000") == "120.0k"

    def test_float_input(self):
        assert _format_tokens(1500.0) == "1.5k"

    def test_bad_value(self):
        assert _format_tokens("abc") == "-"


class TestDefaultOutputDir:
    def test_basic(self, tmp_path: Path):
        d = default_output_dir("AI APIs", base=tmp_path)
        assert d == tmp_path / "docs" / "research" / "ai-apis"

    def test_default_base_is_cwd(self):
        d = default_output_dir("test")
        assert d.relative_to(Path.cwd())


# ─── Integration tests (filesystem) ───


class TestResearchProjectInit:
    def test_init_creates_directory(self, project_dir: Path):
        target = project_dir.parent / "new-project"
        rp = ResearchProject.init("New Project", output_dir=target)
        assert rp.research_dir.exists()
        assert (rp.research_dir / "requirements.md").exists()
        assert (rp.research_dir / ".deep-research-state.json").exists()

    def test_init_creates_requirements_placeholder(self, project_dir: Path):
        ResearchProject.init("Test", output_dir=project_dir)
        req = project_dir / "requirements.md"
        assert req.exists()
        content = req.read_text(encoding="utf-8")
        assert "Requirements:" in content
        assert "User Requirements" in content

    def test_init_sets_phase(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        assert rp.state.load().phase == Phase.initialized

class TestResearchProjectPlan:
    def test_create_plan_generates_plan_md(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        plan_path = rp.create_plan()
        assert plan_path.name == "plan.md"
        assert plan_path.exists()

    def test_create_plan_creates_dirs(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["pricing", "latency"])
        assert (project_dir / "pricing").is_dir()
        assert (project_dir / "latency").is_dir()

    def test_create_plan_sets_state(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["pricing"])
        state = rp.state.load()
        assert state.phase == Phase.planned
        assert len(state.agents) == 1

    def test_create_plan_respects_directions(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["pricing", "latency", "capability"])
        assert len(rp.state.load().agents) == 3

    def test_create_plan_writes_directions_table(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["pricing", "capability"])
        content = (project_dir / "plan.md").read_text()
        assert "pricing" in content
        assert "capability" in content


class TestResearchProjectAgents:
    def test_add_direction(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["pricing", "latency"])
        agent = rp.add_direction("benchmark")
        assert agent.id == 3
        assert agent.topic == "benchmark"
        assert (project_dir / "benchmark").exists()

    def test_add_direction_persists(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["pricing"])
        rp.add_direction("latency")
        assert len(rp.state.load().agents) == 2

    def test_list_agents(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["a", "b", "c"])
        agents = rp.list_agents()
        assert len(agents) == 3

    def test_get_agent_by_id(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["a", "b", "c"])
        agent = rp.get_agent(2)
        assert agent is not None
        assert agent.id == 2

    def test_get_agent_missing(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        assert rp.get_agent(99) is None


class TestResearchProjectAppendix:
    def test_no_meta_returns_none(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        content, warnings = rp.generate_appendix()
        assert content is None
        assert warnings == []

    def test_generates_table_from_meta(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["pricing"])

        meta = {
            "direction": "pricing",
            "duration": "30min",
            "tokens_total": 125_300,
            "searched_links": ["https://openai.com/pricing"],
        }
        meta_path = project_dir / "pricing" / ".meta.json"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        content, warnings = rp.generate_appendix()
        assert content is not None
        assert warnings == []
        assert "pricing" in content
        assert "125.3k" in content
        assert "openai.com" in content

    def test_multiple_agents(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(directions=["dir-1", "dir-2"])

        for name in ["dir-1", "dir-2"]:
            meta = {"direction": name, "searched_links": [f"https://example.com/{name}"]}
            meta_path = project_dir / name / ".meta.json"
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

        content, warnings = rp.generate_appendix()
        assert content is not None
        assert "dir-1" in content
        assert "dir-2" in content


class TestResearchProjectStatus:
    def test_status_after_init(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        s = rp.status()
        assert s["phase"] == "initialized"
        assert s["topic"] == "Test"

    def test_next_steps_initialized(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        steps = rp.next_steps()
        assert any("plan" in s for s in steps)

    def test_next_steps_planned(self, project_dir: Path):
        rp = ResearchProject.init("Test", output_dir=project_dir)
        rp.create_plan(agent_count=2)
        steps = rp.next_steps()
        assert any("agent" in s for s in steps)
