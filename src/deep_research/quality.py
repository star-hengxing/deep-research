"""Quality gate checks for research reports.

Layer 0: Format (existing) — URL accessibility, markdown lint
Layer 1: Structure — report skeleton completeness
Layer 2: Evidence — citation coverage and traceability
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from urllib import error, parse, request


# ── Data types ──


class Severity(StrEnum):
    FAIL = "fail"
    WARN = "warn"
    INFO = "info"


@dataclass
class Finding:
    severity: Severity
    check: str
    message: str
    details: list[str] = field(default_factory=list)


# ── Text helpers ──


def _strip_frontmatter(text: str) -> str:
    return re.sub(r"^---.*?---\s*", "", text, count=1, flags=re.DOTALL)


_REFS_HEADING_RE = re.compile(
    r"^(#{1,2})\s+(?:参考文献|References|Bibliography)"
    r"(?:\s*/\s*(?:参考文献|References|Bibliography))?",
    re.IGNORECASE | re.MULTILINE,
)


def _split_body_refs(text: str) -> tuple[str, str]:
    """Split report into (body, references_section). Frontmatter is stripped."""
    body = _strip_frontmatter(text)
    m = _REFS_HEADING_RE.search(body)
    if m:
        return body[: m.start()], body[m.start() :]
    return body, ""


def _remove_code_blocks(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def _code_block_mask(lines: list[str]) -> list[bool]:
    """Pre-compute which lines are inside fenced code blocks (O(n))."""
    mask = [False] * len(lines)
    in_code = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            mask[i] = True
            in_code = not in_code
        elif in_code:
            mask[i] = True
    return mask


def _refs_start_line(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if _REFS_HEADING_RE.match(line):
            return i
    return len(lines)


def _count_words(text: str) -> int:
    """Count words: Chinese characters + English words."""
    clean = re.sub(r"[#*\[\]\(\)\|`>]", " ", text)
    clean = re.sub(r"https?://\S+", "", clean)
    chinese = len(re.findall(r"[一-鿿]", clean))
    english = len(re.findall(r"[a-zA-Z]+", clean))
    return chinese + english


def _extract_paragraphs(body: str) -> list[str]:
    """Extract content paragraphs, skipping headings, code blocks, tables."""
    clean = _remove_code_blocks(body)
    paragraphs: list[str] = []
    current: list[str] = []
    for line in clean.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append("\n".join(current))
                current = []
            continue
        if stripped.startswith("#") or stripped.startswith("|"):
            if current:
                paragraphs.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def _parse_plan_directions(project_dir: Path) -> list[str]:
    plan_path = project_dir / "plan.md"
    if not plan_path.exists():
        return []
    text = plan_path.read_text(encoding="utf-8")
    directions: list[str] = []
    for line in text.split("\n"):
        m = re.match(r"^\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        cell = m.group(1).strip()
        if not cell or re.match(r"^[-:]+$", cell) or cell.lower() in ("agent", "#"):
            continue
        directions.append(cell)
    return directions


# ── Layer 0: Format (existing functions) ──


def extract_urls(report_path: Path) -> list[str]:
    text = report_path.read_text(encoding="utf-8")
    return re.findall(r"https?://[^\s\)\]\"'<>]+", text)


def _encode_url(url: str) -> str:
    parts = parse.urlsplit(url)
    path = parse.quote(parts.path, safe="/:@!$&'()*+,;=")
    query = parse.quote(parts.query, safe="/:@!$&'()*+,;=")
    return parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def check_url(url: str, timeout: int = 10) -> tuple[bool, str]:
    if not url:
        return False, "No URL"

    encoded_url = _encode_url(url)

    def _try(method: str) -> tuple[bool | None, str]:
        try:
            req = request.Request(encoded_url, method=method)
            req.add_header("User-Agent", "Research URL Verifier/1.0")
            with request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True, "OK"
                return None, f"HTTP {resp.status}"
        except error.HTTPError as e:
            return None, f"HTTP {e.code}"
        except error.URLError as e:
            return False, f"URL error: {e.reason}"
        except Exception as e:
            return False, f"Connection error: {str(e)[:60]}"

    ok, msg = _try("HEAD")
    if ok is not None:
        return ok, msg
    ok, msg = _try("GET")
    return ok or False, msg


def _check_connectivity() -> bool:
    import socket

    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        req = request.Request("https://1.1.1.1")
        req.add_header("User-Agent", "curl/8.0")
        with request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (OSError, Exception):
        return False


def check_references_format(report_path: Path) -> list[str]:
    text = report_path.read_text(encoding="utf-8")
    body = re.sub(r"^---.*?---\s*", "", text, count=1, flags=re.DOTALL)
    warnings: list[str] = []

    bib = re.search(
        r"## (?:References|参考文献|Bibliography)(?:\s*/\s*(?:References|参考文献|Bibliography))?(.*?)(?=##|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if not bib:
        return ["Missing ## References / ## 参考文献 section"]
    refs = bib.group(1).strip()
    if not refs:
        return ["References section is empty"]

    lines = refs.split("\n")
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if re.match(r"\[\d+\]", stripped) and i > 0:
            prev = lines[i - 1].rstrip()
            if re.match(r"\[\d+\]", prev):
                warnings.append(
                    f'  References line {i + 1}: "{stripped}" has no blank line before it '
                    "(pandoc merges adjacent lines into one paragraph)"
                )

    return warnings


def check_report_urls(report_path: Path) -> tuple[bool, str]:
    urls = extract_urls(report_path)

    if not urls:
        return False, "No URLs found in report."

    connectivity_ok = _check_connectivity()

    results = []
    bad = 0
    skipped = 0
    for url in urls:
        if not connectivity_ok:
            skipped += 1
            results.append(f"  ~ skipped (no network)  {url}")
            continue
        ok, msg = check_url(url)
        icon = "✓" if ok else "✗"
        results.append(f"  {icon} {msg:20s} {url}")
        if not ok:
            bad += 1

    lines = [
        f"{'=' * 60}",
        f"URL CHECK: {report_path.name}",
        f"{'=' * 60}",
    ]
    if skipped:
        lines.append(f"Network unavailable — {skipped} URL(s) skipped (treated as passing).")
    else:
        lines.append(f"Total: {len(urls)} URLs, {bad} failed")
    lines += [f"{'-' * 60}", *results]

    _shell = sys.platform == "win32"
    with contextlib.suppress(FileNotFoundError, subprocess.SubprocessError):
        subprocess.run(
            ["prettier", "--write", str(report_path)],
            shell=_shell,
            capture_output=True,
            timeout=30,
        )
    lint_config = Path(__file__).resolve().parent.parent.parent / ".markdownlint.json"
    with contextlib.suppress(FileNotFoundError, subprocess.SubprocessError):
        r = subprocess.run(
            ["markdownlint", "--config", str(lint_config), str(report_path)],
            shell=_shell,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            lines.extend(["", f"{'=' * 60}", "FORMAT (markdownlint)", f"{'=' * 60}", r.stdout[:2000]])

    ref_warnings = check_references_format(report_path)
    if ref_warnings:
        lines.extend(["", f"{'=' * 60}", "REFERENCES FORMAT", f"{'=' * 60}", *ref_warnings])

    passed = (bad == 0) or skipped == len(urls)
    return passed, "\n".join(lines)


# ── Layer 1: Structure ──

_CN_STOP_CHARS = set("与和及或的")  # 虚词，匹配时忽略


def _direction_covered(direction: str, headings_lower: list[str]) -> bool:
    """Check if a direction is covered by any heading.

    Tries substring match first; falls back to checking whether all
    content characters (Chinese, minus stop chars) and English words
    from the direction appear in at least one heading.  Handles the
    common case where synthesis expands direction titles (e.g.
    "租房平台与app对比" → "租房平台与App全面对比").
    """
    d_lower = direction.lower()
    if any(d_lower in h for h in headings_lower):
        return True
    cn_chars = set(re.findall(r"[一-鿿]", d_lower)) - _CN_STOP_CHARS
    en_words = set(re.findall(r"[a-z]+", d_lower))
    if not cn_chars and not en_words:
        return False
    for h in headings_lower:
        cn_ok = all(c in h for c in cn_chars) if cn_chars else True
        en_ok = all(w in h for w in en_words) if en_words else True
        if cn_ok and en_ok:
            return True
    return False


def check_structure(report_path: Path, project_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    text = report_path.read_text(encoding="utf-8")
    body, refs = _split_body_refs(text)

    # Section coverage against plan.md directions
    directions = _parse_plan_directions(project_dir)
    if directions:
        headings = re.findall(r"^#{1,3}\s+(.+)", body, re.MULTILINE)
        headings_lower = [h.lower().strip() for h in headings]
        missing = [d for d in directions if not _direction_covered(d, headings_lower)]
        if missing:
            findings.append(
                Finding(
                    Severity.FAIL,
                    "章节覆盖",
                    f"{len(directions) - len(missing)}/{len(directions)} directions covered",
                    [f"Missing: {d}" for d in missing],
                )
            )
        else:
            findings.append(
                Finding(Severity.INFO, "章节覆盖", f"{len(directions)}/{len(directions)} directions covered")
            )

    # Summary existence (≥100 words)
    summary_match = re.search(
        r"#{1,3}\s+(?:摘要|Executive\s+Summary|Summary|概述)\s*\n(.*?)(?=\n#{1,3}\s|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if summary_match:
        wc = _count_words(summary_match.group(1))
        if wc < 100:
            findings.append(Finding(Severity.FAIL, "摘要", f"Too short: {wc} words (need ≥100)"))
        else:
            findings.append(Finding(Severity.INFO, "摘要", f"{wc} words"))
    else:
        findings.append(Finding(Severity.FAIL, "摘要", "No Summary/摘要 section found"))

    # Bibliography existence
    if refs:
        n_entries = len(re.findall(r"\[\d+\]", refs))
        findings.append(Finding(Severity.INFO, "参考文献", f"{n_entries} entries"))
    else:
        findings.append(Finding(Severity.FAIL, "参考文献", "No References/参考文献 section found"))

    # Word count threshold
    total_words = _count_words(body)
    if directions:
        threshold = len(directions) * 800
        if total_words < threshold:
            findings.append(
                Finding(
                    Severity.WARN,
                    "字数",
                    f"{total_words} (threshold: {len(directions)} × 800 = {threshold})",
                )
            )
        else:
            findings.append(Finding(Severity.INFO, "字数", f"{total_words}"))
    else:
        findings.append(Finding(Severity.INFO, "字数", f"{total_words}"))

    # Agent report completeness
    agent_dirs = sorted(
        d
        for d in project_dir.iterdir()
        if d.is_dir() and d.name != "output" and not d.name.startswith(".")
    )
    if agent_dirs:
        missing_reports = [d.name for d in agent_dirs if not list(d.glob("*.md"))]
        if missing_reports:
            findings.append(
                Finding(
                    Severity.FAIL,
                    "Agent 报告",
                    f"{len(missing_reports)} agent(s) have no .md report",
                    missing_reports,
                )
            )
        else:
            findings.append(
                Finding(Severity.INFO, "Agent 报告", f"All {len(agent_dirs)} agents have reports")
            )

    return findings


# ── Layer 2: Evidence ──

_DATA_PATTERN = re.compile(
    r"\d+\.?\d*%"  # percentages
    r"|\d+[万亿千百]"  # Chinese number units
    r"|(?:19|20)\d{2}年"  # Chinese year
    r"|\$[\d,.]+"  # dollar amounts
    r"|€[\d,.]+"  # euro amounts
    r"|￥[\d,.]+"  # yuan amounts
    r"|\d{1,3}(?:,\d{3})+"  # large comma-separated numbers
)

_CITATION_RE = re.compile(r"\[\d+\]")


def check_evidence(report_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    text = report_path.read_text(encoding="utf-8")
    body, refs = _split_body_refs(text)
    body_clean = _remove_code_blocks(body)

    # Citation density
    paragraphs = _extract_paragraphs(body)
    total_citations = len(_CITATION_RE.findall(body_clean))
    n_paragraphs = max(len(paragraphs), 1)
    density = total_citations / n_paragraphs
    if density < 0.3:
        findings.append(
            Finding(
                Severity.WARN,
                "引用密度",
                f"{density:.2f}/paragraph ({total_citations} citations, {n_paragraphs} paragraphs, need ≥0.3)",
            )
        )
    else:
        findings.append(Finding(Severity.INFO, "引用密度", f"{density:.2f}/paragraph"))

    # Orphan claims: lines with data but no [N]
    lines = text.split("\n")
    code_mask = _code_block_mask(lines)
    refs_start = _refs_start_line(lines)
    orphans: list[str] = []
    for i, line in enumerate(lines):
        if i >= refs_start or code_mask[i]:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("```"):
            continue
        if _DATA_PATTERN.search(stripped) and not _CITATION_RE.search(stripped):
            display = stripped[:60] + "..." if len(stripped) > 60 else stripped
            orphans.append(f'L{i + 1}: "{display}"')
    if orphans:
        shown = orphans[:10]
        suffix = f" (+{len(orphans) - 10} more)" if len(orphans) > 10 else ""
        findings.append(
            Finding(
                Severity.WARN,
                "孤立断言",
                f"{len(orphans)} claims with data but no citation{suffix}",
                shown,
            )
        )
    else:
        findings.append(Finding(Severity.INFO, "孤立断言", "None"))

    # Citation traceability: body [N] must exist in references
    body_nums = set(int(m) for m in re.findall(r"\[(\d+)\]", body_clean))
    ref_nums = set(int(m) for m in re.findall(r"\[(\d+)\]", refs)) if refs else set()

    if body_nums and ref_nums:
        missing = sorted(body_nums - ref_nums)
        if missing:
            findings.append(
                Finding(
                    Severity.FAIL,
                    "引用可追溯",
                    f"{len(missing)} citations missing from references",
                    [f"[{n}]" for n in missing],
                )
            )
        else:
            findings.append(Finding(Severity.INFO, "引用可追溯", "All citations have entries"))
    elif body_nums and not ref_nums:
        findings.append(
            Finding(Severity.FAIL, "引用可追溯", "Citations found but no references section")
        )
    else:
        findings.append(Finding(Severity.INFO, "引用可追溯", "N/A"))

    # Ghost references: defined but never cited in body
    if ref_nums and body_nums:
        ghosts = sorted(ref_nums - body_nums)
        if ghosts:
            findings.append(
                Finding(
                    Severity.WARN,
                    "幽灵引用",
                    f"{len(ghosts)} references never cited",
                    [f"[{n}]" for n in ghosts],
                )
            )
        else:
            findings.append(Finding(Severity.INFO, "幽灵引用", "None"))
    else:
        findings.append(Finding(Severity.INFO, "幽灵引用", "N/A"))

    # Source diversity: unique domains in references
    if refs:
        urls_in_refs = re.findall(r"https?://([^/\s\)\]>]+)", refs)
        domains: set[str] = set()
        for d in urls_in_refs:
            parts = d.lower().split(".")
            if len(parts) >= 2:
                domains.add(".".join(parts[-2:]))
            else:
                domains.add(d.lower())
        n_domains = len(domains)
        if n_domains < 5:
            findings.append(
                Finding(
                    Severity.WARN,
                    "来源多样性",
                    f"{n_domains} unique domains (recommend ≥5)",
                    sorted(domains),
                )
            )
        else:
            findings.append(Finding(Severity.INFO, "来源多样性", f"{n_domains} unique domains"))

    return findings


# ── Unified quality gate runner ──

_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARN: 1, Severity.FAIL: 2}
_SEVERITY_ICON = {Severity.FAIL: "✗", Severity.WARN: "⚠", Severity.INFO: "✓"}


def run_quality_gate(report_path: Path, project_dir: Path) -> tuple[bool, str]:
    """Run layers 1-2 and return (passed, formatted_output).

    Gate fails if any finding has severity FAIL.
    With strict=True in the caller, WARN also causes failure.
    """
    layers: list[tuple[str, list[Finding]]] = [
        ("Structure", check_structure(report_path, project_dir)),
        ("Evidence", check_evidence(report_path)),
    ]

    has_fail = False
    out: list[str] = ["╔══ Quality Gate ══╗"]

    for layer_name, findings in layers:
        worst = max(
            (f.severity for f in findings),
            key=lambda s: _SEVERITY_ORDER[s],
            default=Severity.INFO,
        )

        if worst == Severity.INFO:
            for f in findings:
                out.append(f"✓ {f.check}: {f.message}")
        else:
            icon = _SEVERITY_ICON[worst]
            out.append("")
            out.append(f"{icon} {layer_name}:")
            for f in findings:
                fi = _SEVERITY_ICON[f.severity]
                out.append(f"  {fi} {f.check}: {f.message}")
                for detail in f.details:
                    out.append(f"    {detail}")
                if f.severity == Severity.FAIL:
                    has_fail = True

    out.append("╚══════════════════╝")
    return not has_fail, "\n".join(out)
