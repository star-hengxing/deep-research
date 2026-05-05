"""Shared fixtures for deep-research tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    d = tmp_path / "research" / "test-project"
    d.mkdir(parents=True, exist_ok=True)
    return d
