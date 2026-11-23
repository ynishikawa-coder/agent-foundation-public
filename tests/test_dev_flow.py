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


def test_verify_は申告でなく記録で確かめる():
    skill = (PLUGIN / "skills" / "verify" / "SKILL.md").read_text(encoding="utf-8")
    assert "申告でなく記録" in skill and "記録の所在" in skill


def test_ほんまにできる表に届く先と写しの残りの行が在る():
    text = (PLUGIN / "skills" / "design-mode" / "SKILL.md").read_text(encoding="utf-8")
    rows = {m.group(1).strip() for m in re.finditer(r"^\s*\|\s*([^|]+?)\s*\|", text, flags=re.M)}
    for row in ("届く先", "写しの残り"):
        assert row in rows, f"ほんまにできる表に「{row}」の行が無い"


def test_設計の相談は論点ごとに窓を並べ_1_本の列にしない():
    text = (PLUGIN / "skills" / "design-mode" / "SKILL.md").read_text(encoding="utf-8")
    assert "論点ごとに窓を並べて同時に進める" in text and "1 本の列にしない" in text
    assert "一番手前" not in text, "問いを表の一番手前の 1 つから取る形が戻った"

