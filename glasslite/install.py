"""Install the bundled Claude Code skill (and optionally a Bash permission rule)."""
from __future__ import annotations

import json
import shutil
from importlib.resources import files
from pathlib import Path

RULE = "Bash(glasslite *)"


def install_skill(claude_home: Path | None = None, allow: bool = False) -> None:
    claude_home = claude_home or Path.home() / ".claude"
    dest = claude_home / "skills" / "glasslite" / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with files("glasslite").joinpath("skill/SKILL.md").open("rb") as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)
    print(f"skill installed: {dest}")
    if not allow:
        print(f'tip: rerun with --allow to add "{RULE}" to {claude_home / "settings.json"}')
        return
    settings_path = claude_home / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    rules = settings.setdefault("permissions", {}).setdefault("allow", [])
    if RULE not in rules:
        rules.append(RULE)
        settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f'permission rule "{RULE}" present in {settings_path}')
