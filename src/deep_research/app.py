"""Deep Research CLI — orchestrate multi-agent research with quality gates."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import typer
from rich.console import Console

# Force UTF-8 encoding on Windows to prevent GBK encoding errors
if sys.platform == "win32" and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from rich.panel import Panel
from rich.table import Table

from deep_research import __version__
from deep_research.project import ResearchProject

app = typer.Typer(
    name="deep-research",
    help="Enterprise-grade research orchestration with multi-source synthesis and quality gates.",
    no_args_is_help=True,
)
console = Console()

OUTPUT_DIR_OPTION = typer.Option(
    None,
    "--dir",
    "-d",
    help="Output directory (default: ./docs/research/<topic-slug>)",
)


def _resolve_project(dir_path: Path | None = None) -> ResearchProject:
    """Find and load a research project from the given or CWD-relative directory."""
    if dir_path:
        target = Path(dir_path)
        state_file = target / ".deep-research-state.json"
        if not state_file.exists():
            console.print("[red]No research project found.[/red]")
            console.print("Run [bold]deep-research init <topic>[/bold] to create one.")
            raise typer.Exit(1)
        return ResearchProject(target)

    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        state_file = parent / ".deep-research-state.json"
        if state_file.exists():
            return ResearchProject(parent)
        # Also check docs/research subdirs
        research_dir = parent / "docs" / "research"
        if research_dir.exists():
            # Sort by state file mtime (most recent first) so the newest
            # project is picked when running without --dir
            candidates = []
            for sub in research_dir.iterdir():
                state_file = sub / ".deep-research-state.json"
                if sub.is_dir() and state_file.exists():
                    candidates.append((state_file.stat().st_mtime, sub))
            candidates.sort(key=lambda x: x[0], reverse=True)
            if candidates:
                return ResearchProject(candidates[0][1])

    console.print("[red]No research project found.[/red]")
    console.print("Run [bold]deep-research init <topic>[/bold] to create one.")
    raise typer.Exit(1)


def _report_path(report_name: str | None, project: ResearchProject) -> Path:
    """Resolve the report path. Defaults to the project's README.md."""
    if report_name is None:
        return (project.research_dir / "README.md").resolve()
    p = Path(report_name)
    return p if p.is_absolute() else (Path.cwd() / p).resolve()


# ─── Commands ───


@app.command()
def init(
    topic: str = typer.Argument(..., help="Research topic"),
    fast: bool = typer.Option(False, "--fast", "-f", help="Skip requirements clarification step"),
    language: str = typer.Option(
        "",
        "--lang",
        "-l",
        help="Report language (default: auto-detect from topic)",
    ),
    output_dir: Path | None = OUTPUT_DIR_OPTION,
):
    """Initialize a new research project."""
    project = ResearchProject.init(topic, language, output_dir, fast=fast)
    console.print(
        Panel.fit(
            f"[bold green]Research project initialized[/bold green]\n\n"
            f"Topic:  {topic}\n"
            f"Fast:   {fast}\n"
            f"Lang:   {language}\n"
            f"Output: {project.research_dir}",
            title="deep-research",
        )
    )
    if fast:
        console.print("\nNext: [bold]deep-research plan[/bold] to generate the research plan.")
    else:
        console.print("\nNext: Write requirements to requirements.md, confirm, then run deep-research plan.")


@app.command()
def plan(
    directions: list[str] = typer.Argument(None, help="Direction names (e.g. pricing capability)"),
    agents: int | None = typer.Option(
        None,
        "--agents",
        "-a",
        help="Number of research agents (default: auto based on mode)",
    ),
    dir: Path | None = OUTPUT_DIR_OPTION,
):
    """Generate research plan with agent definitions."""
    project = _resolve_project(dir)
    if not directions and not agents:
        console.print("[red]Either provide direction names or --agents count.[/red]")
        console.print("Example: deep-research plan \"方向1\" \"方向2\" \"方向3\"")
        console.print("Example: deep-research plan --agents 8")
        raise typer.Exit(1)
    plan_path = project.create_plan(directions=directions, agent_count=agents)
    console.print(f"[green]Plan written:[/green] {plan_path}")
    n_agents = len(project.list_agents())
    console.print(f"Created {n_agents} agent directories with .meta.json templates.")


