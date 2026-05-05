"""PDF/HTML generation via pandoc + typst."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _skill_dir() -> Path | None:
    """Locate the runtime directory (for runtime/pixi.toml)."""
    pkg_root = Path(__file__).resolve().parent.parent.parent
    runtime_dir = pkg_root / "runtime"
    if (runtime_dir / "pixi.toml").exists():
        return runtime_dir
    # When running from installed package: check ~/.claude/skills/deep-research/
    claude_skills = Path.home() / ".claude" / "skills" / "deep-research"
    if (claude_skills / "pixi.toml").exists():
        return claude_skills
    return None


def _templates_dir() -> Path:
    """Locate the templates directory (project root)."""
    pkg_root = Path(__file__).resolve().parent.parent.parent
    t = pkg_root / "templates"
    if t.exists():
        return t
    # Fallback: installed skill
    claude_skills = Path.home() / ".claude" / "skills" / "deep-research"
    t2 = claude_skills / "templates"
    if t2.exists():
        return t2
    return pkg_root / "templates"


def _find_pixi() -> str:
    for cmd in ["pixi", "pixi.exe"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=True)
            return cmd
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    raise FileNotFoundError("pixi not found. Install pixi or run pandoc manually.")


def generate_pdf(report_path: Path, output_root: Path, appendix: str | None = None) -> tuple[bool, Path | str]:
    """Generate PDF from a markdown report using pandoc + typst.

    Returns (success, output_pdf_path).
    """
    report_path = report_path.resolve()
    output_dir = output_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = output_dir / f"{output_root.name}.pdf"

    skill = _skill_dir()
    templates = _templates_dir()

    if not report_path.exists():
        return False, f"Report not found: {report_path}"

    appendix_path = None
    if appendix:
        appendix_path = output_dir / ".appendix.md"
        appendix_path.write_text(appendix, encoding="utf-8")

    pandoc_args = [
        str(report_path),
        "-o",
        str(output_pdf),
        "--pdf-engine=typst",
        "--toc",
        "--toc-depth=3",
    ]
    if appendix_path:
        pandoc_args.insert(1, str(appendix_path))

    eq_cols = templates / "equal-cols.lua"
    if eq_cols.exists():
        pandoc_args.extend(["--lua-filter", str(eq_cols)])

    pagebreak_filter = templates / "pagebreak.lua"
    if pagebreak_filter.exists():
        pandoc_args.extend(["--lua-filter", str(pagebreak_filter)])

    style = templates / "style.typst"
    if style.exists():
        pandoc_args.extend(["--include-in-header", str(style)])

    import datetime

    today = datetime.date.today().isoformat()
    pandoc_args.extend(
        [
            "-V",
            f"title={report_path.parent.name}",
            "-V",
            f"date={today}",
            "-V",
            "author=Deep Research",
        ]
    )

    try:
        pixi = _find_pixi()
        cmd = [pixi, "run", "pandoc"] + pandoc_args

        cwd = str(skill) if skill else None

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=120,
            cwd=cwd,
        )
        if result.returncode != 0:
            return False, f"PDF generation failed:\n{result.stderr}"

        if output_pdf.exists() and output_pdf.stat().st_size > 0:
            return True, output_pdf
        else:
            return False, "PDF output file is empty or missing"

    except FileNotFoundError as e:
        return False, f"pandoc/typst not available: {e}"
    except subprocess.TimeoutExpired:
        return False, "PDF generation timed out after 120s"
    except Exception as e:
        return False, f"PDF generation error: {e}"


def generate_html(report_path: Path, output_root: Path, appendix: str | None = None) -> tuple[bool, Path | str]:
    """Generate HTML from a markdown report.

    Returns (success, output_html_path).
    """
    report_path = report_path.resolve()
    output_dir = output_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_html = output_dir / f"{output_root.name}.html"

    skill = _skill_dir()

    appendix_path = None
    if appendix:
        appendix_path = output_dir / ".appendix.md"
        appendix_path.write_text(appendix, encoding="utf-8")

    pandoc_args = [
        str(report_path),
        "-o",
        str(output_html),
        "--toc",
        "--toc-depth=3",
        "--standalone",
    ]
    if appendix_path:
        pandoc_args.insert(1, str(appendix_path))

    try:
        pixi = _find_pixi()
        cmd = [pixi, "run", "pandoc"] + pandoc_args

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=120,
            cwd=str(skill) if skill else None,
        )
        if result.returncode != 0:
            return False, f"HTML generation failed:\n{result.stderr}"

        return True, output_html

    except FileNotFoundError as e:
        return False, f"pandoc/typst not available: {e}"
    except subprocess.TimeoutExpired:
        return False, "HTML generation timed out after 120s"
    except OSError as e:
        return False, f"HTML generation error: {e}"
