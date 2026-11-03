"""The skill exposes the eight planned tools with descriptions agents can choose from."""
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLANNED = {"create_game_project", "write_game_files", "edit_scenes", "check_project", "run_game", "playtest_game",
           "inspect_project", "export_game"}


def test_manifest_lists_planned_tools():
    out = subprocess.run([sys.executable, "-m", "skillnet_sdk", "manifest", "--package", "tools"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    tools = {t["name"]: t for t in json.loads(out)}
    assert set(tools) == PLANNED
    for t in tools.values():
        assert t["description"].startswith(("Use ", "Start here")) and len(t["title"]) <= 60
        assert t["state_version"] == 1
    assert tools["playtest_game"]["long_running"] and tools["export_game"]["long_running"]
    card = yaml.safe_load((ROOT / "skill.yaml").read_text())
    assert {t["name"] for t in card["tools"]} == PLANNED