@app.command("agents")
def list_agents(
    all: bool = typer.Option(False, "--all", "-a", help="Show all agent prompts"),
    agent_id: int | None = typer.Option(None, "--id", "-i", help="Show specific agent prompt"),
    dir: Path | None = OUTPUT_DIR_OPTION,
):
    """List research agents and show their prompts."""
    project = _resolve_project(dir)
    agents = project.list_agents()

    if not agents:
        console.print("[yellow]No agents defined. Run [bold]deep-research plan[/bold] first.[/yellow]")
        raise typer.Exit(0)

    if agent_id is not None:
        agent = project.get_agent(agent_id)
        if not agent:
            console.print(f"[red]Agent #{agent_id} not found.[/red]")
            raise typer.Exit(1)
        console.print(
            Panel(
                project.format_agent_prompt(agent),
                title=f"Agent #{agent.id:02d}: {agent.topic}",
            )
        )
        return

    # Show table
    table = Table(title=f"Research Agents ({len(agents)} total)")
    table.add_column("#", style="dim")
    table.add_column("Topic")
    table.add_column("Status")
    table.add_column("Report")

    for a in agents:
        status_style = {
            "pending": "yellow",
            "in_progress": "blue",
            "complete": "green",
            "failed": "red",
        }.get(a.status.value, "white")
        table.add_row(
            str(a.id),
            a.topic,
            f"[{status_style}]{a.status.value}[/{status_style}]",
            a.report_path or "-",
        )
    console.print(table)

    if all:
        console.print("\n[bold]Agent Prompts:[/bold]\n")
        for a in agents:
            console.print(
                Panel(
                    project.format_agent_prompt(a),
                    title=f"Agent #{a.id:02d}: {a.topic}",
                )
            )


@app.command()
def status(
    dir: Path | None = OUTPUT_DIR_OPTION,
):
    """Show research project status and next steps."""
    try:
        project = _resolve_project(dir)
    except typer.Exit:
        return

    s = project.status()

    panel_lines = [
        f"[bold]Topic:[/bold] {s['topic']}",
        f"[bold]Phase:[/bold] [cyan]{s['phase']}[/cyan]",
        f"[bold]Language:[/bold] {s['language']}",
        f"[bold]Output:[/bold] {s['output_dir']}",
    ]
    if s.get("error"):
        panel_lines.append(f"\n[red]Error: {s['error']}[/red]")

    console.print(Panel.fit("\n".join(panel_lines), title="Research Status"))

    # Phase table
    table = Table("Phase", "Status")
    for phase_name, phase_status in s["phases"].items():
        style = {
            "complete": "green",
            "in_progress": "blue",
            "pending": "dim",
            "failed": "red",
        }.get(phase_status, "white")
        table.add_row(phase_name, f"[{style}]{phase_status}[/{style}]")
    console.print(table)

    # Agent summary
    if s["agent_count"] > 0:
        agent_counts = s["agent_status"]
        console.print(
            f"\nAgents: {s['agent_count']} total | "
            f"[green]{agent_counts.get('complete', 0)} done[/green] | "
            f"[yellow]{agent_counts.get('pending', 0)} pending[/yellow] | "
            f"[red]{agent_counts.get('failed', 0)} failed[/red]"
        )

    # Next steps
    steps = project.next_steps()
    if steps:
        console.print("\n[bold]Next steps:[/bold]")
        for step in steps:
            console.print(f"  - {step}")


