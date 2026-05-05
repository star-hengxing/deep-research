"""CLI integration tests using Typer CliRunner (no real subprocess)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from deep_research.app import app

runner = CliRunner()


class TestCLIInit:
    def test_init_creates_project(self, tmp_path: Path):
        target = tmp_path / "test-project"
        result = runner.invoke(app, ["init", "Test Project", "--dir", str(target)])
        assert result.exit_code == 0
        assert (target / "requirements.md").exists()
        assert (target / ".deep-research-state.json").exists()

    def test_init_fast_skips_requirements(self, tmp_path: Path):
        target = tmp_path / "fast-mode"
        result = runner.invoke(app, ["init", "Fast", "--fast", "--dir", str(target)])
        assert result.exit_code == 0
        assert not (target / "requirements.md").exists()

    def test_init_accepts_lang_flag(self, tmp_path: Path):
        target = tmp_path / "en-mode"
        result = runner.invoke(app, ["init", "English", "--lang", "en", "--dir", str(target)])
        assert result.exit_code == 0


class TestCLIPlan:
    def test_plan_needs_existing_project(self, tmp_path: Path):
        result = runner.invoke(app, ["plan", "--dir", str(tmp_path / "nonexistent")])
        assert result.exit_code != 0
        assert "No research project found" in result.stdout

    def test_plan_after_init(self, tmp_path: Path):
        target = tmp_path / "test-plan"
        runner.invoke(app, ["init", "Test", "--dir", str(target)])
        result = runner.invoke(app, ["plan", "--agents", "3", "--dir", str(target)])
        assert result.exit_code == 0
        assert (target / "plan.md").exists()


class TestCLIAdd:
    def test_add_direction(self, tmp_path: Path):
        target = tmp_path / "test-add"
        runner.invoke(app, ["init", "Test", "--dir", str(target)])
        runner.invoke(app, ["plan", "--dir", str(target)])
        result = runner.invoke(app, ["add", "pricing", "--dir", str(target)])
        assert result.exit_code == 0
        assert "pricing" in result.stdout


class TestCLIAgents:
    def test_agents_needs_project(self, tmp_path: Path):
        result = runner.invoke(app, ["agents", "--dir", str(tmp_path / "missing")])
        assert result.exit_code != 0

    def test_agents_lists_after_plan(self, tmp_path: Path):
        target = tmp_path / "test-agents"
        runner.invoke(app, ["init", "Test", "--dir", str(target)])
        runner.invoke(app, ["plan", "pricing", "latency", "--dir", str(target)])
        result = runner.invoke(app, ["agents", "--dir", str(target)])
        assert result.exit_code == 0
        assert "pricing" in result.stdout or "Agent" in result.stdout


class TestCLIStatus:
    def test_status_after_init(self, tmp_path: Path):
        target = tmp_path / "test-status"
        runner.invoke(app, ["init", "Test", "--dir", str(target)])
        result = runner.invoke(app, ["status", "--dir", str(target)])
        assert result.exit_code == 0
        assert "initialized" in result.stdout


class TestCLIValidate:
    def test_validate_missing_report(self, tmp_path: Path):
        target = tmp_path / "test-val"
        runner.invoke(app, ["init", "Test", "--dir", str(target)])
        result = runner.invoke(app, ["validate", "missing.md", "--dir", str(target)])
        assert result.exit_code != 0

