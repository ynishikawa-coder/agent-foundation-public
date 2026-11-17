"""dev-flow プラグインが、プラグインとして入る形で置かれているかを見る。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "dev-flow"
# 何の skill が在るべきかの正本は plugins/README.md の表（tests/test_plugins_list.py が照らす）。ここは在る物の形だけを見る。
SKILLS = {p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir()}
# SKILL が指す付属の物（同じ dir に在ること）。
ATTACHED = {
    "codex": ["codex_pack.py"],
    "preimpl-cleanup": ["整地受領証.template.md"],
}
# 写す元の repo の中の置き場を指したら、土台の中で閉じていない。
OUTSIDE_REFS = [
    r"core/(rules|dev-workflow|dev-head|spec-template|sop|hooks|lib)\b",
    r"agents/[A-Za-z0-9_-]+/",
    r"requirements-to-brief",
    r"pixel-office",
]


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, flags=re.S)
    assert m, "frontmatter が無い"
    out = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def test_plugin_json_の形():
    data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "dev-flow"
    assert data.get("description")


def test_各_SKILL_の名前と説明():
    for name in SKILLS:
        fm = frontmatter((PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))
        assert fm.get("name") == name, (name, fm.get("name"))
        assert len(fm.get("description", "")) >= 20, name


def test_付属の物が在る():
    for name, files in ATTACHED.items():
        for f in files:
            assert (PLUGIN / "skills" / name / f).is_file(), f"{name}/{f}"


def test_土台の中で閉じる():
    hits = []
    for p in sorted(PLUGIN.rglob("*")):
        if p.is_file() and p.suffix in {".md", ".py", ".json"}:
            text = p.read_text(encoding="utf-8")
            for pat in OUTSIDE_REFS:
                if re.search(pat, text):
                    hits.append(f"{p.relative_to(ROOT)}: {pat}")
    assert not hits, hits


def test_整地は根治の_4_つの問いを持ち_注入の試験と残る穴の欄が在る():
    skill_dir = PLUGIN / "skills" / "preimpl-cleanup"
    tpl = (skill_dir / "整地受領証.template.md").read_text(encoding="utf-8")
    heads = [l for l in tpl.splitlines() if l.startswith("## ")]
    assert heads == ["## 1. 構造の原因", "## 2. 同じ原因から起きている他の問題",
                     "## 3. 構造の変え方（足す物・畳む物）", "## 4. 注入の試験と残る穴"], heads
    for hole in ["手で写す所", "選べる値の外が入る所", "黙って進む所", "正しい道を通らずに出る所", "申告で済む確かめ"]:
        assert hole in tpl, f"残る穴の行が無い: {hole}"
    skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "4 つの問い" in frontmatter(skill)["description"]
    assert "3 つの問い" not in skill and "3 欄の" not in skill, "古い 3 問の言い回しが残る"


def test_verify_は申告でなく記録で確かめる():
    skill = (PLUGIN / "skills" / "verify" / "SKILL.md").read_text(encoding="utf-8")
    assert "申告でなく記録" in skill and "記録の所在" in skill
