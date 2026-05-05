# Deep Research CLI

Enterprise-grade research orchestration tool with multi-source synthesis, citation tracking, and PDF generation.

## Features

- **Multi-agent research** — decompose a topic into directions, research in parallel
- **Quality gates** — URL accessibility checking, reference format validation
- **PDF generation** — auto-generated appendix with model metadata, token usage, and searched links
- **Checkpoint/resume** — state machine persists progress, supports interruption recovery
- **Late direction addition** — add new research directions mid-workflow

## Environments

The project uses two pixi environments:

| Env | File | Tools |
|-----|------|-------|
| **dev** (default) | `pixi.toml` (root) | ruff, mypy, pytest, prettier, tombi |
| **runtime** | `runtime/pixi.toml` | python, pandoc, typst, typer, rich |

```bash
# Run CLI commands
pixi run deep-research init "topic"

# Run dev tools
pixi run lint
pixi run test
pixi run format
pixi run typecheck
```

## Structure

```
├── pyproject.toml           # Package build config
├── pixi.toml                # Dev environment
├── runtime/
│   └── pixi.toml            # Runtime environment
└── src/deep_research/
    ├── app.py               # CLI entry point (8 commands)
    ├── project.py           # Project lifecycle management
    ├── state.py             # JSON state machine
    ├── models.py            # Data models
    ├── quality.py           # URL/report validation
    └── pdf.py               # PDF/HTML generation
```

See [SKILL.md](SKILL.md) for the research workflow.

## Install

Copy these files to `skills/deep-research/`:

```
src/                    # Python source code
runtime/pixi.toml       # Runtime environment (python, pandoc, typst)
runtime/pixi.lock
SKILL.md                # Skill definition
templates/              # PDF templates
```
