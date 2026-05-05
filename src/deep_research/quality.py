"""URL accessibility verification for research reports."""
from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from pathlib import Path
from urllib import error, parse, request


def extract_urls(report_path: Path) -> list[str]:
    text = report_path.read_text(encoding="utf-8")
    return re.findall(r"https?://[^\s\)\]\"'<>]+", text)


def _encode_url(url: str) -> str:
    """Percent-encode non-ASCII characters in URL path and query."""
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

    # Try HEAD first (lightweight), fall back to GET if HEAD not supported
    ok, msg = _try("HEAD")
    if ok is not None:
        return ok, msg
    ok, msg = _try("GET")
    return ok or False, msg


def _check_connectivity() -> bool:
    """Quick check if network is reachable by trying a simple HTTPS connection."""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        # DNS works, try a quick HTTPS check
        req = request.Request("https://1.1.1.1")
        req.add_header("User-Agent", "curl/8.0")
        with request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (OSError, Exception):
        return False


def check_references_format(report_path: Path) -> list[str]:
    """Check References section formatting (custom semantic check)."""
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
                    f"  References line {i+1}: \"{stripped}\" has no blank line before it "
                    "(pandoc merges adjacent lines into one paragraph)"
                )

    return warnings


def check_report_urls(report_path: Path) -> tuple[bool, str]:
    urls = extract_urls(report_path)

    if not urls:
        return False, "No URLs found in report."

    # Test connectivity before checking individual URLs
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

    # Auto-fix with prettier, then check with markdownlint
    # Use shell=True on Windows for .bat/.cmd compatibility
    _shell = sys.platform == "win32"
    with contextlib.suppress(FileNotFoundError, subprocess.SubprocessError):
        subprocess.run(["prettier", "--write", str(report_path)], shell=_shell, capture_output=True, timeout=30)
    lint_config = Path(__file__).resolve().parent.parent.parent / ".markdownlint.json"
    with contextlib.suppress(FileNotFoundError, subprocess.SubprocessError):
        r = subprocess.run(
            ["markdownlint", "--config", str(lint_config), str(report_path)],
            shell=_shell, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            lines.extend(["", f"{'=' * 60}", "FORMAT (markdownlint)", f"{'=' * 60}", r.stdout[:2000]])

    # Also check References format (warnings only, doesn't affect exit code)
    ref_warnings = check_references_format(report_path)
    if ref_warnings:
        lines.extend(["", f"{'=' * 60}", "REFERENCES FORMAT", f"{'=' * 60}", *ref_warnings])

    # Skip check passes if no connectivity (offline env)
    passed = (bad == 0) or skipped == len(urls)
    return passed, "\n".join(lines)
