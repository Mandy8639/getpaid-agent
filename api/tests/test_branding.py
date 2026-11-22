"""Intuit terms: no Intuit marks in names, branding or UI. Setup docs may name QuickBooks."""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKS = re.compile(r"quickbooks|\bqbo?\b|intuit", re.IGNORECASE)


def test_package_names_carry_no_intuit_marks() -> None:
    names = [
        tomllib.loads((ROOT / "api/pyproject.toml").read_text())["project"]["name"],
        json.loads((ROOT / "web/package.json").read_text())["name"],
        json.loads((ROOT / "mcp/package.json").read_text())["name"],
    ]
    assert not [n for n in names if MARKS.search(n)]


def test_web_ui_source_carries_no_intuit_marks() -> None:
    assert (ROOT / "web/src").is_dir()
    hits = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "web/src").rglob("*")
        if p.suffix in {".ts", ".tsx", ".css"} and MARKS.search(p.read_text())
    ]
    assert hits == []
