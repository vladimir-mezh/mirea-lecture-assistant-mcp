"""Print the release tag for this commit; a pushed tag must match the version."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mirea_assistant_mcp import __version__  # noqa: E402

project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
if project["version"] != __version__:
    sys.exit(f"pyproject.toml {project['version']} != package {__version__}")
tag = f"v{__version__}"
if os.environ.get("GITHUB_REF_TYPE") == "tag" and os.environ.get("GITHUB_REF_NAME") != tag:
    sys.exit(f"Tag {os.environ.get('GITHUB_REF_NAME')} does not match version {tag}")
with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as output:
    output.write(f"tag={tag}\n")
print(tag)
