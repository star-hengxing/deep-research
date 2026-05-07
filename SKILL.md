---
name: deep-research
description: Enterprise-grade research with multi-source synthesis, citation tracking, and PDF generation
---

# Deep Research

Orchestrate a structured research pipeline using the `deep-research` CLI.

Run CLI commands from the `runtime/` directory:
```bash
cd runtime
pixi run deep-research init "<topic>" [--fast]
pixi run deep-research plan "方向1" "方向2" ...    # pre-creates dirs + .meta.json
pixi run deep-research add "新方向"                # add single direction post-plan
pixi run deep-research agents                     # summary table (use --id N for prompt)
pixi run deep-research status
pixi run deep-research validate
pixi run deep-research generate                    # default: --engine kami (weasyprint)
pixi run deep-research generate --engine typst      # fallback: pandoc + typst
```

## When to Use

Complex analysis, technology comparisons, multi-perspective investigation, market research — anything requiring 5+ sources and structured synthesis.

## When NOT to Use

Simple lookups, debugging, 1-2 search answers, quick time-sensitive queries.

## Workflow

1. **Init** — `deep-research init "topic"` creates directory and state (use `--fast` to skip requirements step)
2. **Requirements** — main agent writes user requirements to `requirements.md`, user confirms
3. **Plan** — `deep-research plan "方向1" "方向2" ...` generates `plan.md` with direction decomposition AND pre-creates agent dirs with `.meta.json` templates. Always pass explicit direction names.
4. **Research** — launch agents in Claude Code using `deep-research agents --all` prompts; each writes `.md` reports **progressively** (section by section, use Edit to append) and **fills in** the pre-created `.meta.json` (model, tokens, searched links, duration)
5. **Synthesize** — main agent switches to the most capable model, reads all agent reports and `.meta.json`, writes comprehensive `README.md` **progressively** (section by section, Edit-append). Verify every agent filled `.meta.json` — missing ones break the appendix.
6. **Validate** — `deep-research validate` (resolves project README.md automatically)
7. **Generate** — `deep-research generate` produces PDF/HTML with auto-generated appendix

## Critical Rules

### .meta.json is MANDATORY
- `deep-research plan` and `deep-research add` **pre-create** `.meta.json` templates in each agent directory.
- Every research agent MUST edit this file after writing reports — fill in `model_id`, `tokens_total`, `searched_links`, `duration`, `research_completed_at`.
- If `.meta.json` is missing or empty, that direction **will not appear** in the PDF appendix.
- The synthesize agent MUST check: `for d in agent-*/; do test -f "$d/.meta.json" || echo "MISSING: $d"; done`

### Progressive File Assembly
- **NEVER** write the full README.md or agent report in one shot. Output token limits will truncate long reports.
- Write section-by-section: generate one section → Write/Edit to file → next section → Edit append.
- Each section should be as long as it needs to be, but no single write should exceed ~2000 words.
- The `report_template.md` shows the recommended section order and structure.

### PDF-Ready Markdown
- **NO `---` horizontal rules** in report body. Use headings (`##`, `###`) for visual separation.
- The `---` syntax renders as a visible horizontal line in PDF, not a page break.
- A Lua filter converts `---` to page breaks at build time, but reports should not rely on this.
- No emoji in tables. Max 4 columns per table.
- Bibliography: ordered list with blank lines between entries. URLs in angle brackets.

## Output

```
docs/research/<topic>/
├── requirements.md       # User requirements brief
├── plan.md               # Research plan with directions
├── pricing/              # Direction directory
│   ├── gpt.md
│   └── .meta.json
├── capability/
│   ├── reasoning.md
│   └── .meta.json
├── README.md             # Final report (main agent)
└── output/
    └── report.pdf        # PDF with appendix
```