@app.command()
def validate(
    report: str | None = typer.Argument(None, help="Path to report (default: project README.md)"),
    strict: bool = typer.Option(False, "--strict", "-s", help="Strict mode"),
    dir: Path | None = OUTPUT_DIR_OPTION,
):
    """Run quality checks on a research report."""
    project = _resolve_project(dir)
    report_path = _report_path(report, project)
    if not report_path.exists():
        console.print(f"[red]Report not found: {report_path}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Checking URLs in:[/bold] {report_path}\n")

    # Phase 1: meta integrity — catch missing .meta.json before it's too late
    meta_errors, meta_warnings = project.check_meta_integrity()
    if meta_errors:
        console.print("[bold red]Missing .meta.json — fix before generate:[/bold red]")
        for e in meta_errors:
            console.print(f"[red]{e}[/red]")
    if meta_warnings:
        console.print("[yellow]Meta warnings:[/yellow]")
        for w in meta_warnings:
            console.print(f"[yellow]{w}[/yellow]")

    from deep_research.quality import check_report_urls

    passed, output = check_report_urls(report_path)

    console.print(output)

    if passed and not meta_errors:
        console.print("\n[bold green]All checks passed![/bold green]")
    else:
        if meta_errors:
            console.print("\n[bold red]Meta integrity check failed. See errors above.[/bold red]")
        if not passed:
            console.print("\n[bold red]Some URLs are inaccessible. Review and fix before delivery.[/bold red]")
        raise typer.Exit(1)


@app.command()
def generate(
    report: str | None = typer.Option(None, "--report", "-r", help="Report file (default: project README.md)"),
    format: str = typer.Option("pdf", "--format", "-f", help="Output format: pdf or html"),
    dir: Path | None = OUTPUT_DIR_OPTION,
):
    """Generate PDF or HTML from a research report."""
    project = _resolve_project(dir)
    report_path = _report_path(report, project)

    if not report_path.exists():
        console.print(f"[red]Report not found: {report_path}[/red]")
        raise typer.Exit(1)

    # Collect appendix and check for warnings
    appendix, warnings = project.generate_appendix()
    hr_warnings = project.check_horizontal_rules(report_path)
    if hr_warnings:
        warnings.extend(hr_warnings)
    if warnings:
        console.print("[yellow]╔══ Pre-flight warnings ══╗[/yellow]")
        for w in warnings:
            console.print(f"[yellow]{w}[/yellow]")
        console.print("[yellow]╚══════════════════════════╝[/yellow]")

    if format == "pdf":
        success, result = project.generate_pdf(report_path, appendix)
    elif format == "html":
        success, result = project.generate_html(report_path, appendix)
    else:
        console.print(f"[red]Unknown format: {format}[/red] (use pdf or html)")
        raise typer.Exit(1)

    if success:
        console.print(f"[green]Generated:[/green] {result}")
    else:
        console.print(f"[red]Failed:[/red] {result}")
        raise typer.Exit(1)


@app.command()
def resume(
    dir: Path | None = OUTPUT_DIR_OPTION,
):
    """Show next steps to resume an interrupted research project."""
    project = _resolve_project(dir)
    steps = project.next_steps()
    s = project.status()

    console.print(
        Panel.fit(
            f"[bold]Phase:[/bold] [cyan]{s['phase']}[/cyan]\n[bold]Topic:[/bold] {s['topic']}",
            title="Resume Research",
        )
    )
    for step in steps:
        console.print(f"  - {step}")


@app.command("add")
def add_direction(
    name: str = typer.Argument(..., help="New research direction name"),
    dir: Path | None = OUTPUT_DIR_OPTION,
):
    """Add a new research direction after the plan is created."""
    project = _resolve_project(dir)
    agent = project.add_direction(name)
    console.print(f"[green]Added:[/green] {name} → {agent.output_dir}")
    console.print("  .meta.json template pre-created. Agent fills in after research.")


@app.command("phase")
def set_phase(
    phase_name: str = typer.Argument(..., help="Phase to mark complete (plan, agents, synthesize, reviewed, generate)"),
    dir: Path | None = OUTPUT_DIR_OPTION,
):
    """Mark a pipeline phase as complete. Use when agents run outside CLI tracking."""
    valid = {"plan", "agents", "synthesize", "reviewed", "generate"}
    if phase_name not in valid:
        console.print(f"[red]Unknown phase: {phase_name}[/red]. Valid: {', '.join(sorted(valid))}")
        raise typer.Exit(1)
    project = _resolve_project(dir)
    project.state.update_phase(phase_name, "complete")
    console.print(f"[green]Phase '{phase_name}' marked complete.[/green]")


def _version_callback(value: bool):
    if value:
        console.print(f"deep-research v{__version__}")
        raise typer.Exit(0)


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
):
    """Enterprise-grade research orchestration with multi-source synthesis and quality gates."""
    pass


def main():
    app()


if __name__ == "__main__":
    main()
