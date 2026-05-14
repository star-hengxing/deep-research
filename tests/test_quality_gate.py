"""Tests for quality gate layers 1-2."""

from __future__ import annotations

from pathlib import Path

from deep_research.quality import (
    Finding,
    Severity,
    check_evidence,
    check_structure,
    run_quality_gate,
)


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _sev(findings: list[Finding], check: str) -> Severity:
    return next(f.severity for f in findings if f.check == check)


def _find(findings: list[Finding], check: str) -> Finding:
    return next(f for f in findings if f.check == check)


# ── Layer 1: Structure ──


class TestStructure:
    def test_full_coverage(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(
            proj / "plan.md",
            "| Agent | Direction | Sub |\n|---|---|---|\n| pricing | pricing | x |\n| latency | latency | x |\n",
        )
        _write(
            proj / "README.md",
            "# Report\n\n## 摘要\n\n" + "测试内容。" * 50 + "\n\n## pricing\n\nSome text.\n\n## latency\n\nMore.\n\n## 参考文献\n\n[1] Ref one.\n",
        )
        (proj / "pricing").mkdir()
        _write(proj / "pricing" / "report.md", "content")
        (proj / "latency").mkdir()
        _write(proj / "latency" / "report.md", "content")

        findings = check_structure(proj / "README.md", proj)
        assert _sev(findings, "章节覆盖") == Severity.INFO
        assert _sev(findings, "摘要") == Severity.INFO
        assert _sev(findings, "参考文献") == Severity.INFO
        assert _sev(findings, "Agent 报告") == Severity.INFO

    def test_missing_direction(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(
            proj / "plan.md",
            "| Agent | Direction | Sub |\n|---|---|---|\n| pricing | pricing | x |\n| latency | latency | x |\n",
        )
        _write(
            proj / "README.md",
            "# Report\n\n## 摘要\n\n" + "测试。" * 60 + "\n\n## pricing\n\nText.\n\n## 参考文献\n\n[1] Ref.\n",
        )
        (proj / "pricing").mkdir()
        _write(proj / "pricing" / "r.md", "x")
        (proj / "latency").mkdir()
        _write(proj / "latency" / "r.md", "x")

        findings = check_structure(proj / "README.md", proj)
        f = _find(findings, "章节覆盖")
        assert f.severity == Severity.FAIL
        assert "1/2" in f.message
        assert any("latency" in d for d in f.details)

    def test_no_summary(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(proj / "README.md", "# Report\n\nSome text.\n\n## 参考文献\n\n[1] Ref.\n")
        findings = check_structure(proj / "README.md", proj)
        assert _sev(findings, "摘要") == Severity.FAIL

    def test_short_summary(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(proj / "README.md", "# Report\n\n## 摘要\n\nToo short.\n\n## 参考文献\n\n[1] Ref.\n")
        findings = check_structure(proj / "README.md", proj)
        assert _sev(findings, "摘要") == Severity.FAIL

    def test_no_references(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(proj / "README.md", "# Report\n\n## 摘要\n\n" + "内容。" * 60 + "\n")
        findings = check_structure(proj / "README.md", proj)
        assert _sev(findings, "参考文献") == Severity.FAIL

    def test_word_count_warn(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(
            proj / "plan.md",
            "| Agent | Direction | Sub |\n|---|---|---|\n| a | a | x |\n| b | b | x |\n| c | c | x |\n",
        )
        _write(
            proj / "README.md",
            "# Report\n\n## 摘要\n\n" + "短。" * 60 + "\n\n## 参考文献\n\n[1] Ref.\n",
        )
        findings = check_structure(proj / "README.md", proj)
        assert _sev(findings, "字数") == Severity.WARN

    def test_missing_agent_report(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(proj / "README.md", "# Report\n\n## 摘要\n\n" + "内容。" * 60 + "\n\n## 参考文献\n\n[1] Ref.\n")
        (proj / "empty-agent").mkdir()

        findings = check_structure(proj / "README.md", proj)
        f = _find(findings, "Agent 报告")
        assert f.severity == Severity.FAIL
        assert "empty-agent" in f.details


# ── Layer 2: Evidence ──


class TestEvidence:
    def test_good_citations(self, tmp_path: Path):
        report = tmp_path / "report.md"
        _write(
            report,
            "# Report\n\n"
            "First paragraph with citation [1].\n\n"
            "Second paragraph with citation [2].\n\n"
            "Third paragraph with citation [3].\n\n"
            "## 参考文献\n\n"
            "[1] Source one. https://example.com\n\n"
            "[2] Source two. https://other.org\n\n"
            "[3] Source three. https://third.net\n",
        )
        findings = check_evidence(report)
        assert _sev(findings, "引用密度") == Severity.INFO
        assert _sev(findings, "引用可追溯") == Severity.INFO
        assert _sev(findings, "幽灵引用") == Severity.INFO

    def test_low_citation_density(self, tmp_path: Path):
        report = tmp_path / "report.md"
        paras = "\n\n".join(f"Paragraph {i} with no citation." for i in range(10))
        _write(report, f"# Report\n\n{paras}\n\n## References\n\n")
        findings = check_evidence(report)
        assert _sev(findings, "引用密度") == Severity.WARN

    def test_orphan_claims(self, tmp_path: Path):
        report = tmp_path / "report.md"
        _write(
            report,
            "# Report\n\n"
            "销量突破100万份 but no citation here.\n\n"
            "市场份额达到23% is also uncited.\n\n"
            "This has a citation 50% [1].\n\n"
            "## 参考文献\n\n[1] Ref.\n",
        )
        findings = check_evidence(report)
        f = _find(findings, "孤立断言")
        assert f.severity == Severity.WARN
        assert len(f.details) == 2

    def test_missing_reference_entry(self, tmp_path: Path):
        report = tmp_path / "report.md"
        _write(
            report,
            "# Report\n\nCited [1] and [2] and [3].\n\n## References\n\n[1] Source one.\n\n[2] Source two.\n",
        )
        findings = check_evidence(report)
        f = _find(findings, "引用可追溯")
        assert f.severity == Severity.FAIL
        assert "[3]" in f.details

    def test_ghost_references(self, tmp_path: Path):
        report = tmp_path / "report.md"
        _write(
            report,
            "# Report\n\nOnly cite [1].\n\n## References\n\n[1] Used.\n\n[2] Never cited.\n\n[3] Also unused.\n",
        )
        findings = check_evidence(report)
        f = _find(findings, "幽灵引用")
        assert f.severity == Severity.WARN
        assert "[2]" in f.details
        assert "[3]" in f.details

    def test_source_diversity_low(self, tmp_path: Path):
        report = tmp_path / "report.md"
        _write(
            report,
            "# Report\n\nText [1] [2].\n\n"
            "## References\n\n"
            "[1] https://example.com/a\n\n"
            "[2] https://example.com/b\n",
        )
        findings = check_evidence(report)
        f = _find(findings, "来源多样性")
        assert f.severity == Severity.WARN

    def test_source_diversity_good(self, tmp_path: Path):
        report = tmp_path / "report.md"
        refs = "\n\n".join(
            f"[{i}] https://site{i}.com/page" for i in range(1, 7)
        )
        cites = " ".join(f"[{i}]" for i in range(1, 7))
        _write(report, f"# Report\n\nText {cites}.\n\n## References\n\n{refs}\n")
        findings = check_evidence(report)
        assert _sev(findings, "来源多样性") == Severity.INFO


# ── Integration ──


class TestQualityGate:
    def test_passing_gate(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(
            proj / "README.md",
            "# Report\n\n## 摘要\n\n" + "这是一份高质量报告的摘要内容。" * 20 + "\n\n"
            "数据来源充分 [1]。分析透彻 [2]。\n\n"
            "另一段内容 [3]。更多分析 [4]。\n\n"
            "## 参考文献\n\n"
            "[1] Source. https://a.com\n\n"
            "[2] Source. https://b.org\n\n"
            "[3] Source. https://c.net\n\n"
            "[4] Source. https://d.io\n\n"
            "[5] Source. https://e.dev\n",
        )
        passed, output = run_quality_gate(proj / "README.md", proj)
        assert passed
        assert "Quality Gate" in output

    def test_failing_gate(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(proj / "README.md", "# Report\n\nShort report without refs or summary.\n")
        passed, output = run_quality_gate(proj / "README.md", proj)
        assert not passed
        assert "✗" in output

    def test_strict_mode_warnings(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write(
            proj / "README.md",
            "# Report\n\n## 摘要\n\n" + "内容。" * 60 + "\n\n"
            "研究表明这是事实 [1]。\n\n"
            "## 参考文献\n\n[1] Ref. https://a.com\n",
        )
        passed, output = run_quality_gate(proj / "README.md", proj)
        # Gate passes (no FAIL), but has warnings
        assert passed
        assert "⚠" in output
