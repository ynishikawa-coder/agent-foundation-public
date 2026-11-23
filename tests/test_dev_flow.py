"""dev-flow プラグインが、プラグインとして入る形で置かれているかを見る。"""
import json
import re
from pathlib import Path

from test_dev_flow_okiba import (ほんまにできる表の外れ, 原因の段の外れ, 未来の段の外れ, 行き先の外れ, 論点の窓の外れ,
                                 step1の外れ, verify_の外れ)
from test_seichi_nokoru_ana import 残る穴の行

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


def test_整地は根治の_5_段を持ち_解決の段に注入の試験と残る穴が在る():
    skill_dir = PLUGIN / "skills" / "preimpl-cleanup"
    tpl = (skill_dir / "整地受領証.template.md").read_text(encoding="utf-8")
    heads = [l for l in tpl.splitlines() if l.startswith("## ")]
    assert heads == ["## 1. 意図", "## 2. 課題", "## 3. 原因と同じ原因の他の問題",
                     "## 4. 解決（足す物・畳む物・注入の試験と残る穴）", "## 5. 未来"], heads
    # 残る穴は解決の節の「残る穴」の欄の下の箇条の名で照らす（雛形の別の所に字が在っても数えない）
    labels = 残る穴の行(tpl)
    for hole in ["手で写す所", "選べる値の外が入る所", "黙って進む所", "正しい道を通らずに出る所", "申告で済む確かめ"]:
        assert any(lab.endswith(hole) for lab in labels), f"残る穴の欄に行が無い: {hole}（欄の行: {labels}）"
    skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "5 段（意図→課題→原因→解決→未来" in frontmatter(skill)["description"]
    assert 原因の段の外れ(skill, tpl) == []
    assert 未来の段の外れ(skill, tpl) == []
    for old in ["3 つの問い", "4 つの問い", "構造の原因"]:
        assert old not in skill and old not in tpl, f"古い根治の言い回しが残る: {old}"


def test_規律を足す時も止める物かの後に誤りが入れない形と注入の試験を書く():
    skill = (PLUGIN / "skills" / "register-rule" / "SKILL.md").read_text(encoding="utf-8")
    assert step1の外れ(skill) == []
    for old in ["3 つの問い", "文を 1 本足すことを直しの中心にしない"]:
        assert old not in skill, f"古い根治の言い回しが残る: {old}"


def test_verify_は申告でなく記録で確かめる():
    skill = (PLUGIN / "skills" / "verify" / "SKILL.md").read_text(encoding="utf-8")
    assert verify_の外れ(skill) == []


def test_ほんまにできる表に届く先と写しの残りの行が在る():
    text = (PLUGIN / "skills" / "design-mode" / "SKILL.md").read_text(encoding="utf-8")
    assert ほんまにできる表の外れ(text) == []


def test_設計の相談は論点ごとに窓を並べ_1_本の列にしない():
    text = (PLUGIN / "skills" / "design-mode" / "SKILL.md").read_text(encoding="utf-8")
    assert 論点の窓の外れ(text) == []
    assert "一番手前" not in text, "問いを表の一番手前の 1 つから取る形が戻った"


def test_整地の解決は全部の原因に行き先を付ける():
    d = PLUGIN / "skills" / "preimpl-cleanup"
    skill, tpl = (d / "SKILL.md").read_text(encoding="utf-8"), (d / "整地受領証.template.md").read_text(encoding="utf-8")
    assert 行き先の外れ(skill, tpl) == []
    assert "どれを今回直す" not in skill + tpl
