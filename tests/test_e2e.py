"""E2E tests: simulate full research lifecycle without real LLM calls.

The CLI doesn't call LLM APIs — it manages files and state.
We can simulate the full flow by:
1. Creating a project via CLI
2. Writing dummy agent reports as the agents would
3. Generating appendix from .meta.json
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from deep_research.app import app
from deep_research.project import ResearchProject

runner = CliRunner()


class TestE2EFullLifecycle:
    """Simulate: init → plan → add → (agents write reports) → appendix."""

    def test_init_plan_add(self, tmp_path: Path):
        target = tmp_path / "e2e-lifecycle"
        r1 = runner.invoke(app, ["init", "E2E Test", "--dir", str(target)])
        assert r1.exit_code == 0
        assert (target / "requirements.md").exists()

        r2 = runner.invoke(app, ["plan", "pricing", "capability", "latency", "--dir", str(target)])
        assert r2.exit_code == 0
        assert (target / "plan.md").exists()
        assert (target / "pricing").is_dir()
        assert (target / "capability").is_dir()

        r3 = runner.invoke(app, ["add", "benchmark", "--dir", str(target)])
        assert r3.exit_code == 0
        assert (target / "benchmark").is_dir()

    def test_agents_write_reports_then_appendix(self, tmp_path: Path):
        """Simulate research agents writing .md reports and .meta.json."""
        target = tmp_path / "e2e-reports"
        runner.invoke(app, ["init", "E2E", "--dir", str(target)])
        runner.invoke(app, ["plan", "overview", "comparison", "--dir", str(target)])

        (target / "overview" / "overview.md").write_text("# Overview\nContent.\n## References\n[1] A. https://x.com\n")
        meta1 = {
            "direction": "overview",
            "searched_links": ["https://example.com/overview"],
            "duration": "15min",
            "tokens_total": 60_000,
        }
        (target / "overview" / ".meta.json").write_text(json.dumps(meta1), encoding="utf-8")

        (target / "comparison" / "pricing.md").write_text("# Pricing\nContent.\n## References\n[1] B. https://y.com\n")
        (target / "comparison" / "benchmark.md").write_text("# Benchmark\nContent.\n## References\n[2] C. https://z.com\n")
        meta2 = {
            "direction": "comparison",
            "searched_links": ["https://example.com/a", "https://example.com/b"],
            "duration": "10min",
            "tokens_total": 38_000,
        }
        (target / "comparison" / ".meta.json").write_text(json.dumps(meta2), encoding="utf-8")

        rp = ResearchProject(target)
        content, warnings = rp.generate_appendix()
        assert content is not None
        assert warnings == []
        assert "60.0k" in content
        assert "38.0k" in content
        assert "overview" in content
        assert "comparison" in content
        assert "example.com" in content

    def test_appendix_without_meta(self, tmp_path: Path):
        """No meta files → appendix is None (delete pre-created templates first)."""
        target = tmp_path / "e2e-no-meta"
        runner.invoke(app, ["init", "E2E", "--dir", str(target)])
        runner.invoke(app, ["plan", "test-dir", "--dir", str(target)])
        # Remove pre-created .meta.json to simulate agent not filling it
        for meta in target.rglob(".meta.json"):
            meta.unlink()
        content, _ = ResearchProject(target).generate_appendix()
        assert content is None

    def test_add_direction_after_reports(self, tmp_path: Path):
        """Add a new direction after agents have already reported."""
        target = tmp_path / "e2e-late-add"
        runner.invoke(app, ["init", "E2E", "--dir", str(target)])
        runner.invoke(app, ["plan", "pricing", "capability", "--dir", str(target)])

        (target / "pricing" / "report.md").write_text("# A\n")
        (target / "capability" / "report.md").write_text("# B\n")

        r3 = runner.invoke(app, ["add", "latency", "--dir", str(target)])
        assert r3.exit_code == 0
        assert (target / "latency").is_dir()

