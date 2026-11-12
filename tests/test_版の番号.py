"""各 plugin の version が、CHANGELOG の一番新しい版とそろっているか（docs/版の出し方.md）。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def 一番新しい版():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[v(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", text, re.M)
    assert m, "CHANGELOG に版の見出しが無い"
    return m.group(1)


def test_plugin_の_version_は土台の版と同じ():
    版 = 一番新しい版()
    files = sorted(ROOT.glob("plugins/*/.claude-plugin/plugin.json"))
    assert files
    違う = {
        f.parent.parent.name: json.loads(f.read_text(encoding="utf-8")).get("version")
        for f in files
    }
    違う = {k: v for k, v in 違う.items() if v != 版}
    assert not 違う, f"土台の版 {版} と違う plugin: {違う}"
