"""guard の見張りは 1 見張り 1 file で足せるか（並ぶ PR が同じ所へ足して衝突する形が戻らないかの注入の試験）。

見張りを足す PR が全部、skill guard-rules の SKILL.md の表と値の表の例・plugin の説明・plugins/README.md・
guard_common.py の DEFAULTS へ行を足して、続けて衝突した。正本は見張りの file の頭（HOOKS・VALUES）と
skills/guard-rules/見張り/<名>.md の 2 つだけにし、皆の所には見張りの名も鍵も並べない。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "plugins" / "guard"
HEADS = ("## 止められた・知らされた時の直し方", "## 値の表の鍵", "## 射程の外")


def _common(root):
    sys.path.insert(0, str(root / "scripts"))
    try:
        import importlib
        import guard_common
        return importlib.reload(guard_common)
    finally:
        sys.path.pop(0)


def problems(root: Path) -> list[str]:
    """guard の plugin の dir（root）を照らした崩れの並び。空なら緑。"""
    G = _common(root)
    errs = []
    docs = root / "skills" / "guard-rules" / "見張り"
    decl = {}
    for p in G.watcher_files(str(root / "scripts")):
        name = Path(p).stem
        d = G.declared(p)
        if "VALUES" not in d or not isinstance(d["VALUES"], dict):
            errs.append(f"{name}: 頭に VALUES（この見張りだけが読む鍵と既定・無ければ {{}}）が無い")
        decl[name] = d.get("VALUES") or {}
    have = {p.stem for p in docs.glob("*.md")}
    for name in sorted(set(decl) - have):
        errs.append(f"{name}: 直し方の file 見張り/{name}.md が無い")
    for name in sorted(have - set(decl)):
        errs.append(f"見張り/{name}.md: 見張りの file scripts/{name}.py が無い（消した見張りの直し方は一緒に消す）")
    seen = {}
    for name, vals in decl.items():
        for k in vals:
            if k in G.COMMON or k in seen:
                errs.append(f"{name}: 鍵 {k} は {seen.get(k, '皆の鍵')} と重なる（鍵は 1 つの見張りか皆の鍵のどちらか 1 か所）")
            seen[k] = name
    shared = {
        "skills/guard-rules/SKILL.md": (root / "skills" / "guard-rules" / "SKILL.md").read_text(encoding="utf-8"),
        ".claude-plugin/plugin.json": json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["description"],
        "scripts/guard_common.py": (root / "scripts" / "guard_common.py").read_text(encoding="utf-8"),
        "scripts/guard.py": (root / "scripts" / "guard.py").read_text(encoding="utf-8"),
    }
    readme = root.parent / "README.md"
    if readme.is_file():
        shared["plugins/README.md"] = "\n".join(ln for ln in readme.read_text(encoding="utf-8").splitlines()
                                                if ln.startswith("- **guard**"))
    for name in sorted(decl):
        f = docs / f"{name}.md"
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        if not first.startswith(f"# {name}"):
            errs.append(f"見張り/{name}.md: 1 行目が「# {name}（呼び名）」でない")
        for h in HEADS:
            if h not in text:
                errs.append(f"見張り/{name}.md: 欄「{h}」が無い")
        for k in decl[name]:
            if f"`{k}`" not in text and f'"{k}"' not in text:
                errs.append(f"見張り/{name}.md: この見張りの鍵 {k} の書き方が無い")
        call = re.search(r"（(.+?)）", first)
        words = [name] + list(decl[name]) + ([call.group(1)] if call else [])
        for where, body in shared.items():
            for w in words:
                if re.search(r"(?<![0-9A-Za-z_])%s(?![0-9A-Za-z_])" % re.escape(w), body):
                    errs.append(f"{where}: 見張り {name} の「{w}」を並べた（並ぶ PR が全部ここへ足して衝突する。"
                                f"見張り/{name}.md と見張りの頭に置く）")
    skill = shared["skills/guard-rules/SKILL.md"]
    for k in G.COMMON:
        if f"`{k}`" not in skill:
            errs.append(f"skills/guard-rules/SKILL.md: 皆の鍵 {k} の書き方が無い")
    return errs


def test_今の土台は緑():
    assert problems(GUARD) == []


@pytest.fixture
def copy(tmp_path):
    d = tmp_path / "plugins" / "guard"
    shutil.copytree(GUARD, d, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "plugins" / "README.md", tmp_path / "plugins" / "README.md")
    return d


def _edit(path, old, new):
    t = path.read_text(encoding="utf-8")
    assert old in t, f"{path} の形が変わった（この注入を合わせる）"
    path.write_text(t.replace(old, new, 1), encoding="utf-8")


def test_SKILL_の表へ見張りの行を足すと赤(copy):
    f = copy / "skills" / "guard-rules" / "SKILL.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n| spec_gate（設計書の型の gate を直に呼ぶ手） | PreToolUse | 止める | 直す |\n",
                 encoding="utf-8")
    assert any("SKILL.md" in e and "spec_gate" in e for e in problems(copy))


def test_皆の既定へ見張りの鍵を足すと赤(copy):
    _edit(copy / "scripts" / "guard_common.py", 'COMMON = {\n', 'COMMON = {\n    "context_limit": 300_000,\n')
    errs = problems(copy)
    assert any("guard_common.py" in e and "context_limit" in e for e in errs)


def test_plugin_の説明と_README_に見張りを並べると赤(copy):
    p = copy / ".claude-plugin" / "plugin.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["description"] += "未回答の台帳を持つ。"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    _edit(copy.parent / "README.md", "- **guard**（A5）: 守りの hook を", "- **guard**（A5）: 守りの hook（irreversible ほか）を")
    errs = problems(copy)
    assert any("plugin.json" in e and "未回答の台帳" in e for e in errs)
    assert any("README.md" in e and "irreversible" in e for e in errs)


def test_直し方の_file_の無い見張りと_VALUES_の無い見張りは赤(copy):
    (copy / "scripts" / "zz_sakumono.py").write_text('HOOKS = {"pre": "check"}\n\n\ndef check(data, vals):\n    return ""\n',
                                                     encoding="utf-8")
    errs = problems(copy)
    assert any("zz_sakumono" in e and "見張り/zz_sakumono.md" in e for e in errs)
    assert any("zz_sakumono" in e and "VALUES" in e for e in errs)


def test_鍵の重なりと書き方の無い鍵は赤(copy):
    _edit(copy / "scripts" / "spec_gate.py", "VALUES = {}", 'VALUES = {"context_limit": 1, "spec_sakumono": []}')
    errs = problems(copy)
    assert any("context_limit" in e and "重なる" in e for e in errs)
    assert any("spec_gate.md" in e and "spec_sakumono" in e for e in errs)


def test_見張りの無い直し方の_file_は赤(copy):
    (copy / "scripts" / "spec_gate.py").unlink()
    assert any("見張り/spec_gate.md" in e for e in problems(copy))


def test_既定は皆の鍵と各見張りの_VALUES_から組む(copy):
    G = _common(GUARD)
    assert G.DEFAULTS["context_limit"] == 300_000 and G.DEFAULTS["state_dir"].endswith("af-guard")
    assert G.DEFAULTS["context_stop_max"] == 2 and G.DEFAULTS["ask_prior_lookup"] == []
    _edit(copy / "scripts" / "context_size.py", '"context_limit": 300_000,', '"context_limit": 123,')
    assert _common(copy).DEFAULTS["context_limit"] == 123
    _common(GUARD)


def test_止めた文は見張りの直し方の_file_を指し_その_file_が在る(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), AF_GUARD_STATE=str(tmp_path / "st"))
    env.pop("SKILL_VALUES", None)
    p = subprocess.run([sys.executable, "-B", str(GUARD / "scripts" / "guard.py"), "pre"], capture_output=True, text=True,
                       env=env, cwd=tmp_path, input=json.dumps({"tool_name": "Bash", "session_id": "s1", "cwd": str(tmp_path),
                                                                "tool_input": {"command": "python3 型/check_spec_doc.py x --lock"}}))
    reason = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    m = re.search(r"直し方と値の表の鍵: (\S+\.md)", reason)
    assert m and Path(m.group(1)).is_file() and Path(m.group(1)).stem == "spec_gate", reason


@pytest.mark.parametrize("bad", ["dict(x=1)", '{["a"]: 1}'], ids=["式", "鍵が並び"])
def test_壊れた_VALUES_は自分の_HOOKS_を巻き込まず_試験は赤(copy, bad):
    _edit(copy / "scripts" / "spec_gate.py", "VALUES = {}", "VALUES = " + bad)
    G = _common(copy)
    assert G.declared(str(copy / "scripts" / "spec_gate.py")).get("HOOKS") == {"pre": "check"}
    assert any("spec_gate" in e and "VALUES" in e for e in problems(copy))
    _common(GUARD)
